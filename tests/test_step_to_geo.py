"""
step_to_geo.py — IGES (S7.17): faces soltas são costuradas num sólido com as normais para fora.

O IGES não tem sólido: o SolidWorks exporta uma superfície aparada por face e o leitor devolve
N formas livres sem orientação consistente. Este teste escreve um IGES de verdade com o próprio
OpenCASCADE (uma caixa → 6 faces soltas) e confere o que o `converter` promete: `formato`
'iges', `costurado`, volume positivo igual ao da caixa, 12 triângulos com as normais para fora
(volume assinado da MALHA positivo — é isso que o viewer enxerga). O STEP da mesma caixa passa
pelo caminho antigo (sólido do arquivo, sem costura) e tem de dar a mesma malha.

Os IGES da Tupy (`eng-reversa/tupy/downloads/`, gitignored) entram quando existem: sólido
fechado, volume positivo, cor preservada depois da costura.
"""
import glob
import os
import subprocess
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE = os.path.join(RAIZ, 'www', 'apps', 'ingestao', 'pipeline')
sys.path.insert(0, PIPELINE)

step_to_geo = pytest.importorskip('step_to_geo')
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
    r = subprocess.run([sys.executable, os.path.join(PIPELINE, 'step_to_geo.py'), caixa['igs'], str(saida)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert 'IGES em MM' in r.stdout and 'costurado' in r.stdout
    assert saida.exists()


TUPY = sorted(glob.glob(os.path.join(RAIZ, 'eng-reversa', 'tupy', 'downloads', '*', '*.igs')))


@pytest.mark.skipif(not TUPY, reason='IGES da Tupy não baixados (eng-reversa/tupy/tools/tupy_baixar.py)')
@pytest.mark.parametrize('caminho', [p for p in TUPY if 'CURVA 90' in p or 'CRUZETA' in p] or TUPY[:1],
                         ids=lambda p: os.path.basename(p)[:30])
def test_iges_tupy_solido_fechado_com_cor(caminho):
    geo = step_to_geo.converter(caminho)
    assert geo['costurado'] is True
    assert geo['arestas_livres'] == 0
    assert geo['volume_cm3'] > 0
    assert volume_assinado_m3(geo) > 0
    assert len(geo['partes']) == 1
    # a cor do SolidWorks (cinza 0.06) sobrevive à costura — não cai no cinza padrão do viewer
    assert tuple(geo['partes'][0]['cor']) != step_to_geo.COR_PADRAO
    assert len(geo['col']) == len(geo['pos'])
