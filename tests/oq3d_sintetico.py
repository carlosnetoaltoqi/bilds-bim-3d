"""Blobs OQ3D sintéticos e mutações controladas, para testar o parser sem .aq."""
import struct

import oq3d
import oq3d_writer  # eng-reversa/tools — o writer que gerou o .aq da Akato

# Um triângulo em centímetros, Z-up. Valores distintos por eixo para o teste
# de conversão (x, y, z) → (x, z, -y) × 0,01 não passar por coincidência.
VERTS_CM = [(10.0, 20.0, 30.0), (40.0, 50.0, 60.0), (70.0, 80.0, 90.0)]
TRIS = [(0, 1, 2)]
RGBA = (255, 0, 0, 255)

MESH = b'TQi3DIndexedTriangleMeshData'


def triangulo(xform=None):
    return oq3d_writer.escrever([(VERTS_CM, TRIS, RGBA, xform)])


def duas_malhas():
    return oq3d_writer.escrever([
        (VERTS_CM, TRIS, RGBA, None),
        ([(1.0, 2.0, 3.0), (4.0, 5.0, 6.0), (7.0, 8.0, 9.0)], TRIS, (0, 0, 255, 255), None),
    ])


def esperado_triangulo():
    pos = []
    for x, y, z in VERTS_CM:
        pos += [x * 0.01, z * 0.01, -y * 0.01]
    return {'pos': pos, 'col': [1.0, 0.0, 0.0] * 3, 'idx': [0, 1, 2]}


def offset_malha(blob, n=0):
    """Offset do payload (u32 versão) do n-ésimo TQi3DIndexedTriangleMeshData."""
    p = -1
    for _ in range(n + 1):
        p = blob.index(MESH, p + 1)
    return p + len(MESH)


def com_versao_malha(blob, versao, n=0):
    off = offset_malha(blob, n)
    return blob[:off] + struct.pack('<I', versao) + blob[off + 4:]


def com_n_coord(blob, n_coord, n=0):
    off = offset_malha(blob, n) + 4
    return blob[:off] + struct.pack('<I', n_coord) + blob[off + 4:]


def com_n_idx(blob, n_idx, n=0):
    off = offset_malha(blob, n)
    n_coord = struct.unpack_from('<I', blob, off + 4)[0]
    idx_off = off + 12 + n_coord * 8
    return blob[:idx_off] + struct.pack('<I', n_idx) + blob[idx_off + 4:]


def truncado_nas_coords(blob, n=0):
    """Corta o blob no meio dos doubles da malha."""
    off = offset_malha(blob, n)
    return blob[:off + 12 + 8]


def com_raizes_declaradas(blob, n_raizes):
    pos = blob.index(oq3d.MAGIC) + len(oq3d.MAGIC) + 4
    return blob[:pos] + struct.pack('<I', n_raizes) + blob[pos + 4:]
