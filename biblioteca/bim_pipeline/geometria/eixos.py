"""
eixos.py — as conversões entre os sistemas de coordenadas que a biblioteca cruza.

O viewer (e o contrato `{pos, col, idx}`) é **metros, Y-up**. As fontes são todas **Z-up**:
OQ3D em centímetros, STEP/IGES em milímetros (após a leitura pelo OpenCASCADE), IFC em metros.
A regra é uma só, em ambos os sentidos:

    Z-up → viewer   (x, y, z) → (x, z, −y) · escala
    viewer → Z-up   (x, y, z) → (x, −z, y) · escala

Toda função aqui é a mesma coisa em três formas — escalar, lista plana, numpy — para que os
leitores (oq3d, step_iges, ifc/parse_ifc) e os escritores (geo_to_aq, catalogo_to_aq) não
repitam a permutação cada um do seu jeito (era a duplicação D10 da S8).
"""
import numpy as np

CM_TO_M = 0.01
MM_TO_M = 0.001
M_TO_CM = 100.0


def zup_para_viewer(x, y, z, escala=1.0):
    """Um ponto Z-up → Y-up do viewer."""
    return (x * escala, z * escala, -y * escala)


def viewer_para_zup(x, y, z, escala=1.0):
    """Um ponto do viewer → Z-up."""
    return (x * escala, -z * escala, y * escala)


def zup_para_viewer_np(pts, escala=1.0):
    """(N, 3) Z-up → (N, 3) Y-up, já escalado."""
    pts = np.asarray(pts, dtype=float)
    return np.column_stack([pts[:, 0], pts[:, 2], -pts[:, 1]]) * escala


def viewer_para_zup_np(pts, escala=1.0):
    """(N, 3) Y-up do viewer → (N, 3) Z-up, já escalado."""
    pts = np.asarray(pts, dtype=float)
    return np.column_stack([pts[:, 0], -pts[:, 2], pts[:, 1]]) * escala


def plano_zup_para_viewer(plano, escala=1.0, casas=None):
    """Lista plana [x, y, z, x, y, z, …] Z-up → lista plana Y-up. `casas` arredonda (o STEP usa 7)."""
    out = [0.0] * len(plano)
    for i in range(0, len(plano), 3):
        x, y, z = zup_para_viewer(plano[i], plano[i + 1], plano[i + 2], escala)
        if casas is not None:
            x, y, z = round(x, casas), round(y, casas), round(z, casas)
        out[i], out[i + 1], out[i + 2] = x, y, z
    return out


def viewer_para_oq3d(pos, idx):
    """
    `pos` plano (metros, Y-up) + `idx` plano → `(verts_cm, tris)` como o `oq3d_writer` quer:
    lista de tuplas em centímetros Z-up e lista de tuplas de índices.
    """
    verts = [viewer_para_zup(pos[i], pos[i + 1], pos[i + 2], M_TO_CM) for i in range(0, len(pos), 3)]
    tris = [(idx[t], idx[t + 1], idx[t + 2]) for t in range(0, len(idx), 3)]
    return verts, tris
