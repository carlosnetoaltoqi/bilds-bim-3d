#!/usr/bin/env python3
"""
parse_ifc.py — Extrai geometria de arquivos IFC4 e gera JSONs { pos, col, idx }.

Uso direto:
  python3 scripts/parse_ifc.py <ifc_file> <output_dir> [--slug <slug>]

Uso via build.py (recomendado):
  build.py lê file_map do config.json e chama parse_one() para cada arquivo.

Saída:
  <output_dir>/<slug>_raw.json  — geometria expandida (sem idx, vértices repetidos)
  Rodar dedup.py depois gera a versão final com idx (redução ~80% de vértices).

BUGS CONHECIDOS E SOLUÇÕES:
  - Não aplicar IFCLOCALPLACEMENT → peças separadas por metros (bug crítico)
  - split(',') em vez de split_top() → índices deslocados por vírgulas em strings STEP
  - Não extrair IFCINDEXEDCOLOURMAP → modelo aparece todo cinza
  - Converter mm→m quando o exportador já usa metros → modelo 1000× maior
"""
import re
import sys
import json
import math
import struct
import argparse
import os


# ─── Utilitários STEP ────────────────────────────────────────────────────────

def split_top(s):
    """Divide string STEP por vírgulas no nível 0 (respeitando parênteses e strings)."""
    parts = []
    depth = 0
    in_str = False
    cur = []
    for c in s:
        if c == "'":
            in_str = not in_str
            cur.append(c)
        elif in_str:
            cur.append(c)
        elif c == ',' and depth == 0:
            parts.append(''.join(cur).strip())
            cur = []
        else:
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            cur.append(c)
    parts.append(''.join(cur).strip())
    return parts


def parse_floats(s):
    r"""
    Extrai todos os floats de uma string STEP.

    O grupo da mantissa exige pelo menos um dígito ANTES ou DEPOIS do ponto
    (nunca os dois opcionais ao mesmo tempo) — formato STEP permite mantissa
    sem dígitos após o ponto quando há expoente, ex: '-4.E-16' (praticamente
    zero). Uma regex que trata os dígitos após o ponto como sempre opcionais
    (`\.?[0-9]+`) falha nesse caso: ela para em '-4.' (sem consumir o '.'),
    e o 'E-16' restante vira um número fantasma separado ('-16'). Um valor ~0
    assim vira dois valores espúrios grandes — bug real observado em campo:
    fragmentos de peça aparecendo a 4-16m de distância no viewer 3D, quando
    a causa era essa corrupção de parsing, não posicionamento aberrante no IFC
    de origem. Ver docs/specs/leitor-ifc.md.
    """
    return [float(x) for x in re.findall(
        r'[-+]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)(?:[eE][-+]?[0-9]+)?', s
    )]


def parse_ints(s):
    """Extrai todos os inteiros de uma string."""
    return [int(x) for x in re.findall(r'\d+', s)]


# ─── Álgebra linear 4×4 (row-major) ──────────────────────────────────────────

def mat_identity():
    return [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]


def mat_mul(A, B):
    C = [0.0] * 16
    for r in range(4):
        for c in range(4):
            for k in range(4):
                C[r * 4 + c] += A[r * 4 + k] * B[k * 4 + c]
    return C


def apply_matrix(M, p):
    x, y, z = p
    return [
        M[0] * x + M[1] * y + M[2] * z + M[3],
        M[4] * x + M[5] * y + M[6] * z + M[7],
        M[8] * x + M[9] * y + M[10] * z + M[11],
    ]


def normalize(v):
    n = math.sqrt(sum(c * c for c in v))
    return [c / n for c in v] if n > 1e-12 else v


def cross(a, b):
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


# ─── Parse do arquivo IFC ─────────────────────────────────────────────────────

def build_entity_index(content):
    """
    Retorna dict: entity_id (int) → (entity_type (str), args_string (str))
    Ignora linhas que não são entidades (#id = TYPE(...)).
    """
    index = {}
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith('#'):
            continue
        # O ) final é obrigatório para evitar que .* capture ") ;" nos args
        m = re.match(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*;?\s*$', line)
        if not m:
            # Fallback: linha sem ) final (entidade parcial ou malformada)
            m = re.match(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)', line)
        if m:
            eid = int(m.group(1))
            etype = m.group(2)
            args = m.group(3)
            index[eid] = (etype, args)
    return index


# ─── Resolução de IFCAXIS2PLACEMENT3D → matriz 4×4 ───────────────────────────

def parse_cartesian_point(idx, eid):
    etype, args = idx[eid]
    coords = parse_floats(args)
    while len(coords) < 3:
        coords.append(0.0)
    return coords[:3]


def parse_direction(idx, eid):
    etype, args = idx[eid]
    vals = parse_floats(args)
    while len(vals) < 3:
        vals.append(0.0)
    return vals[:3]


def axis2placement_mat(idx, eid):
    """IFCAXIS2PLACEMENT3D → matriz 4×4 row-major."""
    etype, args = idx[eid]
    parts = split_top(args)

    loc_id = int(parts[0].lstrip('#'))
    T = parse_cartesian_point(idx, loc_id)

    # Axis (Z local) — padrão [0,0,1]
    Z = [0.0, 0.0, 1.0]
    if len(parts) > 1 and parts[1] not in ('$', ''):
        try:
            Z = parse_direction(idx, int(parts[1].lstrip('#')))
        except (ValueError, KeyError):
            pass

    # RefDirection (X local) — padrão [1,0,0]
    X_ref = [1.0, 0.0, 0.0]
    if len(parts) > 2 and parts[2] not in ('$', ''):
        try:
            X_ref = parse_direction(idx, int(parts[2].lstrip('#')))
        except (ValueError, KeyError):
            pass

    Z = normalize(Z)
    proj = dot(X_ref, Z)
    X = normalize([X_ref[i] - proj * Z[i] for i in range(3)])
    Y = cross(Z, X)

    return [
        X[0], Y[0], Z[0], T[0],
        X[1], Y[1], Z[1], T[1],
        X[2], Y[2], Z[2], T[2],
        0.0,  0.0,  0.0,  1.0,
    ]


# ─── Resolução recursiva de IFCLOCALPLACEMENT ────────────────────────────────

def resolve_lp(idx, lp_id, _cache=None):
    """
    Resolve IFCLOCALPLACEMENT recursivamente, acumulando toda a hierarquia.
    Retorna matriz 4×4 row-major no espaço mundial.

    BUG CRÍTICO se não implementado: peças renderizam na origem local
    em vez de no espaço mundial — motor, flanges e voluta aparecem separados.
    """
    if _cache is None:
        _cache = {}
    if lp_id in _cache:
        return _cache[lp_id]

    etype, args = idx[lp_id]
    parts = split_top(args)

    rel_placement_id = int(parts[1].lstrip('#'))
    M_rel = axis2placement_mat(idx, rel_placement_id)

    if parts[0] != '$' and parts[0] != '':
        try:
            parent_id = int(parts[0].lstrip('#'))
            M_parent = resolve_lp(idx, parent_id, _cache)
            result = mat_mul(M_parent, M_rel)
        except (ValueError, KeyError):
            result = M_rel
    else:
        result = M_rel

    _cache[lp_id] = result
    return result


# ─── Extração de IFCINDEXEDCOLOURMAP ─────────────────────────────────────────

def build_face_color_map(content, idx):
    """
    Retorna dict: face_set_id → (colours_list, colour_indices)
      colours_list   : list de [r,g,b] floats 0–1
      colour_indices : list de int 1-based (um por triângulo)

    Entidades standalone — não filhas de nenhuma outra, ligação vai do mapa
    para o face set, não o contrário.
    """
    face_color_map = {}
    for cm_id_str in re.findall(r'#(\d+)\s*=\s*IFCINDEXEDCOLOURMAP\s*\(', content):
        cm_id = int(cm_id_str)
        if cm_id not in idx:
            continue
        _, args = idx[cm_id]
        parts = split_top(args)
        if len(parts) < 4:
            continue

        try:
            face_set_id = int(parts[0].lstrip('#'))
            colour_list_id = int(parts[2].lstrip('#'))
        except ValueError:
            continue

        # ColourIndex: lista flat de ints 1-based
        colour_indices = [int(x) for x in re.findall(r'\d+', parts[3])]

        # IFCCOLOURRGBLIST: ((r1,g1,b1),(r2,g2,b2),...)
        if colour_list_id not in idx:
            continue
        _, cargs = idx[colour_list_id]
        inner = cargs.strip()
        if inner.startswith('('):
            inner = inner[1:]
        if inner.endswith(')'):
            inner = inner[:-1]

        colours = []
        for m in re.finditer(r'\(([0-9.,\s]+)\)', inner):
            vals = [float(x.strip()) for x in m.group(1).split(',') if x.strip()]
            if len(vals) >= 3:
                colours.append(vals[:3])

        if colours and colour_indices:
            face_color_map[face_set_id] = (colours, colour_indices)

    return face_color_map


# ─── Emissão de triângulos ────────────────────────────────────────────────────

def ifc_to_threejs(p):
    """Converte ponto IFC (Z-up) para Three.js (Y-up)."""
    return [p[0], p[2], -p[1]]


def emit_colored(coord_list, face_indices, lp_matrix, colours, colour_indices, pos_out, col_out):
    """Geometria com cor por face — expande cada triângulo (sem compartilhar vértices)."""
    for tri_idx, (i0, i1, i2) in enumerate(face_indices):
        if tri_idx >= len(colour_indices):
            r, g, b = 0.72, 0.75, 0.80
        else:
            c_idx = colour_indices[tri_idx] - 1
            if 0 <= c_idx < len(colours):
                r, g, b = colours[c_idx][:3]
            else:
                r, g, b = 0.72, 0.75, 0.80
        for vi in (i0, i1, i2):
            p = coord_list[vi - 1]
            v = apply_matrix(lp_matrix, p)
            pos_out += ifc_to_threejs(v)
            col_out += [r, g, b]


def emit_uniform(coord_list, face_indices, lp_matrix, default_rgb, pos_out, col_out, idx_out):
    """Geometria uniforme — compartilha vértices, usa idx para triângulos."""
    base = len(pos_out) // 3
    for p in coord_list:
        v = apply_matrix(lp_matrix, p)
        pos_out += ifc_to_threejs(v)
        col_out += default_rgb
    for i0, i1, i2 in face_indices:
        idx_out += [base + i0 - 1, base + i1 - 1, base + i2 - 1]


# ─── Parse de um arquivo IFC ──────────────────────────────────────────────────

def parse_ifc_file(ifc_path, default_rgb=None):
    """
    Lê um arquivo IFC4 e retorna geometria expandida:
      { 'pos': [...], 'col': [...] }   — sem idx (vértices repetidos por triângulo colorido)
      ou
      { 'pos': [...], 'col': [...], 'idx': [...] }  — geometria indexada (uniforme)

    Na prática retorna sem idx quando há IFCINDEXEDCOLOURMAP (cores por face),
    e com idx quando é geometria uniforme. O dedup.py padroniza tudo para indexado.
    """
    if default_rgb is None:
        default_rgb = [0.72, 0.75, 0.80]  # cinza aço

    with open(ifc_path, encoding='utf-8', errors='replace') as f:
        content = f.read()

    idx = build_entity_index(content)
    face_color_map = build_face_color_map(content, idx)

    pos_out = []
    col_out = []
    idx_out = []
    has_colors = bool(face_color_map)

    assembly_types = {'IFCELEMENTASSEMBLY', 'IFCBUILDINGELEMENTPROXY',
                      'IFCFLOWFITTING', 'IFCFLOWTERMINAL', 'IFCFLOWSEGMENT',
                      'IFCMECHANICALFASTENER', 'IFCPLATE', 'IFCBEAM',
                      'IFCCOLUMN', 'IFCMEMBER', 'IFCDISCRETEACCESSORY'}

    for eid, (etype, args) in idx.items():
        if etype not in assembly_types:
            continue
        parts = split_top(args)
        if len(parts) < 7:
            continue

        # ObjectPlacement — índice 5 (0=GlobalId,1=OwnerHistory,2=Name,3=Desc,4=ObjectType,5=ObjectPlacement,6=Representation)
        lp_str = parts[5]
        if lp_str == '$':
            continue
        try:
            lp_id = int(lp_str.lstrip('#'))
            M_lp = resolve_lp(idx, lp_id)
        except (ValueError, KeyError):
            continue

        # Representation
        rep_str = parts[6]
        if rep_str == '$':
            continue
        try:
            rep_id = int(rep_str.lstrip('#'))
        except ValueError:
            continue
        if rep_id not in idx:
            continue

        # Busca IFCTRIANGULATEDFACESET via shape representations
        _, rep_args = idx[rep_id]
        for shape_id_str in re.findall(r'#(\d+)', rep_args):
            shape_id = int(shape_id_str)
            if shape_id not in idx:
                continue
            s_etype, s_args = idx[shape_id]
            if s_etype != 'IFCSHAPEREPRESENTATION':
                continue

            # Busca IFCTRIANGULATEDFACESET direto ou via IFCMAPPEDITEM
            for item_id_str in re.findall(r'#(\d+)', s_args):
                item_id = int(item_id_str)
                if item_id not in idx:
                    continue
                i_etype, i_args = idx[item_id]

                M_final = M_lp

                if i_etype == 'IFCMAPPEDITEM':
                    # Caminho B: instância compartilhada
                    i_parts = split_top(i_args)
                    try:
                        map_src_id = int(i_parts[0].lstrip('#'))
                        map_tgt_id = int(i_parts[1].lstrip('#'))
                    except (ValueError, IndexError):
                        continue

                    # MappingTarget (transform adicional)
                    if map_tgt_id in idx:
                        tgt_etype, tgt_args = idx[map_tgt_id]
                        if tgt_etype == 'IFCCARTESIANTRANSFORMATIONOPERATOR3D':
                            tgt_parts = split_top(tgt_args)
                            try:
                                origin_id = int(tgt_parts[3].lstrip('#'))
                                M_tgt = axis2placement_mat(idx, origin_id)
                                M_final = mat_mul(M_lp, M_tgt)
                            except (ValueError, IndexError, KeyError):
                                pass

                    if map_src_id not in idx:
                        continue
                    _, src_args = idx[map_src_id]
                    for fs_id_str in re.findall(r'#(\d+)', src_args):
                        fs_id = int(fs_id_str)
                        if fs_id in idx and idx[fs_id][0] == 'IFCTRIANGULATEDFACESET':
                            _process_faceset(fs_id, idx, M_final, face_color_map,
                                             default_rgb, pos_out, col_out, idx_out)
                elif i_etype == 'IFCTRIANGULATEDFACESET':
                    _process_faceset(item_id, idx, M_final, face_color_map,
                                     default_rgb, pos_out, col_out, idx_out)

    if not pos_out:
        # Nenhum IFCTRIANGULATEDFACESET no arquivo — exportador não-tessellated
        # (ex: Revit gera IFCFACETEDBREP/IFCADVANCEDBREP). Cai para ifcopenshell,
        # que tesseliza qualquer representação sólida via OpenCascade.
        return _parse_via_ifcopenshell(ifc_path, default_rgb)

    result = {'pos': pos_out, 'col': col_out}
    if idx_out:
        result['idx'] = idx_out
    return result


def _parse_via_ifcopenshell(ifc_path, default_rgb):
    """
    Fallback para IFCs cuja geometria não é IFCTRIANGULATEDFACESET (ex: sólidos
    BRep/Revit — IFCFACETEDBREP, IFCADVANCEDBREP, swept solids). ifcopenshell
    tesseliza qualquer representação via OpenCascade e já devolve coordenadas
    em metros e em coordenadas de mundo (USE_WORLD_COORDS), sem precisar
    resolver IFCLOCALPLACEMENT manualmente.

    Retorna geometria expandida (sem idx) — cor por triângulo via material.
    """
    try:
        import ifcopenshell
        import ifcopenshell.geom
    except ImportError as e:
        raise RuntimeError(
            'ifcopenshell não instalado — necessário para IFCs em formato BRep '
            '(sem IFCTRIANGULATEDFACESET). Rode: pip install -r requirements.txt'
        ) from e

    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    ifc_file = ifcopenshell.open(ifc_path)
    pos_out = []
    col_out = []

    for product in ifc_file.by_type('IFCPRODUCT'):
        if not getattr(product, 'Representation', None):
            continue
        # Só elementos físicos/tangíveis — sem isso, IFCOPENINGELEMENT (vazios
        # de furos/recortes) e IFCSPACE (volumes de ambiente) também têm
        # Representation sólida válida e virariam geometria fantasma visível.
        # IfcElement cobre proxies, tubulações, fixadores etc. (equivalente ao
        # allow-list do parser manual, mas por herança de schema — o nome de
        # tipo folha do ifcopenshell nem sempre bate com o allow-list manual,
        # ex: IfcPipeFitting não é string-igual a IFCFLOWFITTING mas É um por
        # herança). IfcFeatureElement é o ramo dos vazios (subtração/adição) —
        # excluir explicitamente mesmo sendo IfcElement. IfcVirtualElement é
        # subtype de IfcElement (não de IfcFeatureElement) — representa limites
        # de espaço/porta aberta como superfície planar — também deve ser excluído.
        if (not product.is_a('IfcElement')
                or product.is_a('IfcFeatureElement')
                or product.is_a('IfcVirtualElement')):
            continue
        try:
            shape = ifcopenshell.geom.create_shape(settings, product)
        except Exception:
            continue

        try:
            geom = shape.geometry
            verts = geom.verts
            faces = geom.faces
            materials = geom.materials
            material_ids = geom.material_ids

            mat_colors = []
            for m in materials:
                c = getattr(m, 'diffuse', None)
                mat_colors.append([c.r(), c.g(), c.b()] if c else default_rgb)

            n_tris = len(faces) // 3
            for t in range(n_tris):
                mi = material_ids[t] if t < len(material_ids) else -1
                rgb = mat_colors[mi] if 0 <= mi < len(mat_colors) else default_rgb
                for k in range(3):
                    vi = faces[t * 3 + k]
                    x, y, z = verts[vi * 3], verts[vi * 3 + 1], verts[vi * 3 + 2]
                    pos_out += [x, z, -y]  # IFC Z-up → Three.js Y-up
                    col_out += rgb
        except Exception:
            continue

    return {'pos': pos_out, 'col': col_out}


def _process_faceset(fs_id, idx, M, face_color_map, default_rgb, pos_out, col_out, idx_out):
    """Processa um IFCTRIANGULATEDFACESET e acumula nos buffers de saída."""
    _, fs_args = idx[fs_id]
    fs_parts = split_top(fs_args)
    # IFC4 IFCTRIANGULATEDFACESET: [0]=Coordinates, [1]=Normals, [2]=Closed, [3]=CoordIndex, [4]=PnIndex
    if len(fs_parts) < 4:
        return

    try:
        coords_id = int(fs_parts[0].lstrip('#'))
    except ValueError:
        return
    if coords_id not in idx:
        return

    # Coordenadas: IFCCARTESIANPOINTLIST3D(((x,y,z),(x,y,z),...))
    _, coords_args = idx[coords_id]
    coord_list = []
    for m in re.finditer(r'\(([^()]+)\)', coords_args):
        vals = parse_floats(m.group(1))
        if len(vals) >= 3:
            coord_list.append(vals[:3])

    if not coord_list:
        return

    # Índices dos triângulos: CoordIndex em parts[3] (parts[1]=Normals, parts[2]=Closed)
    face_indices = []
    coord_index_str = fs_parts[3]
    for m in re.finditer(r'\(([^()]+)\)', coord_index_str):
        vals = parse_ints(m.group(1))
        if len(vals) >= 3:
            face_indices.append(tuple(vals[:3]))

    if not face_indices:
        return

    if fs_id in face_color_map:
        colours, colour_indices = face_color_map[fs_id]
        emit_colored(coord_list, face_indices, M, colours, colour_indices, pos_out, col_out)
    else:
        emit_uniform(coord_list, face_indices, M, default_rgb, pos_out, col_out, idx_out)


# ─── CLI standalone ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Parse IFC4 → JSON de geometria')
    parser.add_argument('ifc_file', help='Arquivo .IFC de entrada')
    parser.add_argument('output_dir', help='Diretório de saída')
    parser.add_argument('--slug', help='Nome do arquivo de saída (sem .json)', default=None)
    args = parser.parse_args()

    slug = args.slug or os.path.splitext(os.path.basename(args.ifc_file))[0].lower().replace(' ', '-')
    out_path = os.path.join(args.output_dir, slug + '_raw.json')

    print(f'Parsing: {args.ifc_file}')
    data = parse_ifc_file(args.ifc_file)
    n_verts = len(data['pos']) // 3
    n_tris = len(data.get('idx', data['pos'])) // (1 if 'idx' not in data else 3)
    print(f'  → {n_verts} vértices, arquivo: {out_path}')

    os.makedirs(args.output_dir, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(data, f, separators=(',', ':'))


if __name__ == '__main__':
    main()
