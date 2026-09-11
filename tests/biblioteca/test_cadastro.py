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

    # e o supertipo continua servindo de rede quando o nome também não diz nada — com a
    # aplicação que a medição sustenta (conexão), não "equipamento"
    ent, _t, _e, _s, apl = cadastro.classificar('XPTO 42', 'climatizacao', 2087)
    assert (ent, apl) == (2087, cadastro.APL_CONEXAO)


def test_o_supertipo_2087_e_conexao_e_o_nome_do_fabricante_e_reconhecido():
    """Round-trip de 2026-09-11 numa biblioteca real de barramento blindado.

    As 212 peças de conexão dela declaram `2087` e aplicação **2**, e saíam da reexportação como
    68 (equipamento) — a tabela derivava do supertipo uma aplicação que nem o catálogo oficial
    (2 em 56 % de 1.024 peças) nem a nativa (212 de 212) sustentam. E o vocabulário elétrico já
    tinha regra de conexão, que não pegava porque o fabricante escreve "Cotovelo" e `"T"`.
    """
    # nome que não diz nada (o fabricante batiza a linha): fica o supertipo, com a aplicação medida
    assert cadastro.classificar('XPTO 400A', 'eletrico', 2087)[::4] == (2087, cadastro.APL_CONEXAO)
    # nome que diz: o vocabulário vence o supertipo e traz a entidade específica
    for nome in ('Barramento CMAX - Cotovelo Horizontal', 'Barramento VMAX - "T" Vertical'):
        assert cadastro.classificar(nome, 'eletrico', 2087)[::4] == (2051, cadastro.APL_CONEXAO), nome

    # 'COFRE' entrou medido (32 de 32 peças do catálogo oficial na aplicação 32), e é o que
    # impede o armário de virar conexão pelo fallback
    assert cadastro.classificar('Caixa Cofre', 'eletrico', 2087)[::4] == \
        (2059, cadastro.APL_QUADRO_DISTRIBUICAO)


def test_as_entidades_medidas_em_2026_09_11_classificam():
    """Dez entidades do catálogo oficial estavam fora da tabela e caíam no genérico."""
    assert cadastro.classificar('Caixa de gordura 100L', 'sanitario', 2066)[4] == 30
    assert cadastro.classificar('Transformador 150 kVA', 'eletrico', 2082)[4] == 35
    assert cadastro.classificar('Detetor de fumaça', 'eletrico', 2077)[0] == 2077


def test_nome_em_ingles_classifica_igual_ao_portugues():
    """Família Revit de fabricante internacional nomeia tudo em inglês.

    Medido no Builder em 2026-09-11: uma biblioteca de válvulas e atuadores de HVAC saiu
    **inteira** como "Elemento genérico" (aplicação 68) — nenhuma palavra do vocabulário casou
    com `Actuator - MP500C` nem com `PIBCV Valves`, e o Builder recebeu o nosso "não sei".
    """
    assert cadastro.classificar('Actuator - MP500C', 'climatizacao')[::4] == \
        cadastro.classificar('Atuador MP500C', 'climatizacao')[::4] == (2084, cadastro.APL_VALVULA_BLOQUEIO)
    for ingles, portugues, disciplina in [('Ball Valve DN50', 'Válvula de esfera DN50', 'hidraulico'),
                                          ('Elbow 90 DN50', 'Curva 90 DN50', 'hidraulico'),
                                          ('Pump 3CV', 'Bomba 3CV', 'hidraulico'),
                                          ('Floor Drain 100', 'Ralo 100', 'sanitario')]:
        assert cadastro.classificar(ingles, disciplina)[::4] == cadastro.classificar(portugues, disciplina)[::4], ingles


def test_peca_com_ligacao_3d_so_aceita_dois_modos_de_posicionamento():
    """O Cadastro oferece só dois modos quando "Pontos de ligação 3D" está em Sim, e o catálogo
    oficial concorda: 4.206 de 4.206 peças usam 2 ou 6, nunca 0, 1 ou 3.

    A engenharia do Builder descreveu a diferença: 2 é a peça que fica **sempre de pé** (apoiada
    no piso ou na face da parede) e 6 é a que fica **como o usuário lançar** — a curva entre dois
    tubos, de pé, deitada ou de ponta-cabeça.
    """
    em_linha = [cadastro.APL_CONEXAO, cadastro.APL_REGISTRO, 81]          # conexão, registro, pressurizador
    apoiada = [cadastro.APL_BOMBA, cadastro.APL_EVAPORADORA, cadastro.APL_CONDENSADORA,
               cadastro.APL_RESERVATORIO, cadastro.APL_EQUIPAMENTO]
    assert all(cadastro.posicionar_com_ligacao(a) == 6 for a in em_linha)
    assert all(cadastro.posicionar_com_ligacao(a) == 2 for a in apoiada)


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
