"""bim_pipeline.geometria — eixos, dedup e malhas por cor: uma implementação para toda a biblioteca (S8/F1).

O dedup vetorizado tem de dar EXATAMENTE o que a implementação pura de referência dava (mesma ordem
de primeira ocorrência, -0.0 ≠ 0.0, cor na chave). As conversões de eixos são inversas uma da outra.
As malhas por cor seguem a regra "cor do primeiro vértice, 4 casas".
"""
import struct

import numpy as np
import pytest

from bim_pipeline.geometria import eixos
from bim_pipeline.geometria.dedup import dedup, dedup_arrays
from bim_pipeline.geometria.malhas import GeometriaInvalida, malhas_de_partes, malhas_por_cor


def _dedup_referencia(data):
    """A implementação pura que a biblioteca tinha até 2026-09-06 — é o oráculo."""
    pos, col, existing_idx = data['pos'], data.get('col', []), data.get('idx')
    if existing_idx is not None:
        ep, ec = [], []
        for i in existing_idx:
            ep += pos[i * 3:i * 3 + 3]
            if col:
                ec += col[i * 3:i * 3 + 3]
        pos, col = ep, ec
    n = len(pos) // 3
    q = lambda v: struct.pack('f', v)   # noqa: E731
    seen, new_pos, new_col, new_idx = {}, [], [], []
    for i in range(n):
        px, py, pz = pos[i * 3:i * 3 + 3]
        if col:
            cr, cg, cb = col[i * 3:i * 3 + 3]
            key = (q(px), q(py), q(pz), q(cr), q(cg), q(cb))
        else:
            key = (q(px), q(py), q(pz))
        if key not in seen:
            seen[key] = len(new_pos) // 3
            new_pos += [px, py, pz]
            if col:
                new_col += [cr, cg, cb]
        new_idx.append(seen[key])
    return {'pos': new_pos, 'col': new_col if col else [], 'idx': new_idx}, n, len(new_pos) // 3


@pytest.mark.parametrize('com_cor', [True, False])
def test_dedup_vetorizado_igual_a_referencia(com_cor):
    rng = np.random.default_rng(7)
    base = rng.uniform(-1, 1, size=(40, 3))
    pos = base[rng.integers(0, 40, size=600)]                  # muitos repetidos
    pos[5] = [0.0, 0.0, 0.0]; pos[9] = [-0.0, 0.0, 0.0]         # -0.0 e 0.0 são chaves distintas
    pos[11] = pos[5] + 1e-9                                      # abaixo da resolução float32: colapsa
    col = np.where(rng.random((600, 1)) < 0.5, [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]) if com_cor else None
    data = {'pos': pos.ravel().tolist(), 'col': col.ravel().tolist() if com_cor else []}
    esperado, n, n_u = _dedup_referencia(data)
    obtido, orig, dedup_n, pct = dedup(data)
    assert (orig, dedup_n) == (n, n_u) and 0 < pct < 100
    assert obtido['idx'] == esperado['idx']
    assert obtido['pos'] == esperado['pos'] and obtido['col'] == esperado['col']
    # a cor entra na chave: mesma posição com cores diferentes são vértices diferentes
    if com_cor:
        assert dedup_n > dedup({'pos': data['pos'], 'col': []})[2]


def test_dedup_reindexa_entrada_ja_indexada_e_vazia():
    data = {'pos': [0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0], 'col': [], 'idx': [0, 1, 2, 2, 1, 3]}
    r, orig, n, _ = dedup(data)
    assert orig == 6 and n == 3 and r['idx'] == [0, 1, 2, 2, 1, 1]
    assert dedup({'pos': [], 'col': []}) == ({'pos': [], 'col': [], 'idx': []}, 0, 0, 0)
    pos_u, col_u, idx = dedup_arrays(np.zeros((3, 3)), None)
    assert len(pos_u) == 1 and col_u is None and idx.tolist() == [0, 0, 0]


def test_eixos_sao_inversos_e_batem_com_a_regra():
    assert eixos.zup_para_viewer(1, 2, 3) == (1, 3, -2)
    assert eixos.viewer_para_zup(1, 3, -2) == (1, 2, 3)
    pts = np.array([[1.0, 2.0, 3.0], [-4.0, 5.0, -6.0]])
    ida = eixos.zup_para_viewer_np(pts, eixos.CM_TO_M)
    assert np.allclose(ida, [[0.01, 0.03, -0.02], [-0.04, -0.06, -0.05]])
    assert np.allclose(eixos.viewer_para_zup_np(ida, eixos.M_TO_CM), pts)
    assert eixos.plano_zup_para_viewer([1000, 2000, 3000], eixos.MM_TO_M, casas=7) == [1.0, 3.0, -2.0]
    verts, tris = eixos.viewer_para_oq3d([0, 0, 0, 0.1, 0, 0, 0, 0.1, 0], [0, 1, 2])
    assert verts == [(0.0, -0.0, 0.0), (10.0, -0.0, 0.0), (0.0, -0.0, 10.0)] and tris == [(0, 1, 2)]


def test_malhas_por_cor_regra_do_primeiro_vertice():
    # dois triângulos: o primeiro vermelho, o segundo azul (pelo primeiro vértice), em metros Y-up
    geo = {'pos': [0, 0, 0, 1, 0, 0, 0, 1, 0, 2, 0, 0, 3, 0, 0, 2, 1, 0],
           'col': [1, 0, 0] * 3 + [0, 0, 1] * 3, 'idx': [0, 1, 2, 3, 4, 5]}
    malhas = malhas_por_cor(geo)
    cores = sorted(m[2] for m in malhas)
    assert cores == [(0, 0, 255, 255), (255, 0, 0, 255)]
    for verts, tris, _, xform in malhas:
        assert len(verts) == 3 and tris == [[0, 1, 2]] and xform is None
        assert all(len(v) == 3 for v in verts) and max(abs(c) for v in verts for c in v) <= 300   # cm
    # sem cor → uma malha com a cor padrão; partes do editor → uma malha por parte
    assert len(malhas_por_cor({'pos': geo['pos'], 'col': [], 'idx': geo['idx']})) == 1
    partes = [{'pos': geo['pos'][:9], 'idx': [0, 1, 2], 'col': [0, 1, 0]}, {'pos': [], 'idx': []}]
    assert [m[2] for m in malhas_de_partes(partes)] == [(0, 255, 0, 255)]


@pytest.mark.parametrize('geo, motivo', [
    ({'pos': [0, 0, 0], 'idx': []}, 'sem triângulos'),
    ({'pos': [0, 0, 0, 1, 0, 0], 'idx': [0, 1, 5]}, 'fora dos'),
    ({'pos': [0, 0, float('nan'), 1, 0, 0, 0, 1, 0], 'idx': [0, 1, 2]}, 'não finita'),
    ({'pos': 'x'}, 'inválido'),
])
def test_malhas_por_cor_acusa_geometria_invalida(geo, motivo):
    with pytest.raises(GeometriaInvalida, match=motivo):
        malhas_por_cor(geo, onde='teste')
