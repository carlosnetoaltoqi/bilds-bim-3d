#!/usr/bin/env python3
"""
oq3d.py — Lê o formato binário OQ3D ("OQ3D 3D Objects File"), a geometria 3D
que o AltoQi Builder guarda dentro do .aq, no BLOB SIMBOLOGIA_3D.SIMBOLOGIA_3D.

É o mesmo sólido que o AltoQi exporta como IFC: em bibliotecas tessellated os
triângulos batem exatamente; em bibliotecas B-rep (IFCADVANCEDBREP) a forma
converge mas a tesselação é independente.

FORMATO
-------
Assinatura: 5 bytes + b'OQ3D 3D Objects File'.

Árvore de objetos serializados no estilo Delphi:

    0x5B <len:u32> <ClassName>   abre um objeto
    ...payload...
    0x5D                         fecha

O byte que precede o 0x5B varia conforme o contexto — não pode entrar no padrão
de busca. E 0x5B/0x5D ocorrem naturalmente dentro de doubles, então os blocos de
tamanho conhecido têm de ser consumidos por inteiro antes de qualquer varredura.

Classes que carregam dados:

    TQi3DIndexedTriangleMeshData
        u32 versao(=2) | u32 nCoords | u32 reservado
        nCoords doubles                    -> nCoords/3 vértices (x,y,z)
        u32 nIdx | u32 reservado
        nIdx u32                           -> nIdx/3 triângulos
    TCoatingColor
        u32 versao | u32 flag | u8 R | u8 G | u8 B | u8 A   (cor uniforme da malha)
    TCoordinateTransformation3D
        u32 versao | 12 doubles            -> rotação 3x3 row-major + translação

Hierarquia:

    TQi3DReusedObject(guid)          instância
      TQi3DReusableObject              definição inline (opcional)
        TQi3DTriangleMesh
          TCoatingColor
          TQi3DIndexedTriangleMeshData
      TCoordinateTransformation3D      origem — quase sempre identidade
      TCoordinateTransformation3D      alvo  — posiciona a instância

O último TCoordinateTransformation3D filho direto é o que posiciona; o par
origem/alvo espelha MappingOrigin/MappingTarget do IFC.

UNIDADES: centímetros, Z-up (a mesma orientação do IFC nativo).
Para o viewer: x, y=z, z=-y e multiplicar por 0.01.

ARMADILHAS
----------
- Ignorar os transforms funciona em bibliotecas de equipamentos (as malhas já
  vêm em coordenadas de mundo) e QUEBRA em bibliotecas de conexões, onde a peça
  é montada a partir de malhas reaproveitadas. Use sempre o parser de árvore.
- As cores verde/azul de bocal são marcadores de conexão do AltoQi, não parte do
  produto: inflam a bounding box. Use MARKER_COLORS para separá-los.
"""
import re
import struct

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

MAGIC = b'OQ3D 3D Objects File'
CM_TO_M = 0.01

OPEN, CLOSE = 0x5B, 0x5D

CLASSES = {
    'TQi3DReusedObject', 'TQi3DReusableObject', 'TQi3DObjectGroup',
    'TQi3DTriangleMesh', 'TCoatingColor', 'TQi3DIndexedTriangleMeshData',
    'TCoordinateTransformation3D',
}

# Marcadores de ponto de conexão (macho/fêmea) que o AltoQi desenha nas bocas.
MARKER_COLORS = {(1, 154, 63), (10, 84, 152), (0, 116, 232)}

DEFAULT_RGBA = (150, 150, 150, 255)


class OQ3DError(ValueError):
    """Blob que não é OQ3D ou cujo layout binário não é o esperado."""


class Node:
    __slots__ = ('cls', 'children', 'mesh', 'color', 'xform', 'guid')

    def __init__(self, cls):
        self.cls = cls
        self.children = []
        self.mesh = None
        self.color = None
        self.xform = None
        self.guid = None

    def __repr__(self):
        return f'<{self.cls} kids={len(self.children)}>'


def is_oq3d(buf):
    """True se o blob tem a assinatura OQ3D."""
    return isinstance(buf, (bytes, bytearray)) and MAGIC in buf[:64]


def _class_at(buf, p):
    """(nome, offset_do_payload) se há marcador de classe em p, senão None."""
    if p + 5 > len(buf):
        return None
    length = struct.unpack_from('<I', buf, p + 1)[0]
    if not (3 <= length <= 60) or p + 5 + length > len(buf):
        return None
    try:
        name = buf[p + 5:p + 5 + length].decode('ascii')
    except UnicodeDecodeError:
        return None
    return (name, p + 5 + length) if name in CLASSES else None


def parse(buf):
    """Devolve a lista de nós-raiz da árvore de objetos."""
    if not is_oq3d(buf):
        raise OQ3DError('blob sem assinatura OQ3D')

    roots, stack = [], []
    p, n = 0, len(buf)

    while p < n:
        byte = buf[p]

        if byte == OPEN:
            hit = _class_at(buf, p)
            if hit is None:
                p += 1
                continue
            name, off = hit
            node = Node(name)
            (stack[-1].children if stack else roots).append(node)
            stack.append(node)

            if name == 'TCoatingColor':
                node.color = struct.unpack_from('<4B', buf, off + 8)
                p = off + 12
            elif name == 'TCoordinateTransformation3D':
                m = struct.unpack_from('<12d', buf, off + 4)
                node.xform = (m[:9], m[9:12])
                p = off + 100
            elif name == 'TQi3DIndexedTriangleMeshData':
                p = _read_mesh(buf, off, node, n)
            else:
                if name == 'TQi3DReusedObject':
                    try:
                        if struct.unpack_from('<I', buf, off + 28)[0] == 36:
                            node.guid = buf[off + 32:off + 68].decode('ascii', 'replace')
                    except struct.error:
                        pass
                p = off
            continue

        if byte == CLOSE:
            if stack:
                stack.pop()
            p += 1
            continue

        p += 1

    return roots


def _read_mesh(buf, off, node, n):
    """Preenche node.mesh e devolve a posição logo após o bloco."""
    try:
        ver, n_coord, _ = struct.unpack_from('<3I', buf, off)
    except struct.error:
        return off
    if ver != 2 or not n_coord or n_coord % 3:
        return off
    idx_off = off + 12 + n_coord * 8
    if idx_off + 8 > n:
        return off
    n_idx = struct.unpack_from('<I', buf, idx_off)[0]
    end = idx_off + 8 + n_idx * 4
    if n_idx % 3 or end > n:
        return off

    if HAS_NUMPY:
        verts = np.frombuffer(buf, '<f8', n_coord, off + 12).reshape(-1, 3)
        tris = np.frombuffer(buf, '<u4', n_idx, idx_off + 8).reshape(-1, 3)
    else:
        flat = struct.unpack_from('<%dd' % n_coord, buf, off + 12)
        verts = [list(flat[i:i + 3]) for i in range(0, n_coord, 3)]
        fi = struct.unpack_from('<%dI' % n_idx, buf, idx_off + 8)
        tris = [list(fi[i:i + 3]) for i in range(0, n_idx, 3)]
    node.mesh = (verts, tris)
    return end


def _mat_mul(a, b):
    """Produto de duas matrizes 3x3 achatadas (row-major)."""
    return tuple(
        sum(a[r * 3 + k] * b[k * 3 + c] for k in range(3))
        for r in range(3) for c in range(3)
    )


def _apply(rot, trans, v):
    return [
        rot[0] * v[0] + rot[1] * v[1] + rot[2] * v[2] + trans[0],
        rot[3] * v[0] + rot[4] * v[1] + rot[5] * v[2] + trans[1],
        rot[6] * v[0] + rot[7] * v[1] + rot[8] * v[2] + trans[2],
    ]


def _collect(nodes, rot, trans, color, out):
    for nd in nodes:
        own = None
        col = color
        for ch in nd.children:
            if ch.cls == 'TCoordinateTransformation3D' and ch.xform is not None:
                own = ch.xform          # o último filho vence
            elif ch.cls == 'TCoatingColor' and ch.color is not None:
                col = ch.color

        if own is None:
            rot2, trans2 = rot, trans
        elif rot is None:
            rot2, trans2 = own
        else:
            rot2 = _mat_mul(rot, own[0])
            t = _apply(rot, trans, own[1])
            rot2, trans2 = rot2, tuple(t)

        if nd.mesh is not None:
            verts, tris = nd.mesh
            if rot2 is None:
                world = verts
            elif HAS_NUMPY:
                R = np.array(rot2).reshape(3, 3)
                world = verts @ R.T + np.array(trans2)
            else:
                world = [_apply(rot2, trans2, v) for v in verts]
            out.append((world, tris, col or DEFAULT_RGBA))

        _collect(nd.children, rot2, trans2, col, out)
    return out


def extract(buf, skip_markers=False):
    """
    [(verts, tris, rgba)] em centímetros, Z-up, já com os transforms aplicados.

    skip_markers=True descarta os bocais de conexão (verde/azul), úteis de
    remover quando se quer a bounding box real do produto.
    """
    meshes = _collect(parse(buf), None, None, None, [])
    if skip_markers:
        body = [m for m in meshes if tuple(m[2][:3]) not in MARKER_COLORS]
        return body or meshes
    return meshes


def to_buffers(buf, scale=CM_TO_M, skip_markers=False):
    """
    Geometria indexada em metros e Y-up — mesmo contrato de parse_ifc.py:
      { 'pos': [...], 'col': [...], 'idx': [...] }
    """
    pos, col, idx = [], [], []
    base = 0
    for verts, tris, rgba in extract(buf, skip_markers=skip_markers):
        rgb = [c / 255.0 for c in rgba[:3]]
        if HAS_NUMPY:
            world = np.column_stack([verts[:, 0], verts[:, 2], -verts[:, 1]]) * scale
            pos.extend(world.ravel().tolist())
            col.extend(np.tile(rgb, (len(world), 1)).ravel().tolist())
            idx.extend((np.asarray(tris) + base).ravel().tolist())
            base += len(world)
        else:
            for v in verts:
                pos.extend([v[0] * scale, v[2] * scale, -v[1] * scale])
                col.extend(rgb)
            for t in tris:
                idx.extend([t[0] + base, t[1] + base, t[2] + base])
            base += len(verts)
    return {'pos': pos, 'col': col, 'idx': idx}


def bbox(buf, skip_markers=True):
    """(dx, dy, dz) em centímetros — para diagnóstico e validação."""
    meshes = extract(buf, skip_markers=skip_markers)
    if not meshes:
        return (0.0, 0.0, 0.0)
    if HAS_NUMPY:
        pts = np.concatenate([m[0] for m in meshes])
        return tuple((pts.max(0) - pts.min(0)).round(3).tolist())
    lo = [float('inf')] * 3
    hi = [float('-inf')] * 3
    for verts, _, _ in meshes:
        for v in verts:
            for i in range(3):
                lo[i] = min(lo[i], v[i])
                hi[i] = max(hi[i], v[i])
    return tuple(round(hi[i] - lo[i], 3) for i in range(3))


def stats(buf):
    """Resumo para logs: n_malhas, n_vertices, n_triangulos, cores."""
    meshes = extract(buf)
    n_v = sum(len(m[0]) for m in meshes)
    n_t = sum(len(m[1]) for m in meshes)
    cores = {tuple(m[2][:3]) for m in meshes}
    return {'malhas': len(meshes), 'vertices': n_v, 'triangulos': n_t,
            'cores': sorted(cores), 'bbox_cm': bbox(buf)}
