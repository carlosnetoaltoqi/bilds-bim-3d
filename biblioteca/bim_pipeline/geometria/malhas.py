"""
malhas.py — de `{pos, col, idx}` do viewer para as malhas que o OQ3D grava.

O OQ3D só tem **cor por malha**; o viewer tem cor por vértice. A regra, única para os dois
escritores de `.aq` (uma peça e catálogo inteiro): a cor de um triângulo é a do seu **primeiro
vértice**, arredondada a 4 casas; triângulos da mesma cor viram uma malha, com os vértices
reindexados; tudo em centímetros Z-up (`eixos.viewer_para_zup_np`).
"""
import numpy as np

from bim_pipeline.geometria.eixos import M_TO_CM, viewer_para_zup_np

COR_PADRAO = (0.533, 0.588, 0.667)


class GeometriaInvalida(ValueError):
    """A geometria não tem o formato do contrato — quem chama decide como reportar."""


def rgba(rgb):
    """(r, g, b) em 0–1 → (R, G, B, 255) em 0–255, saturado."""
    return tuple(int(round(max(0.0, min(1.0, float(c))) * 255)) for c in rgb[:3]) + (255,)


def malhas_por_cor(geo, onde='geometria'):
    """
    `geo` = `{pos, col?, idx}` → `[(verts_cm, tris, rgba, None)]`, uma malha por cor.
    Lança `GeometriaInvalida` com o motivo (JSON inválido, sem triângulos, índice fora, NaN).
    """
    try:
        pos = np.asarray(geo['pos'], dtype=float).reshape(-1, 3)
        idx = np.asarray(geo['idx'], dtype=np.int64).reshape(-1, 3)
    except (KeyError, TypeError, ValueError) as e:
        raise GeometriaInvalida(f'{onde}: JSON de geometria inválido ({e})')
    if len(idx) == 0 or len(pos) == 0:
        raise GeometriaInvalida(f'{onde}: geometria sem triângulos')
    if idx.min() < 0 or idx.max() >= len(pos):
        raise GeometriaInvalida(f'{onde}: índice {int(idx.max())} fora dos {len(pos)} vértices')
    if not np.isfinite(pos).all():
        raise GeometriaInvalida(f'{onde}: coordenada não finita')

    col = geo.get('col') or []
    if len(col) == len(geo['pos']):
        cores_v = np.asarray(col, dtype=float).reshape(-1, 3)
        chave = np.round(cores_v[idx[:, 0]], 4)
        cores, inv = np.unique(chave, axis=0, return_inverse=True)
        inv = np.asarray(inv).ravel()
    else:
        cores = np.array([COR_PADRAO])
        inv = np.zeros(len(idx), dtype=np.int64)

    malhas = []
    for k, cor in enumerate(cores):
        tris = idx[inv == k]
        usados, remap = np.unique(tris, return_inverse=True)
        verts = viewer_para_zup_np(pos[usados], M_TO_CM)
        malhas.append((verts.tolist(), np.asarray(remap).reshape(-1, 3).tolist(), rgba(cor), None))
    return malhas


def malhas_de_partes(partes):
    """
    Partes do editor `[{nome, pos, col?, idx}]` → uma malha por parte, cor do primeiro
    vértice (ou a padrão). Partes sem triângulos são ignoradas.
    """
    malhas = []
    for p in partes:
        pos, idx, col = p['pos'], p['idx'], p.get('col')
        if not idx:
            continue
        cor = tuple(col[:3]) if col else COR_PADRAO
        verts = viewer_para_zup_np(np.asarray(pos, dtype=float).reshape(-1, 3), M_TO_CM)
        tris = np.asarray(idx, dtype=np.int64).reshape(-1, 3)
        malhas.append((verts.tolist(), tris.tolist(), rgba(cor), None))
    return malhas
