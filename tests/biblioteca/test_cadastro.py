"""
O construtor único do cadastro (`bim_pipeline.aq.cadastro`) — a regra do ADR-024.

O que estes testes protegem é o defeito que a engenharia do Builder encontrou: uma biblioteca
de válvulas de HVAC exportada daqui saiu **inteira** cadastrada como "Conexão" hidráulica,
porque o classificador era um vocabulário de catálogo de PVC com *default* "conexão" e a
disciplina saía de quatro palavras no título.
"""
import pytest

from bim_pipeline.aq import cadastro


def test_disciplina_desconhecida_levanta():
    with pytest.raises(ValueError):
        cadastro.mascara_da_disciplina('encanamento')


def test_a_mascara_de_agua_fria_e_4_e_a_de_incendio_e_20():
    """As duas que estavam erradas: 12 é hidráulico + sanitário; 22 carrega um bit não identificado."""
    assert cadastro.mascara_da_disciplina('hidraulico') == 4
    assert cadastro.mascara_da_disciplina('incendio') == 20
    assert cadastro.mascara_da_disciplina('sanitario') == 8
    assert cadastro.mascara_da_disciplina('gas') == 36


def test_a_entidade_ifc_da_fonte_vence_o_nome():
    """Passo 1 do ADR-024: a classe IFC prevê a aplicação com pouca ambiguidade."""
    # o nome diz "conexão", mas a fonte declarou uma condensadora
    _ent, _tipo, _e23, _sub, apl = cadastro.classificar(
        'Conexão frigorígena', 'climatizacao', entidade_ifc=2102)
    assert apl == cadastro.APL_CONDENSADORA


def test_supertipo_abstrato_nao_vence_o_nome():
    """ADR-026: `IfcDistributionFlowElement` (2087) não diz o que a peça é — diz que é uma peça.

    Medido no catálogo oficial: das 1.024 peças declaradas com 2087, a aplicação dominante é
    **conexão** (56 %), não "equipamento". Uma fonte que declara o supertipo não pode calar o
    vocabulário; uma que declara `IfcValve` ou uma condensadora, pode.
    """
    ent, _t, _e, _s, apl = cadastro.classificar('Válvula de esfera', 'climatizacao', 2087)
    assert (ent, apl) == (2084, cadastro.APL_VALVULA_BLOQUEIO)      # o nome decidiu

    # e o supertipo continua servindo de rede quando o nome também não diz nada
    ent, _t, _e, _s, apl = cadastro.classificar('XPTO 42', 'climatizacao', 2087)
    assert (ent, apl) == (2087, cadastro.APL_EQUIPAMENTO)


def test_as_entidades_medidas_em_2026_09_11_classificam():
    """Dez entidades do catálogo oficial estavam fora da tabela e caíam no genérico."""
    assert cadastro.classificar('Caixa de gordura 100L', 'sanitario', 2066)[4] == 30
    assert cadastro.classificar('Transformador 150 kVA', 'eletrico', 2082)[4] == 35
    assert cadastro.classificar('Detetor de fumaça', 'eletrico', 2077)[0] == 2077


def test_a_mesma_entidade_muda_de_aplicacao_com_a_disciplina():
    """2073 é componente elétrico no elétrico e captor no SPDA — medido no catálogo oficial."""
    assert cadastro.classificar('Captor', 'eletrico', 2073)[4] == cadastro.APL_COMPONENTE
    assert cadastro.classificar('Captor', 'spda', 2073)[4] == cadastro.APL_CAPTOR


def test_o_vocabulario_e_o_da_disciplina_escolhida():
    """Um atuador de HVAC não pode mais cair no vocabulário do PVC hidráulico."""
    apl_clima = cadastro.classificar('Válvula de bloqueio', 'climatizacao')[4]
    apl_hidro = cadastro.classificar('Válvula de gaveta', 'hidraulico')[4]
    assert apl_clima == cadastro.APL_VALVULA_BLOQUEIO
    assert apl_hidro == cadastro.APL_REGISTRO
    assert apl_clima != apl_hidro


def test_sem_reconhecer_cai_no_generico_da_disciplina_e_avisa():
    """A decisão de 2026-09-10: avisa e grava o genérico — não aborta, nem escolhe calado."""
    diag = cadastro.Diagnostico()
    apl = cadastro.classificar('Actuator MP500C-SRD', 'eletrico', diag=diag)[4]
    assert apl == cadastro.APL_DISPOSITIVO_ELETRICO       # e não conexão hidráulica
    assert diag.sem_aplicacao == ['Actuator MP500C-SRD']
    assert any('sem aplicação reconhecida' in linha for linha in diag.linhas())
    assert diag.resumo()['gruposSemAplicacao'] == ['Actuator MP500C-SRD']


def test_o_posicionamento_sai_da_aplicacao_e_tubo_e_nulo():
    """Tubo é a única coluna nula, e é regra fechada: 2.104 de 2.104 no catálogo oficial."""
    assert cadastro.posicionar_simbologia_3d(cadastro.APL_TUBO) is None
    assert cadastro.posicionar_simbologia_3d(cadastro.APL_CONEXAO) == 0
    assert cadastro.posicionar_simbologia_3d(cadastro.APL_BOMBA) == 3
    assert cadastro.posicionar_simbologia_3d(999) == cadastro.POSICIONAR_PADRAO


def test_as_duas_linhas_saem_prontas_e_coerentes():
    """`linha_grupo` e `linha_peca` são o que os dois escritores gravam — sem divergir."""
    diag = cadastro.Diagnostico()
    campos_gp, apl = cadastro.linha_grupo(
        id_grupo=1, nome='Tubos', disciplina='sanitario', id_classe=1, diag=diag)
    assert campos_gp['PROJETO_APLICACAO'] == 8
    assert apl == cadastro.APL_TUBO
    assert campos_gp['ELEMENTO_APLICACAO'] == 1 and campos_gp['REPRESENTACAO_GP'] == 2

    campos_peca = cadastro.linha_peca(
        id_peca=1, nome='Tubo 100', id_grupo=1, aplicacao=apl,
        fabricante='Fábrica', descricao='Tubo')
    assert campos_peca['POSICIONAR_SIMBOLOGIA_3D'] is None       # tubo
    assert campos_peca['INDICE_SIMBOLO3D_SELECIONADO'] == -1     # o default do schema
    assert campos_peca['CONEXAO_VOLUMETRICA'] == 0               # ligado por entradas_aq
    assert diag.vazio
