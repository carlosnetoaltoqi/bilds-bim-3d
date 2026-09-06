"""oq3d.py — o leitor do formato binário dentro do .aq.

Cobre o contrato compartilhado com o port TS (www/tools/oq3d-parser.ts):
truncado → OQ3DError; layout desconhecido → bloco pulado + OQ3DAvisoParse;
versões 2 e 3 de malha idênticas; contagem de raízes do cabeçalho conferida.
"""
import warnings

import pytest

from bim_pipeline.aq import oq3d
from bim_pipeline.aq import read_aq
from oq3d_sintetico import (RGBA, TRIS, VERTS_CM, com_n_coord, com_n_idx,
                            com_raizes_declaradas, com_versao_malha,
                            duas_malhas, esperado_triangulo, triangulo,
                            truncado_nas_coords)


def _to_buffers_sem_aviso(blob):
    with warnings.catch_warnings():
        warnings.simplefilter('error', oq3d.OQ3DAvisoParse)
        return oq3d.to_buffers(blob)


def _avisos(blob):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always', oq3d.OQ3DAvisoParse)
        data = oq3d.to_buffers(blob)
    return data, [str(x.message) for x in w if issubclass(x.category, oq3d.OQ3DAvisoParse)]


# ── assinatura ────────────────────────────────────────────────────────────────

def test_is_oq3d():
    assert oq3d.is_oq3d(triangulo())
    assert not oq3d.is_oq3d(b'')
    assert not oq3d.is_oq3d(b'\x00' * 64 + oq3d.MAGIC)   # assinatura fora dos 64 primeiros bytes
    assert not oq3d.is_oq3d('OQ3D 3D Objects File')      # str não é blob


def test_sem_assinatura_lanca():
    with pytest.raises(oq3d.OQ3DError, match='assinatura'):
        oq3d.parse(b'isto nao e um blob OQ3D')
    with pytest.raises(oq3d.OQ3DError):
        oq3d.to_buffers(b'')


# ── geometria e conversão de eixos ────────────────────────────────────────────

def test_triangulo_sintetico_to_buffers():
    data = _to_buffers_sem_aviso(triangulo())
    assert data == esperado_triangulo()


def test_extract_devolve_cm_z_up_e_cor():
    (verts, tris, rgba), = oq3d.extract(triangulo())
    assert [tuple(v) for v in verts] == VERTS_CM
    assert [tuple(t) for t in tris] == TRIS
    assert tuple(rgba) == RGBA


def test_duas_malhas_reindexam():
    data = _to_buffers_sem_aviso(duas_malhas())
    assert len(data['pos']) == 18
    assert data['idx'] == [0, 1, 2, 3, 4, 5]
    assert data['col'][:3] == [1.0, 0.0, 0.0] and data['col'][-3:] == [0.0, 0.0, 1.0]


def test_transform_translada():
    xform = ((1, 0, 0, 0, 1, 0, 0, 0, 1), (100.0, 0.0, 0.0))   # +1 m em x
    data = _to_buffers_sem_aviso(triangulo(xform))
    base = esperado_triangulo()['pos']
    assert data['pos'][0::3] == pytest.approx([v + 1.0 for v in base[0::3]])
    assert data['pos'][1::3] == pytest.approx(base[1::3])


def test_bbox_e_stats():
    assert oq3d.bbox(triangulo(), skip_markers=False) == (60.0, 60.0, 60.0)
    s = oq3d.stats(triangulo())
    assert (s['malhas'], s['vertices'], s['triangulos']) == (1, 3, 1)
    assert s['cores'] == [(255, 0, 0)]


def test_contagem_de_raizes_confere_no_sintetico():
    blob = duas_malhas()
    assert oq3d.n_raizes_declarado(blob) == 2
    assert len(oq3d.parse(blob)) == 2


# ── versões de malha (Maxbar usa a 3) ─────────────────────────────────────────

def test_malha_versao_3_tem_o_mesmo_layout_da_2():
    assert oq3d.MESH_VERSOES == (2, 3)
    data = _to_buffers_sem_aviso(com_versao_malha(triangulo(), 3))
    assert data == esperado_triangulo()


def test_malha_de_versao_desconhecida_e_pulada_com_aviso():
    data, avisos = _avisos(com_versao_malha(triangulo(), 9))
    assert data == {'pos': [], 'col': [], 'idx': []}
    assert len(avisos) == 1 and 'versão 9' in avisos[0] and 'pulado' in avisos[0]


def test_n_idx_invalido_e_pulado_com_aviso():
    data, avisos = _avisos(com_n_idx(triangulo(), 4))
    assert data['pos'] == []
    assert any('4 índices' in a for a in avisos)


def test_n_coord_zero_e_pulado_com_aviso():
    data, avisos = _avisos(com_n_coord(triangulo(), 0))
    assert data['pos'] == [] and avisos


# ── truncado / corrompido → erro, nunca silêncio ──────────────────────────────

def test_truncado_nas_coordenadas_lanca():
    with pytest.raises(oq3d.OQ3DError, match='excedem'):
        oq3d.to_buffers(truncado_nas_coords(triangulo()))


def test_n_coord_maior_que_o_buffer_lanca_antes_de_alocar():
    with pytest.raises(oq3d.OQ3DError, match='coordenadas declaradas'):
        oq3d.to_buffers(com_n_coord(triangulo(), 3 * 10 ** 8))


def test_n_idx_maior_que_o_buffer_lanca():
    with pytest.raises(oq3d.OQ3DError, match='índices declarados'):
        oq3d.to_buffers(com_n_idx(triangulo(), 3 * 10 ** 8))


# ── cabeçalho: raízes declaradas ──────────────────────────────────────────────

def test_raizes_divergentes_avisam_mas_devolvem_geometria():
    data, avisos = _avisos(com_raizes_declaradas(triangulo(), 5))
    assert data == esperado_triangulo()
    assert len(avisos) == 1 and 'declara 5 objetos-raiz' in avisos[0]


# ── bibliotecas reais ─────────────────────────────────────────────────────────

def test_akato_todas_as_simbologias_legiveis_e_sem_aviso(akato_aq):
    sims, por_peca = read_aq.extract_simbologias(akato_aq)
    assert len(sims) == 262 and len(por_peca) == 262
    for sid, s in sims.items():
        assert oq3d.is_oq3d(s['blob']), sid
        data, avisos = _avisos(s['blob'])
        assert avisos == [], (sid, avisos)
        n_v = len(data['pos']) // 3
        assert n_v > 0 and len(data['col']) == len(data['pos']), sid
        assert len(data['idx']) % 3 == 0 and max(data['idx']) < n_v, sid


def test_maxbar_malhas_versao_3_agora_tem_geometria(maxbar_aq):
    """Regressão do achado de 2026-09-03: 31 simbologias (56 peças) saíam vazias."""
    sims, por_peca = read_aq.extract_simbologias(maxbar_aq)
    v3 = {sid for sid, s in sims.items() if s['blob'][25] == 3}
    assert len(v3) == 31
    assert sum(1 for sid in por_peca.values() if sid in v3) == 56
    for sid in v3:
        data, avisos = _avisos(sims[sid]['blob'])
        assert data['pos'] and avisos == [], sid
        assert oq3d.n_raizes_declarado(sims[sid]['blob']) == len(oq3d.parse(sims[sid]['blob']))
