"""bim_pipeline.geometria.bocais — os pontos de ligação recuperados da malha.

O que estes testes provam, com malha sintética (as nativas ficam fora do repositório):

- num tubo de parede fina o detector acha **os dois** bocais, no centro de cada ponta, com
  o raio interno como bitola — e não acha nada nas faces circulares do meio do tubo;
- a malha pode ser estanque: a ponta é uma face anelar de triângulos coplanares, não um
  buraco, que é como a malha de fabricante vem;
- a orientação dos triângulos não muda o resultado (o *winding* de malha de fabricante não
  é consistente, então o "lado de fora" não pode sair do sinal da normal);
- parede grossa, anel sem tubo atrás e tampa cheia **não** são bocal.
"""
import numpy as np
import pytest

from bim_pipeline.geometria.bocais import bocais, solda
from malhas_sinteticas import cilindro_tampado, tubo


def test_tubo_tem_bocal_nas_duas_pontas():
    achados = bocais(tubo(r_int=0.9, r_ext=1.0, comprimento=6.0))
    assert len(achados) == 2
    centros = sorted(b['centro'][2] for b in achados)
    assert centros == pytest.approx([0.0, 6.0], abs=1e-6)
    for b in achados:
        assert b['raio'] == pytest.approx(0.9, rel=2e-2)      # bitola = raio interno
        assert b['centro'][:2] == pytest.approx([0.0, 0.0], abs=1e-6)
        assert abs(abs(b['normal'][2]) - 1.0) < 1e-6          # eixo do tubo


def test_face_circular_do_meio_do_tubo_nao_e_bocal():
    """Friso e degrau de parede são faces anelares tão boas quanto a ponta — só não são
    extremas. Se entrassem, a peça ganharia bocal no meio do corpo."""
    achados = bocais(tubo(comprimento=9.0, planos_extra=(3.0, 6.0)))
    assert len(achados) == 2
    assert sorted(round(b['centro'][2], 6) for b in achados) == [0.0, 9.0]


@pytest.mark.parametrize('inverte', [False, True])
def test_winding_nao_muda_o_resultado(inverte):
    achados = bocais(tubo(comprimento=6.0, inverte=inverte))
    assert sorted(round(b['centro'][2], 6) for b in achados) == [0.0, 6.0]


@pytest.mark.parametrize('malhas, motivo', [
    (tubo(r_int=0.4, r_ext=1.0), 'parede grossa não é ponta de tubo'),
    (tubo(r_int=0.9, r_ext=1.0, comprimento=1.0), 'sem tubo atrás da face'),
    (cilindro_tampado(), 'tampa cheia não é anel'),
])
def test_o_que_nao_e_bocal(malhas, motivo):
    assert bocais(malhas) == [], motivo


def test_solda_junta_vertices_repetidos_de_malhas_distintas():
    """O OQ3D traz uma malha por cor; sem soldar, o contorno sai picado na fronteira."""
    (V, F, _), = tubo()
    metade = len(F) // 2
    duas = [(V, F[:metade], (1, 2, 3, 255)), (V, F[metade:], (4, 5, 6, 255))]
    Vs, Fs = solda(duas)
    assert len(Vs) == len(V)
    assert Fs.max() == len(V) - 1
    assert len(bocais(duas)) == 2


@pytest.mark.parametrize('inverte', [False, True])
def test_normal_aponta_para_fora_do_corpo(inverte):
    """O azimute que vira `ANGULO_EP` depende do sentido da normal, e o sentido do
    triângulo não serve — a de cada bocal tem de apontar para fora."""
    achados = sorted(bocais(tubo(comprimento=6.0, inverte=inverte)),
                     key=lambda b: b['centro'][2])
    baixo, alto = achados
    assert baixo['normal'][2] < -0.99
    assert alto['normal'][2] > 0.99
