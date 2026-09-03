#!/usr/bin/env python3
"""
ifc_to_geo.py — um IFC vira o JSON de geometria do viewer, no mesmo contrato do
`step_to_geo.py`: `{ pos, col, idx, partes, unidade, bbox_mm, fonte }`, metros,
Y-up, indexado e deduplicado. É a porta de entrada de IFC no editor 3D da POC
(`POST /cad/importar`), ao lado do STEP.

Não reimplementa nada: a geometria vem do `parse_ifc.py` do projeto — o parser
STEP/IFC4 validado nas bibliotecas da Dancor (tessellated) e da Amanco (B-rep via
`ifcopenshell`), com LocalPlacement, MappedItem, cores por face
(`IFCINDEXEDCOLOURMAP`) e a troca de eixos Z-up → Y-up. Aqui só se acrescenta:

- **dedup** com a quantização float32 do pipeline (`dedup.py`) — o `parse_ifc`
  devolve vértices expandidos quando há cor por face;
- **unidade**: o `parse_ifc` não converte unidade (a skill `leitor-ifc` manda
  verificar a magnitude, porque o CATIA declara MILLIMETRE e escreve metros).
  Regra aqui: se o arquivo declara `.MILLI.` E a bbox bruta passa de 50 (ou
  seja, uma peça de "50 m"), os valores estão de fato em milímetros e são
  divididos por 1000; caso contrário ficam como estão. O que foi feito vai em
  `escala_aplicada`;
- **partes**: nome dos `IfcProduct` com representação (via `ifcopenshell` quando
  instalado; senão, por regex nas entidades de elemento), só para o editor
  mostrar de onde veio — a divisão em partes é feita por componentes conexos,
  como sempre.

DOIS CAMINHOS. O `parse_ifc.py` é exato para biblioteca de peça (tessellated,
com `IFCINDEXEDCOLOURMAP`), mas indexa o arquivo inteiro por regex em Python: num
IFC de projeto (Revit, 130 MB, 2,5 milhões de entidades, B-rep facetado com
700 mil faces) isso leva minutos e gigabytes. Por isso:

    arquivo <= LIMIAR_MB (20) e com IFCTRIANGULATEDFACESET  → parse_ifc.py (exato)
    caso contrário                                            → ifcopenshell.geom.iterator
                                                                (C++, multithread, cor por
                                                                material) + dedup em numpy

O caminho rápido também é o fallback quando o `parse_ifc` não acha geometria.
`--max-triangulos` não corta a malha — só avisa no JSON (`aviso`), para a interface
mostrar que o modelo é pesado para o editor no browser.

Uso:
    python3 scripts/ifc_to_geo.py peca.ifc saida.json [--forcar-rapido] [--max-triangulos 2000000]
    python3 scripts/ifc_to_geo.py peca.ifc --info
"""
import argparse
import json
import os
import re
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import parse_ifc            # noqa: E402  o parser do projeto, intocado
from dedup import dedup     # noqa: E402

LIMIAR_MB = 20
COR_PADRAO = (0.533, 0.588, 0.667)

ELEMENTOS = ('IFCBUILDINGELEMENTPROXY', 'IFCELEMENTASSEMBLY', 'IFCFLOWFITTING', 'IFCFLOWTERMINAL',
             'IFCFLOWSEGMENT', 'IFCMECHANICALFASTENER', 'IFCPLATE', 'IFCBEAM', 'IFCCOLUMN',
             'IFCMEMBER', 'IFCDISCRETEACCESSORY')


def unidade_declarada(conteudo):
    m = re.search(r'IFCSIUNIT\s*\(\s*\*\s*,\s*\.LENGTHUNIT\.\s*,\s*(\$|\.[A-Z]+\.)\s*,\s*\.([A-Z_]+)\.', conteudo)
    if not m:
        return 'desconhecida'
    prefixo = '' if m.group(1) == '$' else m.group(1).strip('.')
    return f'{prefixo}{m.group(2)}'.replace('MILLIMETRE', 'MILLIMETRE').replace('METRE', 'METRE')


def nomes_das_partes(caminho, conteudo):
    try:
        import ifcopenshell
        f = ifcopenshell.open(caminho)
        nomes = []
        for p in f.by_type('IfcProduct'):
            if getattr(p, 'Representation', None):
                nomes.append({'nome': p.Name or p.is_a(), 'tipo': p.is_a()})
        if nomes:
            return nomes
    except Exception:
        pass
    nomes = []
    for m in re.finditer(r"=\s*(" + '|'.join(ELEMENTOS) + r")\s*\(\s*'[^']*'\s*,\s*(?:#\d+|\$)\s*,\s*('([^']*)'|\$)", conteudo):
        nomes.append({'nome': m.group(3) or m.group(1), 'tipo': m.group(1)})
    return nomes


def cabecalho(caminho, n=64 * 1024):
    """Só o começo do arquivo: unidade e presença de face set tessellated ficam nos primeiros KB… mas
    o IFCTRIANGULATEDFACESET pode estar em qualquer lugar — em arquivo grande, procura por streaming."""
    with open(caminho, encoding='utf-8', errors='replace') as f:
        return f.read(n)


def tem_faceset_tessellated(caminho):
    with open(caminho, 'rb') as f:
        while True:
            bloco = f.read(8 * 1024 * 1024)
            if not bloco:
                return False
            if b'IFCTRIANGULATEDFACESET' in bloco:
                return True


def _rgb_do_material(m):
    """A API do estilo mudou entre versões do ifcopenshell: `diffuse` é objeto (r,g,b) ou tupla."""
    d = getattr(m, 'diffuse', None)
    if d is None:
        return COR_PADRAO
    try:
        if hasattr(d, 'r'):
            # no ifcopenshell 0.8 `r/g/b` são MÉTODOS; em versões antigas, atributos
            comp = lambda v: float(v() if callable(v) else v)
            rgb = (comp(d.r), comp(d.g), comp(d.b))
        else:
            rgb = tuple(float(v) for v in list(d)[:3])
    except Exception:
        return COR_PADRAO
    if len(rgb) != 3 or any(v < 0 or v > 1 for v in rgb):
        return COR_PADRAO
    return rgb


def rapido_ifcopenshell(caminho, log=print):
    """
    Caminho rápido: `ifcopenshell.geom.iterator` tessela TODO IfcProduct com representação
    (paredes, lajes, B-rep facetado, mapped items…) em C++ com todas as CPUs e
    `USE_WORLD_COORDS`. Cor por triângulo vem dos materiais (IfcSurfaceStyle); o
    `IFCINDEXEDCOLOURMAP` não é lido aqui — para isso existe o caminho exato.
    Devolve (pos_m_yup, col, partes) já deduplicado via numpy.
    """
    import multiprocessing
    import numpy as np
    import ifcopenshell
    import ifcopenshell.geom

    t = time.time()
    f = ifcopenshell.open(caminho)
    log(f'  ifcopenshell.open: {time.time() - t:.1f}s, {len(f.by_type("IfcProduct"))} IfcProduct')
    s = ifcopenshell.geom.settings()
    s.set(s.USE_WORLD_COORDS, True)
    it = ifcopenshell.geom.iterator(s, f, multiprocessing.cpu_count())
    blocos_pos, blocos_col, partes = [], [], []
    n_tri = 0
    if it.initialize():
        while True:
            sh = it.get()
            g = sh.geometry
            verts = np.asarray(g.verts, dtype=np.float64).reshape(-1, 3)
            faces = np.asarray(g.faces, dtype=np.int64).reshape(-1, 3)
            if len(faces):
                tri = verts[faces].reshape(-1, 3)              # expandido: 3 vértices por triângulo
                mats = list(getattr(g, 'materials', []))
                mids = np.asarray(getattr(g, 'material_ids', []), dtype=np.int64)
                cores = np.tile(np.asarray(COR_PADRAO, dtype=np.float64), (len(faces), 1))
                if mats and len(mids) == len(faces):
                    paleta = np.asarray([_rgb_do_material(m) for m in mats], dtype=np.float64)
                    ok = (mids >= 0) & (mids < len(paleta))
                    cores[ok] = paleta[mids[ok]]
                blocos_pos.append(tri)
                blocos_col.append(np.repeat(cores, 3, axis=0))
                n_tri += len(faces)
                partes.append({'nome': sh.name or sh.type, 'tipo': sh.type, 'triangulos': int(len(faces))})
                if len(partes) % 500 == 0:
                    log(f'  {len(partes)} formas, {n_tri:,} triângulos, {time.time() - t:.0f}s')
            if not it.next():
                break
    if not blocos_pos:
        raise SystemExit(f'{caminho}: ifcopenshell não gerou geometria')

    pos = np.concatenate(blocos_pos)                 # (N, 3) em metros, Z-up — USE_WORLD_COORDS
    col = np.concatenate(blocos_col)
    # Z-up → Y-up: (x, y, z) → (x, z, −y)
    pos = np.stack([pos[:, 0], pos[:, 2], -pos[:, 1]], axis=1)
    # dedup com quantização float32 em (pos, cor) — a mesma chave do pipeline, vetorizada
    chave = np.concatenate([pos.astype(np.float32), col.astype(np.float32)], axis=1)
    _, primeiro, inverso = np.unique(chave.view([('', chave.dtype)] * chave.shape[1]), return_index=True, return_inverse=True)
    geo = {
        'pos': np.round(pos[primeiro], 7).ravel().tolist(),
        'col': np.round(col[primeiro], 4).ravel().tolist(),
        'idx': inverso.ravel().astype(int).tolist(),
    }
    log(f'  rápido: {len(partes)} formas, {n_tri:,} triângulos, {len(primeiro):,} vértices únicos em {time.time() - t:.1f}s')
    return geo, partes


def converter(caminho, forcar_rapido=False, max_triangulos=2_000_000, log=print):
    t0 = time.time()
    tamanho_mb = os.path.getsize(caminho) / 1024 / 1024
    conteudo = cabecalho(caminho)
    unidade = unidade_declarada(conteudo)
    grande = tamanho_mb > LIMIAR_MB
    exato = not forcar_rapido and not grande and tem_faceset_tessellated(caminho)

    partes = None
    bruto = None
    if exato:
        bruto = parse_ifc.parse_ifc_file(caminho)
        if not bruto.get('pos'):
            log('  parse_ifc.py não extraiu geometria — caindo para o ifcopenshell')
            bruto = None
    if bruto is not None:
        caminho_usado = 'parse_ifc'
        geo, _n, _nd, _pct = dedup({'pos': bruto['pos'], 'col': bruto.get('col', []), **({'idx': bruto['idx']} if 'idx' in bruto else {})})
    else:
        caminho_usado = 'ifcopenshell'
        try:
            geo, partes = rapido_ifcopenshell(caminho, log)
        except ImportError:
            raise SystemExit(f'{caminho}: arquivo {"grande" if grande else "sem IFCTRIANGULATEDFACESET"} exige ifcopenshell (pip install ifcopenshell)')
        bruto = {'idx': geo['idx']}   # o rápido já vem indexado; a cor é por triângulo (materiais)

    # unidade: o parser não escala; decide pela declaração E pela magnitude
    pos = geo['pos']
    xs, ys, zs = pos[0::3], pos[1::3], pos[2::3]
    bruto_bbox = [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)]
    escala = 1.0
    if unidade.startswith('MILLI') and max(bruto_bbox) > 50:
        escala = 0.001
    elif unidade.startswith('CENTI') and max(bruto_bbox) > 50:
        escala = 0.01
    if escala != 1.0:
        geo['pos'] = [round(v * escala, 7) for v in pos]
    else:
        geo['pos'] = [round(v, 7) for v in pos]

    bb = [round(d * escala * 1000, 3) for d in bruto_bbox]
    if partes is None:
        with open(caminho, encoding='utf-8', errors='replace') as f:
            partes = nomes_das_partes(caminho, f.read())
    n_tri = len(geo['idx']) // 3
    geo.update({
        'partes': partes,
        'unidade': unidade,
        'escala_aplicada': escala,
        'bbox_mm': bb,
        'fonte': os.path.basename(caminho),
        'cor_por_face': caminho_usado == 'ifcopenshell' or 'idx' not in bruto,
        'caminho': caminho_usado,
        'tamanho_mb': round(tamanho_mb, 1),
        'segundos': round(time.time() - t0, 2),
    })
    if n_tri > max_triangulos:
        geo['aviso'] = (f'{n_tri:,} triângulos — acima de {max_triangulos:,}; o editor no browser vai ficar lento. '
                        f'Considere simplificar o modelo na origem.').replace(',', '.')
    return geo


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('entrada')
    ap.add_argument('saida', nargs='?')
    ap.add_argument('--info', action='store_true')
    ap.add_argument('--forcar-rapido', action='store_true', help='usa o ifcopenshell mesmo em arquivo pequeno')
    ap.add_argument('--max-triangulos', type=int, default=2_000_000)
    args = ap.parse_args()

    geo = converter(args.entrada, args.forcar_rapido, args.max_triangulos, log=lambda m: print(m, file=sys.stderr, flush=True))
    fmt = lambda n: f'{n:,}'.replace(',', '.')
    nv, nt = len(geo['pos']) // 3, len(geo['idx']) // 3
    bb = geo['bbox_mm']
    print(f"{geo['fonte']} ({geo['tamanho_mb']} MB, via {geo['caminho']}): unidade {geo['unidade']} (escala {geo['escala_aplicada']}), "
          f"{len(geo['partes'])} produto(s), {fmt(nv)} vértices, {fmt(nt)} triângulos, bbox {bb[0]:.1f}×{bb[1]:.1f}×{bb[2]:.1f} mm, "
          f"{'cor por face' if geo['cor_por_face'] else 'cor uniforme'}, {geo['segundos']} s")
    if geo.get('aviso'):
        print('  AVISO:', geo['aviso'])
    for p in geo['partes'][:12]:
        print(f"  {p['tipo']}: {p['nome']}")
    if len(geo['partes']) > 12:
        print(f'  … +{len(geo["partes"]) - 12}')
    if args.info or not args.saida:
        return
    with open(args.saida, 'w', encoding='utf-8') as f:
        json.dump(geo, f, separators=(',', ':'))
    print(f'  → {args.saida} ({os.path.getsize(args.saida) / 1024:.0f} KB)')


if __name__ == '__main__':
    main()
