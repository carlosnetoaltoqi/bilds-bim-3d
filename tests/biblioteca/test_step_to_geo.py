"""
step_to_geo.py — IGES (S7.17): faces soltas são costuradas num sólido com as normais para fora.

O IGES não tem sólido: o SolidWorks exporta uma superfície aparada por face e o leitor devolve
N formas livres sem orientação consistente. Este teste escreve um IGES de verdade com o próprio
OpenCASCADE (uma caixa → 6 faces soltas) e confere o que o `converter` promete: `formato`
'iges', `costurado`, volume positivo igual ao da caixa, 12 triângulos com as normais para fora
(volume assinado da MALHA positivo — é isso que o viewer enxerga). O STEP da mesma caixa passa
pelo caminho antigo (sólido do arquivo, sem costura) e tem de dar a mesma malha.

IGES reais (fixture `iges_pasta`, local) entram quando existem: sólido
fechado, volume positivo, cor preservada depois da costura.
"""
import glob
import os
import subprocess
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, 'biblioteca'))
sys.path.insert(0, os.path.join(RAIZ, 'tests'))
from fixtures import caminho as fixture   # noqa: E402

step_to_geo = pytest.importorskip('bim_pipeline.conversores.step_iges')
if not step_to_geo.HAS_OCP:
    pytest.skip('OCP (cadquery-ocp) não instalado', allow_module_level=True)

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox          # noqa: E402
from OCP.IGESControl import IGESControl_Writer, IGESControl_Controller  # noqa: E402
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs  # noqa: E402
from OCP.TopExp import TopExp_Explorer                   # noqa: E402
from OCP.TopAbs import TopAbs_FACE                       # noqa: E402

LADOS_MM = (20.0, 30.0, 40.0)


def volume_assinado_m3(geo):
    """Soma de (a · (b × c)) / 6 sobre os triângulos: positivo se as normais apontam para fora."""
    pos, idx = geo['pos'], geo['idx']
    v = 0.0
    for t in range(0, len(idx), 3):
        a, b, c = (pos[3 * idx[t + k]: 3 * idx[t + k] + 3] for k in range(3))
        v += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return v


@pytest.fixture(scope='module')
def caixa(tmp_path_factory):
    d = tmp_path_factory.mktemp('caixa')
    solido = BRepPrimAPI_MakeBox(*LADOS_MM).Shape()
    # IGES só com as faces, como o SolidWorks faz — sem o sólido, sem orientação garantida.
    IGESControl_Controller.Init_s()
    w = IGESControl_Writer('MM', 0)
    ex = TopExp_Explorer(solido, TopAbs_FACE)
    while ex.More():
        w.AddShape(ex.Current())
        ex.Next()
    w.ComputeModel()
    igs = str(d / 'caixa.igs')
    assert w.Write(igs)
    sw = STEPControl_Writer()
    sw.Transfer(solido, STEPControl_AsIs)
    stp = str(d / 'caixa.stp')
    sw.Write(stp)
    return {'igs': igs, 'stp': stp}


def test_formato_de():
    assert step_to_geo.formato_de('x.igs') == 'iges'
    assert step_to_geo.formato_de('X.IGES') == 'iges'
    assert step_to_geo.formato_de('x.stp') == 'step'
    with pytest.raises(SystemExit, match='não é STEP'):
        step_to_geo.formato_de('x.dxf')


def test_iges_faces_soltas_viram_solido_orientado(caixa):
    geo = step_to_geo.converter(caixa['igs'])
    assert geo['formato'] == 'iges'
    assert geo['costurado'] is True
    assert geo['arestas_livres'] == 0
    vol = LADOS_MM[0] * LADOS_MM[1] * LADOS_MM[2] / 1000.0
    assert geo['volume_cm3'] == pytest.approx(vol, rel=1e-6)
    assert len(geo['idx']) // 3 == 12
    assert len(geo['partes']) == 1 and geo['partes'][0]['triangulos'] == 12
    # normais para fora: volume assinado da malha em m³ = volume da caixa
    assert volume_assinado_m3(geo) == pytest.approx(vol * 1e-6, rel=1e-6)
    assert sorted(round(x, 3) for x in geo['bbox_mm']) == sorted(LADOS_MM)


def test_step_da_mesma_caixa_nao_costura(caixa):
    geo = step_to_geo.converter(caixa['stp'])
    assert geo['formato'] == 'step'
    assert 'costurado' not in geo
    assert len(geo['idx']) // 3 == 12
    assert volume_assinado_m3(geo) == pytest.approx(LADOS_MM[0] * LADOS_MM[1] * LADOS_MM[2] * 1e-9, rel=1e-6)


def test_cli_iges(caixa, tmp_path):
    saida = tmp_path / 'caixa.json'
    r = subprocess.run([sys.executable, '-m', 'bim_pipeline.cli.step_iges', caixa['igs'], str(saida)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert 'IGES em MM' in r.stdout and 'costurado' in r.stdout
    assert saida.exists()


_PASTA_IGES = fixture('iges_pasta')
IGES_REAIS = sorted(glob.glob(os.path.join(_PASTA_IGES, '**', '*.igs'), recursive=True)) if _PASTA_IGES else []


@pytest.mark.skipif(not IGES_REAIS, reason='fixture "iges_pasta" não configurada (tests/fixtures.py)')
def test_iges_reais_costurados_ficam_fechados_com_a_cor_original():
    """Sobre IGES reais de faces soltas: a costura fecha o que dá para fechar (volume positivo,
    normais para fora, cor do CAD preservada) e é HONESTA sobre o que não fecha (arestas livres
    contadas, nunca `costurado` sem ser). Ao menos uma peça da pasta tem de fechar."""
    fechados, abertos = [], []
    for caminho in IGES_REAIS[:6]:
        geo = step_to_geo.converter(caminho)
        assert geo['costurado'] is True and geo['formato'] == 'iges' and len(geo['col']) == len(geo['pos'])
        # a cor do CAD sobrevive à costura — não cai no cinza padrão do viewer
        assert all(tuple(p['cor']) != step_to_geo.COR_PADRAO for p in geo['partes']), caminho
        if geo['arestas_livres'] == 0:
            assert geo['volume_cm3'] > 0 and volume_assinado_m3(geo) > 0, caminho
            fechados.append(caminho)
        else:
            abertos.append((caminho, geo['arestas_livres']))
    assert fechados, f'nenhum IGES da pasta fechou: {abertos}'
