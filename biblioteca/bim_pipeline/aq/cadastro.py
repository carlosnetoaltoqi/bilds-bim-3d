"""
cadastro.py — o cadastro de uma peça (`GRUPO_PECA` + `PECA`) montado **num lugar só**.

Os dois escritores de `.aq` — `saida/geo_to_aq.py` (uma peça, "Exportar .aq" do editor) e
`saida/catalogo_to_aq.py` (o catálogo inteiro) — montavam essas duas linhas em duplicata e
**divergiam**: `POSICIONAR_SIMBOLOGIA_3D` 0 num e 3 no outro, `INDICE_SIMBOLO3D_SELECIONADO`
-1 num e 1 no outro. Aqui está a regra única; lá ficou só o que é do formato de origem.

## As três decisões que este módulo toma (ADR-024)

1. **Disciplina** (`GRUPO_PECA.PROJETO_APLICACAO`) — **vem de fora**, escolhida por quem
   importa, nunca inferida do nome. É bitmask (`docs/conhecimento/aplicacoes-builder.md`), e
   uma biblioteca tem uma só (decisão do usuário em 2026-09-10).
2. **Aplicação** (`PECA.TIPO_APLICACAO_PECA`) — vem da **entidade IFC** quando a fonte a
   declara; na falta dela, do vocabulário **da disciplina escolhida**; e na falta dos dois,
   do genérico da disciplina, **com aviso** (nunca em silêncio).
3. **Posicionamento** (`PECA.POSICIONAR_SIMBOLOGIA_3D`) — sai da aplicação, pela tabela
   medida no catálogo oficial, não de um valor fixo.

## De onde vêm os números

Tudo aqui foi medido no catálogo oficial do Builder (`Catalog.db`, schema 625, 31.611 peças,
3.929 grupos — ver `docs/conhecimento/aq-formato.md` §"As duas fontes externas de verdade").
Onde a medição é fraca, o comentário diz. Nada foi inventado: o que a medição não decide sai
como sentinela e aviso, não como palpite.
"""
import re
import unicodedata

from bim_pipeline.aq.aq_writer import (MANNING_PVC, RUGOSIDADE_EQUIV_PVC, RUGOSIDADE_PVC,
                                       SENT_INT, SENT_REAL, TIPO_FWH_PVC)


# ── 1. Disciplina — `GRUPO_PECA.PROJETO_APLICACAO` ────────────────────────────
#
# Bitmask, não enum. Os bits saíram das aplicações que caem em cada valor puro no catálogo
# oficial; os valores gravados são os que o catálogo usa de fato para cada disciplina —
# incêndio é 20 (=4+16, incêndio **com água**) e gás é 36 (=4+32), porque a rede desses dois
# projetos é hidráulica. Água fria é 4 puro: o 12 que gravávamos é 4+8, hidráulico **mais
# sanitário**, e punha toda peça de água fria também no esgoto.
BIT_HIDRAULICO = 4
BIT_SANITARIO = 8
BIT_INCENDIO = 16
BIT_GAS = 32
BIT_ELETRICO = 64
BIT_SPDA = 256
BIT_CLIMATIZACAO = 512

DISCIPLINAS = {
    'hidraulico':   dict(mascara=BIT_HIDRAULICO, rotulo='Hidráulico (água fria e quente)'),
    'sanitario':    dict(mascara=BIT_SANITARIO, rotulo='Sanitário (esgoto e pluvial)'),
    'incendio':     dict(mascara=BIT_HIDRAULICO | BIT_INCENDIO, rotulo='Incêndio'),
    'gas':          dict(mascara=BIT_HIDRAULICO | BIT_GAS, rotulo='Gás'),
    'eletrico':     dict(mascara=BIT_ELETRICO, rotulo='Elétrico (força, cabeamento, fotovoltaico)'),
    'spda':         dict(mascara=BIT_SPDA, rotulo='SPDA e aterramento'),
    'climatizacao': dict(mascara=BIT_CLIMATIZACAO, rotulo='Climatização'),
}


def mascara_da_disciplina(disciplina):
    """Slug da disciplina → `PROJETO_APLICACAO`. Levanta se o slug não existe."""
    try:
        return DISCIPLINAS[disciplina]['mascara']
    except KeyError:
        raise ValueError(
            f'disciplina {disciplina!r} desconhecida; as sete são '
            + ', '.join(sorted(DISCIPLINAS)))


# ── 2. Aplicação — `PECA.TIPO_APLICACAO_PECA` ─────────────────────────────────
#
# O enum vai de 1 a 84 e está nomeado em `docs/conhecimento/aplicacoes-builder.md`. Só as
# constantes usadas aqui ganham nome.
APL_TUBO = 1
APL_CONEXAO = 2
APL_REGISTRO = 3
APL_UTILIZACAO = 4
APL_BOMBA = 6
APL_APARELHO = 8
APL_CAIXA = 9
APL_RALO = 10
APL_PECA_GAS = 12
APL_REGULADOR_ALTA = 13
APL_CENTRAL_GAS = 14
APL_REGULADOR_BAIXA = 15
APL_HIDRANTE = 16
APL_SPRINKLER = 17
APL_AQUECEDOR_PASSAGEM = 25
APL_RESERVATORIO = 27
APL_DISPOSITIVO_ELETRICO = 31
APL_QUADRO_DISTRIBUICAO = 32
APL_QUADRO_MEDICAO = 34
APL_ENTRADA_SERVICO = 36
APL_CAIXA_PASSAGEM_ELETRICA = 37
APL_RACK = 38
APL_COMPONENTE = 41
APL_CONECTOR = 43
APL_CAIXA_INSPECAO_SPDA = 46
APL_CAPTOR = 47
APL_HASTE_ATERRAMENTO = 48
APL_ISOLADOR = 49
APL_RAMAL_VENTILACAO = 55
APL_EXTINTOR = 64
APL_SINALIZACAO = 67
APL_EQUIPAMENTO = 68
APL_EVAPORADORA = 69
APL_CONDENSADORA = 70
APL_EXAUSTOR = 71
APL_DUTO_CLIMATIZACAO = 72
APL_VALVULA_BLOQUEIO = 75
APL_MODULO_FOTOVOLTAICO = 77
APL_PRESSURIZADOR = 81

# O genérico de cada disciplina: onde a peça cai quando nem a entidade IFC nem o vocabulário
# resolvem. Não existe "aplicação nenhuma" no enum — o que existe é escolher o valor mais
# comum da disciplina e **avisar**, que é o que `Diagnostico` faz.
GENERICO_DA_DISCIPLINA = {
    'hidraulico':   APL_CONEXAO,
    'sanitario':    APL_CONEXAO,
    'incendio':     APL_CONEXAO,
    'gas':          APL_CONEXAO,
    'eletrico':     APL_DISPOSITIVO_ELETRICO,
    'spda':         APL_COMPONENTE,
    'climatizacao': APL_EQUIPAMENTO,
}


# ── A ponte da entidade IFC ───────────────────────────────────────────────────
#
# `ENTIDADE_IFC` é o que uma fonte que não conhece o vocabulário do Builder (um IFC, uma
# família Revit, um catálogo de plugin) sempre tem. Cada entidade traz junto o
# `TIPO_ENTIDADE_IFC` e o `ENTIDADE_IFC_2X3`, que andam colados a ela: os três valores são o
# par dominante medido no catálogo oficial, e em 26 das 31 entidades com mais de 30 peças o
# par é único (100 %).
#
# entidade: (tipo_entidade, entidade_2x3, subtipo_padrao, aplicacao_dominante)
IFC = {
    2048: (4125, 2089, 0, APL_DISPOSITIVO_ELETRICO),
    2049: (4115, 2090, 0, APL_AQUECEDOR_PASSAGEM),   # 23/24/25 aquecedor; 25 é o de passagem
    2050: (4127, 2087, 1, APL_PECA_GAS),
    2051: (4100, 2088, 0, APL_CONEXAO),              # eletrocalha/perfilado: 5.246 de 5.265
    2052: (4097, 2086, 1, APL_TUBO),                 # 100 %
    2053: (4101, 2088, 6, 57),                       # patch cord
    2054: (4098, 2086, 2, APL_TUBO),                 # 100 %
    2055: (4112, 2089, 10, 44),                      # caixa de cabeamento
    2059: (4106, 2091, 0, APL_QUADRO_MEDICAO),
    2060: (4128, 2094, 0, 76),                       # bateria
    2064: (4120, 2092, 3, APL_SPRINKLER),            # 17 sprinkler 1.445 / 16 hidrante 96
    2065: (4102, 2091, 0, APL_ENTRADA_SERVICO),
    2067: (4132, 2088, 1, APL_DISPOSITIVO_ELETRICO),
    2069: (4109, 2092, 1, APL_DISPOSITIVO_ELETRICO),  # 100 %
    2071: (4099, 2088, 4, APL_CONEXAO),              # IfcPipeFitting hidráulico
    2072: (4096, 2086, 3, APL_TUBO),                 # IfcPipeSegment, 100 %
    2073: (4105, 2091, 0, APL_COMPONENTE),           # 41 componente / 47 captor (SPDA)
    2075: (4118, 2093, 5, APL_BOMBA),
    2076: (4122, 2092, 10, APL_UTILIZACAO),          # 4 utilização / 8 aparelho sanitário
    2078: (4114, 2094, 1, APL_MODULO_FOTOVOLTAICO),
    2079: (4121, 2092, 1, APL_RAMAL_VENTILACAO),     # terminal de ventilação
    2080: (4104, 2091, 6, APL_DISPOSITIVO_ELETRICO),
    2081: (4119, 2094, 5, APL_RESERVATORIO),
    2084: (4103, 2091, 13, APL_REGISTRO),
    2085: (4123, 2092, 0, APL_CAIXA),                # ralo, caixa sifonada
    2086: (4099, 2086, 8, APL_TUBO),                 # 100 %
    2087: (4133, 2087, 1, APL_CONEXAO),            # supertipo: conexão em 56 % das 1.024
                                                   # peças do catálogo e em 212/212 de uma nativa
    2090: (4113, 2090, 2, 60),                       # inversor
    2096: (4147, 2092, 0, APL_DUTO_CLIMATIZACAO),
    2102: (4152, 2090, 0, APL_CONDENSADORA),         # 100 %
    2106: (4156, 2088, 1, APL_CONEXAO),
    2111: (4161, 2090, 0, APL_EVAPORADORA),          # 100 %
    # As dez que faltavam, medidas em 2026-09-11 no catálogo oficial (2 a 26 peças cada).
    # Fora ficou só a 2057, cujos dois grupos trazem `TIPO_ENTIDADE_IFC = 0` — cadastro
    # incompleto do próprio catálogo, que não serve de padrão para ninguém.
    2058: (4111, 2092, 14, APL_DISPOSITIVO_ELETRICO),  # IfcElectricAppliance
    2061: (4107, 2091, 0, APL_DISPOSITIVO_ELETRICO),   # IfcElectricTimeControl
    2063: (4116, 2095, 5, 54),                         # IfcFilter — filtro de água da chuva
    2066: (4124, 2092, 2, 30),                         # IfcInterceptor — caixa de gordura
    2070: (4108, 2092, 2, APL_DISPOSITIVO_ELETRICO),   # IfcOutlet
    2077: (4131, 2089, 0, APL_DISPOSITIVO_ELETRICO),   # IfcSensor
    2082: (4113, 2090, 4, 35),                         # IfcTransformer
    2083: (4126, 2087, 1, APL_DISPOSITIVO_ELETRICO),   # IfcUnitaryControlElement
    2092: (4122, 2092, 11, APL_EQUIPAMENTO),           # IfcSanitaryTerminal (louça)
}

# Os supertipos abstratos do IFC (`IfcDistributionFlowElement`, `IfcFlowFitting`,
# `IfcBuildingElementProxy` e os outros do fim da lista da ajuda, tipos 4133…4142). Uma fonte
# que declara um deles **não disse o que a peça é** — disse que é um elemento de instalação.
# Por isso eles não vencem o nome: servem de rede, quando o vocabulário também não sabe.
TIPOS_SUPERTIPO = frozenset(range(4133, 4143))

# Onde a entidade sozinha não decide, a **disciplina** desempata. São os três casos medidos em
# que o segundo valor não é ruído: captor de SPDA contra componente elétrico, hidrante contra
# sprinkler, aparelho sanitário contra peça de utilização.
APLICACAO_POR_IFC_E_DISCIPLINA = {
    (2073, 'spda'): APL_CAPTOR,
    (2076, 'sanitario'): APL_APARELHO,
}


def _sem_acento(texto):
    nfd = unicodedata.normalize('NFD', texto or '')
    return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn').upper()


# ── O vocabulário, agora **um por disciplina** ────────────────────────────────
#
# A primeira regra que casa (palavra inteira) vence. Cada entrada é
# (palavras, entidade_ifc, subtipo_ifc, aplicacao); o subtipo `None` usa o padrão da entidade.
#
# O vocabulário hidráulico é o antigo `aq_writer.REGRAS_GRUPO`, sem perda: nasceu calibrado
# contra os 192 grupos com 3D de uma biblioteca de conexões real (reproduz 189). O que mudou
# é que ele deixou de ser o vocabulário de **todas** as disciplinas — era isso que fazia uma
# válvula de HVAC e um aquecedor a gás saírem cadastrados como "Conexão", que é o defeito que
# a engenharia do Builder encontrou. Os outros seis saíram dos nomes de grupo mais frequentes
# de cada aplicação no catálogo oficial.
_HIDRAULICO = (
    (('TUBO',),                                      2072, 3, APL_TUBO),
    (('BOMBA', 'PRESSURIZADOR', 'MOTOBOMBA'),        2075, 5, APL_BOMBA),
    (('CAIXA SIFONADA',),                            2085, 1, APL_CAIXA),
    (('GRELHA',),                                    2076, 3, APL_APARELHO),
    (('RALO', 'RALOS'),                              2085, 0, APL_RALO),
    (('MAQUINA',),                                   2076, 10, APL_APARELHO),
    (('CHUVEIRO',),                                  2076, 3, APL_APARELHO),
    (('PIA', 'LAVATORIO', 'TANQUE', 'VASO', 'KIT'),  2076, 4, APL_APARELHO),
    (('SIFAO',),                                     2071, 3, APL_CONEXAO),
    (('TERMINAL DE VENTILACAO',),                    2079, 1, APL_RAMAL_VENTILACAO),
    (('RESERVATORIO', 'CAIXA DAGUA', 'CISTERNA'),    2081, 5, APL_RESERVATORIO),
    (('AQUECEDOR', 'BOILER'),                        2049, 0, APL_AQUECEDOR_PASSAGEM),
    (('VALVULA', 'REGISTRO', 'TORNEIRA', 'BOIA', 'HIDROMETRO'), 2084, 13, APL_REGISTRO),
    (('JUNCAO', 'TE'),                               2071, 4, APL_CONEXAO),
    (('CURVA', 'JOELHO', 'TRANSPOSICAO'),            2071, 0, APL_CONEXAO),
    (('CAP', 'PLUG', 'ESPUDE', 'TAMPAO'),            2071, 3, APL_CONEXAO),
    (('REDUCAO', 'BUCHA'),                           2071, 6, APL_CONEXAO),
    (('LUVA', 'UNIAO', 'NIPEL', 'ANEL', 'ENGATE', 'ADAPTADOR'), 2071, 1, APL_CONEXAO),
)

_SANITARIO = (
    (('TUBO', 'CALHA'),                              2052, 1, APL_TUBO),
    (('CAIXA SIFONADA',),                            2085, 1, APL_CAIXA),
    (('CAIXA DE GORDURA',),                          2085, 0, 30),
    (('CAIXA DE PASSAGEM', 'POCO DE VISITA'),        2085, 0, 58),
    (('RALO', 'RALOS'),                              2085, 0, APL_RALO),
    (('RAMAL DE VENTILACAO', 'RAMAIS DE VENTILACAO'), 2071, 7, APL_RAMAL_VENTILACAO),
    (('TERMINAL DE VENTILACAO',),                    2079, 1, APL_RAMAL_VENTILACAO),
    (('PIA', 'LAVATORIO', 'TANQUE', 'VASO', 'MICTORIO', 'BIDE'), 2076, 4, APL_APARELHO),
    (('MAQUINA', 'CHUVEIRO'),                        2076, 10, APL_APARELHO),
    (('TANQUE SEPTICO', 'FOSSA'),                    2087, 1, 18),
    (('FILTRO ANAEROBIO',),                          2087, 1, 19),
    (('SUMIDOURO',),                                 2087, 1, 22),
    (('VALVULA', 'REGISTRO'),                        2084, 13, APL_REGISTRO),
    (('JUNCAO', 'TE'),                               2071, 4, APL_CONEXAO),
    (('CURVA', 'JOELHO'),                            2071, 0, APL_CONEXAO),
    (('CAP', 'PLUG', 'TAMPAO'),                      2071, 3, APL_CONEXAO),
    (('REDUCAO', 'BUCHA'),                           2071, 6, APL_CONEXAO),
    (('LUVA', 'UNIAO', 'ADAPTADOR', 'ANEL'),         2071, 1, APL_CONEXAO),
)

_INCENDIO = (
    (('TUBO',),                                      2052, 1, APL_TUBO),
    (('SPRINKLER', 'CHUVEIRO AUTOMATICO'),           2064, 3, APL_SPRINKLER),
    (('HIDRANTE', 'MANGOTINHO'),                     2064, 1, APL_HIDRANTE),
    (('EXTINTOR',),                                  2064, 6, APL_EXTINTOR),
    (('ALARME',),                                    2064, 6, 65),
    (('ILUMINACAO DE EMERGENCIA',),                  2064, 6, 66),
    (('SINALIZACAO', 'SAIDA DE EMERGENCIA'),         2064, 6, APL_SINALIZACAO),
    (('BOMBA', 'JOCKEY', 'MOTOBOMBA'),               2075, 5, APL_BOMBA),
    (('RESERVATORIO', 'CAIXA DAGUA'),                2081, 5, APL_RESERVATORIO),
    (('VALVULA', 'REGISTRO'),                        2084, 13, APL_REGISTRO),
    (('JUNCAO', 'TE'),                               2071, 4, APL_CONEXAO),
    (('CURVA', 'JOELHO'),                            2071, 0, APL_CONEXAO),
    (('REDUCAO', 'BUCHA'),                           2071, 6, APL_CONEXAO),
    (('LUVA', 'UNIAO', 'NIPEL', 'ADAPTADOR'),        2071, 1, APL_CONEXAO),
)

_GAS = (
    (('TUBO',),                                      2052, 1, APL_TUBO),
    (('REGULADOR DE ALTA', 'ALTA PRESSAO'),          2084, 17, APL_REGULADOR_ALTA),
    (('REGULADOR DE BAIXA', 'BAIXA PRESSAO', 'MEDIDOR'), 2065, 1, APL_REGULADOR_BAIXA),
    (('CENTRAL DE GAS', 'CILINDRO'),                 2087, 1, APL_CENTRAL_GAS),
    (('AQUECEDOR', 'BOILER'),                        2050, 1, APL_PECA_GAS),
    (('DISTRIBUIDOR',),                              2071, 4, 78),
    (('VALVULA', 'REGISTRO'),                        2084, 13, APL_REGISTRO),
    (('JUNCAO', 'TE'),                               2071, 4, APL_CONEXAO),
    (('CURVA', 'JOELHO'),                            2071, 0, APL_CONEXAO),
    (('REDUCAO', 'BUCHA'),                           2071, 6, APL_CONEXAO),
    (('LUVA', 'UNIAO', 'NIPEL', 'ADAPTADOR'),        2071, 1, APL_CONEXAO),
)

_ELETRICO = (
    (('ELETROCALHA', 'PERFILADO', 'LEITO', 'ELETRODUTO', 'BARRAMENTO BLINDADO',
      'SUSPENSAO', 'CANALETA'),                      2052, 1, APL_TUBO),
    (('TOMADA', 'INTERRUPTOR', 'CONDULETE', 'LUMINARIA', 'PONTO DE LUZ',
      'SENSOR', 'CAMPAINHA'),                        2067, 1, APL_DISPOSITIVO_ELETRICO),
    (('QUADRO DE DISTRIBUICAO', 'CAIXA DE DERIVACAO', 'UNIDADE DE DERIVACAO', 'COFRE'),
                                                     2059, 1, APL_QUADRO_DISTRIBUICAO),
    (('QUADRO DE MEDICAO', 'MEDICAO'),               2059, 0, APL_QUADRO_MEDICAO),
    (('ENTRADA DE SERVICO', 'ANCORAGEM', 'POSTE', 'RAMAL DE ENTRADA'),
                                                     2065, 0, APL_ENTRADA_SERVICO),
    (('CAIXA DE PASSAGEM',),                         2067, 1, APL_CAIXA_PASSAGEM_ELETRICA),
    (('RACK', 'GABINETE'),                           2067, 1, APL_RACK),
    (('PATCH CORD', 'PATCH PANEL'),                  2053, 6, 57),
    (('DIO', 'BASTIDOR', 'DISTRIBUIDOR OPTICO'),     2055, 10, 44),
    (('DISJUNTOR', 'DPS', 'CONTATOR', 'RELE', 'FUSIVEL'), 2073, 0, APL_COMPONENTE),
    (('CONECTOR',),                                  2073, 0, APL_CONECTOR),
    (('INVERSOR', 'CONTROLADOR DE CARGA'),           2090, 2, 60),
    (('MODULO FOTOVOLTAICO', 'PAINEL FOTOVOLTAICO', 'PLACA SOLAR'), 2078, 1, APL_MODULO_FOTOVOLTAICO),
    (('BATERIA', 'NOBREAK'),                         2060, 0, 76),
    (('GERADOR',),                                   2087, 1, 84),
    (('TRANSFORMADOR', 'ESTABILIZADOR'),             2087, 1, 35),
    (('CURVA', 'JOELHO', 'COTOVELO', 'TE', 'T', 'JUNCAO', 'REDUCAO', 'FLANGE',
      'TERMINAL', 'CRUZETA', 'DERIVACAO'),           2051, 0, APL_CONEXAO),
)

_SPDA = (
    (('CABO', 'RE-BAR', 'CORDOALHA', 'FITA', 'MASTRO'), 2052, 1, APL_TUBO),
    (('CAPTOR', 'TERMINAL AEREO', 'FRANKLIN'),       2073, 7, APL_CAPTOR),
    (('ISOLADOR',),                                  2073, 7, APL_ISOLADOR),
    (('HASTE', 'ATERRAMENTO'),                       2073, 7, APL_HASTE_ATERRAMENTO),
    (('CAIXA DE INSPECAO',),                         2067, 2, APL_CAIXA_INSPECAO_SPDA),
    (('BARRAMENTO', 'EQUIPOTENCIALIZACAO', 'BEP'),   2073, 7, 50),
    (('DUTO DE PROTECAO', 'PROTECAO MECANICA'),      2053, 6, 51),
    (('CONECTOR', 'CLIP', 'PRESILHA', 'SUPORTE'),    2073, 0, APL_COMPONENTE),
)

_CLIMATIZACAO = (
    (('DUTO', 'DUTOS'),                              2096, 0, APL_DUTO_CLIMATIZACAO),
    (('CONDENSADORA', 'VRF', 'CONDENSADORAS'),       2102, 0, APL_CONDENSADORA),
    (('EVAPORADORA', 'CASSETE', 'EVAPORADORAS', 'SPLIT', 'FANCOIL'),
                                                     2111, 0, APL_EVAPORADORA),
    (('EXAUSTOR', 'VENTILADOR'),                     2096, 0, APL_EXAUSTOR),
    (('CAIXA DE DISTRIBUICAO', 'PLENUM'),            2096, 0, 73),
    (('BOMBA DE DRENO', 'BOMBA PARA DRENAGEM', 'DRENO'), 2096, 0, 74),
    (('VALVULA', 'ATUADOR', 'REGISTRO'),             2084, 13, APL_VALVULA_BLOQUEIO),
    (('TUBO', 'LINHA FRIGORIGENA'),                  2052, 1, APL_TUBO),
    (('CURVA', 'JOELHO', 'COTOVELO', 'TE', 'T', 'JUNCAO', 'REDUCAO', 'LUVA', 'CAP'),
                                                     2071, 1, APL_CONEXAO),
)

VOCABULARIO = {
    'hidraulico': _HIDRAULICO,
    'sanitario': _SANITARIO,
    'incendio': _INCENDIO,
    'gas': _GAS,
    'eletrico': _ELETRICO,
    'spda': _SPDA,
    'climatizacao': _CLIMATIZACAO,
}


# ── O nome pode chegar em inglês ──────────────────────────────────────────────
#
# Família Revit de fabricante internacional nomeia tudo em inglês (`Actuator - MP500C`,
# `PIBCV Valves`, `Pipe Accessories`). Medido no Builder em 2026-09-11: uma biblioteca de
# válvulas e atuadores de HVAC saiu **inteira** como "Elemento genérico" (aplicação 68) porque
# nenhuma palavra do vocabulário casou — o Builder recebeu, corretamente, o nosso "não sei".
#
# A tradução acontece **antes** do casamento, num lugar só, em vez de duplicar cada termo nos
# sete vocabulários: assim os dois idiomas dão exatamente a mesma classificação, e uma regra
# nova em português vale para o inglês de graça. Só entram termos cujo equivalente já existe
# em alguma regra — nada aqui inventa classificação.
SINONIMOS_EN = {
    'PIPE': 'TUBO', 'TUBING': 'TUBO', 'DUCT': 'DUTO', 'DUCTWORK': 'DUTO',
    'ELBOW': 'CURVA', 'BEND': 'CURVA', 'TEE': 'TE', 'WYE': 'JUNCAO', 'CROSS': 'CRUZETA',
    'REDUCER': 'REDUCAO', 'COUPLING': 'LUVA', 'UNION': 'UNIAO', 'ADAPTER': 'ADAPTADOR',
    'NIPPLE': 'NIPEL', 'PLUG': 'PLUG', 'FITTING': 'CONEXAO', 'FITTINGS': 'CONEXAO',
    'VALVE': 'VALVULA', 'ACTUATOR': 'ATUADOR', 'DAMPER': 'REGISTRO',
    'PUMP': 'BOMBA', 'BOOSTER': 'PRESSURIZADOR', 'TANK': 'RESERVATORIO',
    'HEATER': 'AQUECEDOR', 'BOILER': 'AQUECEDOR', 'FAN': 'EXAUSTOR',
    'SPRINKLER': 'SPRINKLER', 'HYDRANT': 'HIDRANTE', 'EXTINGUISHER': 'EXTINTOR',
    'OUTLET': 'TOMADA', 'SOCKET': 'TOMADA', 'SWITCH': 'INTERRUPTOR', 'BREAKER': 'DISJUNTOR',
    'PANEL': 'QUADRO', 'BUSBAR': 'BARRAMENTO', 'CABLE': 'CABO', 'TRAY': 'ELETROCALHA',
    'LUMINAIRE': 'LUMINARIA', 'FIXTURE': 'LUMINARIA', 'SENSOR': 'SENSOR',
    'RACK': 'RACK', 'CABINET': 'GABINETE', 'BATTERY': 'BATERIA', 'INVERTER': 'INVERSOR',
    'TRANSFORMER': 'TRANSFORMADOR', 'GENERATOR': 'GERADOR', 'FILTER': 'FILTRO',
    'STRAINER': 'FILTRO', 'METER': 'HIDROMETRO', 'DRAIN': 'RALO', 'TRAP': 'SIFAO',
    'EVAPORATOR': 'EVAPORADORA', 'CONDENSER': 'CONDENSADORA', 'SPLIT': 'SPLIT',
}
_RX_EN = re.compile(r'\b(' + '|'.join(sorted(SINONIMOS_EN, key=len, reverse=True)) + r')S?\b')


def _traduzir(alvo):
    """Nome já sem acento e em maiúscula → com os termos em inglês trocados pelo equivalente."""
    return _RX_EN.sub(lambda m: SINONIMOS_EN[m.group(1)], alvo)


# ── 3. Posicionamento — `PECA.POSICIONAR_SIMBOLOGIA_3D` ───────────────────────
#
# **Peça com "Pontos de ligação 3D: Sim" só aceita dois modos.** O Cadastro oferece dois itens no
# combo, e o catálogo oficial confirma: das 4.206 peças com `CONEXAO_VOLUMETRICA = 1`, **todas**
# usam 2 ou 6 — nunca 0, 1, 3, 4 ou 5. A engenharia do Builder descreveu o que cada um significa,
# e a medição bate com a descrição:
#
#   2 "Na horizontal, apontando para o ponto diretor" — a peça fica **sempre de pé**: apoiada no
#     piso ou na face da parede. Bomba (26/26), evaporadora (32/32), condensadora (58/58),
#     reservatório (26/26), aquecedor (36/36), elemento genérico (101/102).
#   6 "No plano de lançamento, apontando para o ponto diretor" — a peça fica **como o usuário
#     lançar**: de pé, deitada ou de ponta-cabeça. É a curva entre dois tubos — conexão (288/332),
#     registro (7/12), pressurizador (33/33).
#
# Como o pipeline marca a ligação 3D em toda peça com bocal detectado (ADR-023), é esta regra que
# vale para ela — e não a tabela por aplicação abaixo, que descreve a peça **sem** ligação 3D.
POSICIONAR_APOIADA = 2
POSICIONAR_EM_LINHA = 6

# Quem entra na tubulação em vez de se apoiar. Medido entre as peças com ligação 3D do catálogo.
APLICACOES_EM_LINHA = frozenset({APL_CONEXAO, APL_REGISTRO, 5, APL_DISPOSITIVO_ELETRICO, 81})


def posicionar_com_ligacao(aplicacao):
    """Modo de posicionamento de uma peça **com** "Pontos de ligação 3D" — 6 se entra na
    tubulação, 2 se se apoia. Ver o bloco acima."""
    return POSICIONAR_EM_LINHA if aplicacao in APLICACOES_EM_LINHA else POSICIONAR_APOIADA


#
# O modo diz para onde aponta o eixo X da simbologia quando o Builder monta o 3D a partir do
# croqui: é o que faz a peça **já entrar certa** no projeto. Os sete modos (0…6) estão em
# `docs/conhecimento/aplicacoes-builder.md`. O valor é o dominante de cada aplicação no
# catálogo oficial; onde a dominância é fraca o comentário diz.
#
# Tubo é o único caso de **nulo**, e é regra fechada: 2.104 de 2.104. Conduto não tem
# simbologia a orientar.
POSICIONAR_POR_APLICACAO = {
    APL_TUBO: None,                       # 2.104/2.104
    APL_CONEXAO: 0,                       # 8.039/10.467 — "no plano formado pelos condutos"
    APL_REGISTRO: 1,                      # 353/733
    APL_UTILIZACAO: 1,                    # 370/439
    5: 0, 7: 0,
    APL_BOMBA: 3,                         # 503/588 — "apontando para a tubulação de entrada"
    APL_APARELHO: 0,                      # 72/106
    APL_CAIXA: 2,                         # 12/21 — amostra pequena
    APL_PECA_GAS: 1,                      # 152/280 — fraca, o 0 tem 128
    APL_REGULADOR_ALTA: 0, APL_REGULADOR_BAIXA: 0,
    APL_HIDRANTE: 2,                      # 60/96
    APL_SPRINKLER: 0,                     # 1.278/1.445
    23: 2, 24: 2, APL_AQUECEDOR_PASSAGEM: 2,
    APL_RESERVATORIO: 2,                  # 202/202
    APL_DISPOSITIVO_ELETRICO: 2,          # 1.780/4.583 — dominância fraca (0 tem 1.504)
    APL_QUADRO_DISTRIBUICAO: 2,           # 168/344, com 6 em 166
    APL_QUADRO_MEDICAO: 2,                # 2.623/3.771
    APL_ENTRADA_SERVICO: 0,               # 2.532/2.532
    APL_CAIXA_PASSAGEM_ELETRICA: 2,       # 211/315
    APL_RACK: 0,                          # 305/305
    40: 0,
    APL_COMPONENTE: 0,                    # 1.385/1.385
    44: 0,
    APL_CAIXA_INSPECAO_SPDA: 2,           # 40/40
    APL_CAPTOR: 2,                        # 132/132
    APL_ISOLADOR: 0,                      # 50/50
    53: 2, APL_RAMAL_VENTILACAO: 0, 57: 0, 58: 2, 59: 0,
    60: 2, 61: 2, APL_SINALIZACAO: 2,
    APL_EQUIPAMENTO: 2,                   # 133/134
    APL_EVAPORADORA: 2,                   # 78/78
    APL_CONDENSADORA: 2,                  # 155/155
    APL_DUTO_CLIMATIZACAO: 2,             # 27/27
    76: 2, APL_MODULO_FOTOVOLTAICO: 2, 78: 2, 80: 2,
    APL_PRESSURIZADOR: 6,                 # 33/33
    82: 1, 84: 2,
}

# Aplicação que não está na tabela: 0 ("no plano formado pelos condutos"), que é o modo mais
# comum do catálogo inteiro e o que uma conexão quer.
POSICIONAR_PADRAO = 0


def posicionar_simbologia_3d(aplicacao):
    """`POSICIONAR_SIMBOLOGIA_3D` da aplicação — `None` (coluna nula) para tubo."""
    return POSICIONAR_POR_APLICACAO.get(aplicacao, POSICIONAR_PADRAO)


# ── O código de bitola — `ENTRADA_PECA.DIAMETRO_EP` e `PECA.DIAMETRO_PECA` ────
#
# A escala é **em polegada**, não em milímetro: os códigos 0…17 são o índice de uma lista de
# bitolas nominais em polegada. Medido no catálogo oficial cruzando o código com o nome da
# peça: 1/2"→3 (584 peças), 3/4"→5 (533), 1"→6 (542), 1.1/4"→7 (364), 1.1/2"→8 (363), 2"→9
# (391), 2.1/2"→10 (187), 3"→11 (223), 4"→12 (186), 5"→13 (55), 6"→14 (61), 8"→15 (46),
# 10"→16 (42), 12"→17 (42), e nas pontas 1/4"→0, 3/8"→2, 5/8"→4.
#
# **A tabela antiga estava errada em milímetro.** `{40: 8, 50: 9, 60: 10, 75: 11, …}` é a
# equivalência do **PVC esgoto** — e 60→10 não existe em nenhuma série. Em PVC soldável de
# água fria 40 mm é 1.1/4" (código 7), não 1.1/2"; 50 mm é 1.1/2" (8), não 2".
ESCALA_POLEGADA = {
    0: '1/4', 2: '3/8', 3: '1/2', 4: '5/8', 5: '3/4', 6: '1', 7: '1.1/4', 8: '1.1/2',
    9: '2', 10: '2.1/2', 11: '3', 12: '4', 13: '5', 14: '6', 15: '8', 16: '10', 17: '12',
}
# O código 1 fica de fora: nenhuma peça do catálogo oficial o usa com nome em polegada. Pela
# posição seria 5/16", e escrever isso seria inventar.

CODIGO_POR_POLEGADA = {v: k for k, v in ESCALA_POLEGADA.items()}

# Milímetro → código, só onde a medição é **inequívoca** (uma bitola em mm cai num único
# código no catálogo inteiro). São as séries de cobre (15, 22, 28, 35, 42, 54, 66, 79, 104),
# de aço (60, 63, 73, 80, 89, 114) e as pontas do PVC que não colidem.
MM_INEQUIVOCO = {
    15: 3, 16: 3, 20: 3, 22: 5, 25: 5, 28: 6, 32: 6, 35: 7, 42: 8, 54: 9, 60: 9, 63: 9,
    66: 10, 73: 10, 79: 11, 80: 11, 85: 11, 89: 11, 100: 12, 104: 12, 110: 12, 114: 12,
    120: 13, 125: 13, 150: 14, 200: 15, 225: 16, 250: 16,
}

# Milímetro → código quando **depende da série**, porque a mesma bitola em mm é uma polegada
# em PVC soldável e outra em PVC esgoto. Medido: 40 mm aparece em 7 (80 peças) e em 8 (117);
# 50 mm em 8 (85) e 9 (136); 75 mm em 10 (60) e 11 (152).
MM_POR_SERIE = {
    40: {'soldavel': 7, 'esgoto': 8},
    50: {'soldavel': 8, 'esgoto': 9},
    75: {'soldavel': 10, 'esgoto': 11},
}

# Tolerância da conversão raio medido → bitola nominal (8 %, como em `entradas_aq`).
TOLERANCIA_NOMINAL = 0.08

_POLEGADA = re.compile(r'(?<![\d./])(\d+)(?:[.\s](\d+)/(\d+))?\s*"')
_FRACAO = re.compile(r'(?<![\d./])(\d+)/(\d+)\s*"')


def codigo_de_polegada(texto):
    """Código de bitola da polegada declarada no texto, ou `None` se não houver.

    É o caminho mais confiável: no catálogo oficial a polegada no nome bate com o código sem
    ambiguidade nenhuma, porque a escala **é** em polegada.
    """
    if not texto:
        return None
    # o inteiro vem primeiro: em '1 1/2"' a bitola é 1.1/2", não 1/2".
    m = _POLEGADA.search(texto)
    if m:
        inteiro, num, den = m.group(1), m.group(2), m.group(3)
        chave = f'{inteiro}.{num}/{den}' if num else inteiro
        if chave in CODIGO_POR_POLEGADA:
            return CODIGO_POR_POLEGADA[chave]
    fr = _FRACAO.search(texto)
    if fr:
        return CODIGO_POR_POLEGADA.get(f'{fr.group(1)}/{fr.group(2)}')
    return None


def codigo_de_milimetro(nominal_mm, serie=None):
    """Código de bitola da bitola nominal em mm, ou `None` quando a medição não decide.

    `serie` é `'soldavel'` (PVC água fria) ou `'esgoto'` (PVC série normal) e só é consultada
    nas três bitolas que colidem — 40, 50 e 75 mm. Sem ela, a bitola que colide sai **sem
    código**: gravar o palpite seria pôr a peça na bitola errada em silêncio.
    """
    nominal = int(round(float(nominal_mm)))
    if nominal in MM_INEQUIVOCO:
        return MM_INEQUIVOCO[nominal]
    if nominal in MM_POR_SERIE:
        return MM_POR_SERIE[nominal].get(serie)
    return None


def codigo_de_raio(raio_cm, serie=None):
    """Raio interno medido na malha (cm) → código de bitola, ou `None` fora da escala."""
    diametro_mm = 2.0 * float(raio_cm) * 10.0
    candidatos = set(MM_INEQUIVOCO) | set(MM_POR_SERIE)
    melhor, erro_melhor = None, None
    for nominal in candidatos:
        erro = abs(diametro_mm - nominal) / nominal
        if erro <= TOLERANCIA_NOMINAL and (erro_melhor is None or erro < erro_melhor):
            melhor, erro_melhor = nominal, erro
    if melhor is None:
        return None
    return codigo_de_milimetro(melhor, serie)


SERIES = {
    'soldavel': 'PVC soldável (água fria)',
    'esgoto': 'PVC série normal (esgoto)',
}

_PISTAS_SERIE = (
    ('soldavel', ('SOLDAVEL', 'AGUA FRIA', 'AGUA QUENTE', 'CPVC', 'PPR', 'ROSCAVEL')),
    ('esgoto', ('ESGOTO', 'SERIE NORMAL', 'SERIE REFORCADA', 'PLUVIAL', 'VENTILACAO')),
)


def serie_do_titulo(*textos):
    """`'soldavel'`, `'esgoto'` ou `None` — a série de bitolas declarada no título/linha.

    Só serve para desempatar 40, 50 e 75 mm; não decide disciplina nenhuma (isso é do
    usuário, ADR-024).
    """
    alvo = ' '.join(_sem_acento(t) for t in textos if t)
    for serie, pistas in _PISTAS_SERIE:
        if any(p in alvo for p in pistas):
            return serie
    return None


# ── Diagnóstico — o que a exportação não soube decidir ────────────────────────

class Diagnostico:
    """Coletor dos avisos da exportação: o que caiu no genérico e o que saiu sem bitola.

    Existe porque a decisão de 2026-09-10 é **avisar e gravar o genérico da disciplina**, não
    abortar nem escolher em silêncio. Quem chama despeja isto no resumo da exportação; o
    `validar_aq` confere o mesmo no arquivo pronto.
    """

    def __init__(self):
        self.sem_aplicacao = []       # nomes de grupo que caíram no genérico da disciplina
        self.sem_bitola = []          # (onde, motivo)

    def generico(self, nome_grupo):
        self.sem_aplicacao.append(nome_grupo)

    def bitola(self, onde, motivo):
        self.sem_bitola.append((onde, motivo))

    @property
    def vazio(self):
        return not self.sem_aplicacao and not self.sem_bitola

    def resumo(self):
        """Dict serializável para o JSON de resumo dos escritores."""
        return {
            'gruposSemAplicacao': sorted(set(self.sem_aplicacao)),
            'pecasSemBitola': len(self.sem_bitola),
        }

    def linhas(self):
        """Avisos em texto, um por linha, para o stderr."""
        saida = []
        if self.sem_aplicacao:
            grupos = sorted(set(self.sem_aplicacao))
            saida.append(
                f'aviso: {len(grupos)} grupo(s) sem aplicação reconhecida entraram no genérico '
                f'da disciplina: ' + ', '.join(repr(g) for g in grupos[:8])
                + (' …' if len(grupos) > 8 else ''))
        if self.sem_bitola:
            saida.append(f'aviso: {len(self.sem_bitola)} entrada(s) sem código de bitola '
                         f'(sentinela); a primeira: {self.sem_bitola[0][0]} — {self.sem_bitola[0][1]}')
        return saida


# ── A classificação, na ordem do ADR-024 ──────────────────────────────────────

def classificar(nome, disciplina, entidade_ifc=None, diag=None):
    """(entidade_ifc, tipo_entidade, entidade_2x3, subtipo, aplicacao) de um grupo.

    A ordem é a do ADR-024:

    1. **entidade IFC declarada pela fonte** — a classe IFC de uma família Revit, de um IFC, de
       um catálogo de plugin ou do `.aq` de origem, quando ela **diz o que a peça é**. Supertipo
       abstrato (`TIPOS_SUPERTIPO`) não diz, e por isso não vence o nome: espera no degrau 3;
    2. **vocabulário da disciplina escolhida** — nunca o de outra disciplina;
    3. **genérico da disciplina, com aviso** em `diag`.
    """
    mascara_da_disciplina(disciplina)          # valida o slug antes de qualquer coisa

    declarada = entidade_ifc if entidade_ifc in IFC else None
    if declarada is not None and IFC[declarada][0] not in TIPOS_SUPERTIPO:
        tipo, e23, sub, apl = IFC[declarada]
        apl = APLICACAO_POR_IFC_E_DISCIPLINA.get((declarada, disciplina), apl)
        return declarada, tipo, e23, sub, apl

    alvo = _traduzir(_sem_acento(nome))
    for chaves, ent, sub, apl in VOCABULARIO[disciplina]:
        # o `S?` é o plural: no catálogo oficial o nome de grupo mais comum do tubo é
        # literalmente "Tubos", e `\bTUBO\b` não casa com ele. Plural irregular
        # ('ANEL'/'ANEIS') continua fora, e é por isso que 'RALO'/'RALOS' está escrito à mão.
        if any(re.search(rf'\b{re.escape(k)}S?\b', alvo) for k in chaves):
            tipo, e23, sub_padrao, _ = IFC[ent]
            return ent, tipo, e23, sub if sub is not None else sub_padrao, apl

    if diag is not None:
        diag.generico(nome)

    # Supertipo declarado e nome que não diz nada: fica o supertipo, que ao menos é o que a
    # fonte afirmou — melhor que trocá-lo pelo genérico da disciplina, que é palpite nosso.
    if declarada is not None:
        tipo, e23, sub, apl = IFC[declarada]
        return declarada, tipo, e23, sub, APLICACAO_POR_IFC_E_DISCIPLINA.get(
            (declarada, disciplina), apl)

    apl = GENERICO_DA_DISCIPLINA[disciplina]
    ent = 2067 if disciplina in ('eletrico', 'spda') else 2071
    if disciplina == 'climatizacao':
        ent = 2087
    tipo, e23, sub, _ = IFC[ent]
    return ent, tipo, e23, sub, apl


# ── As duas linhas do cadastro ────────────────────────────────────────────────

def linha_grupo(*, id_grupo, nome, disciplina, id_classe, entidade_ifc=None, diag=None):
    """Campos de `GRUPO_PECA` — o dict que vai direto para `EscritorAq.ins`.

    Devolve `(campos, aplicacao)`: a aplicação sai daqui porque é ela que decide o
    `TIPO_APLICACAO_PECA` e o `POSICIONAR_SIMBOLOGIA_3D` das peças do grupo.
    """
    ent, tipo, e23, sub, apl = classificar(nome, disciplina, entidade_ifc, diag)
    tubo = apl == APL_TUBO
    campos = dict(
        ID_GRUPO_PECA=id_grupo, NOME_GP=nome, TIPO_SECAO_GP=0,
        RUGOSIDADE_GP=RUGOSIDADE_PVC, RUGOSIDADE_EQUIVALENTE=RUGOSIDADE_EQUIV_PVC,
        TIPO_FWH=TIPO_FWH_PVC, COEFICIENTE_MANNING=MANNING_PVC,
        TIPO_MATERIAL=0, PROJETO_APLICACAO=mascara_da_disciplina(disciplina),
        ELEMENTO_APLICACAO=1 if tubo else 0, TIPO_CONFIGURACAO_GP=SENT_INT,
        REPRESENTACAO_GP=2 if tubo else 0, ID_CLASSE_PECA=id_classe, CODIGO_ELLO=0, ATIVO=1,
        ENTIDADE_IFC=ent, SUBTIPO_IFC=sub, TIPO_ENTIDADE_IFC=tipo,
        ENTIDADE_IFC_2X3=e23, SUBTIPO_IFC_2X3=sub, TIPO_ENTIDADE_IFC_2X3=tipo)
    return campos, apl


def linha_peca(*, id_peca, nome, id_grupo, aplicacao, fabricante, descricao,
               indicacao=None, descricao_simbologia=None,
               comprimento=None, diametro=None):
    """Campos de `PECA` — o dict que vai direto para `EscritorAq.ins`.

    O que aqui é regra, e antes divergia entre os dois escritores:

    - `POSICIONAR_SIMBOLOGIA_3D` sai da aplicação (`posicionar_simbologia_3d`), não é fixo;
    - `INDICE_SIMBOLO3D_SELECIONADO` é **-1**, o *default* do próprio schema — o `1` que o
      `catalogo_to_aq` gravava aponta para um símbolo que pode não existir;
    - `CONEXAO_VOLUMETRICA` entra em 0 e é ligado depois por
      `entradas_aq.marcar_pontos_de_ligacao`, que é quem sabe se a peça ganhou entrada.
    """
    campos = dict(
        ID_PECA=id_peca, NOME_PECA=nome, BIBLIOTECA=fabricante, SIMBOLO_SELECIONADO=1,
        DESCRICAO_DADOS=descricao, POSICIONAR_SIMBOLOGIA=0, POSICAO_DADOS=0,
        INDICACAO_DADOS=indicacao if indicacao is not None else nome,
        POSICIONA_CAMPOS=1, DESENHA_SIMBOLOGIA=2,
        DIAMETRO_PECA=diametro if diametro is not None else SENT_REAL,
        COMPRIMENTO_PECA=comprimento if comprimento is not None else SENT_REAL,
        ID_GRUPO_PECA=id_grupo, TIPO_APLICACAO_PECA=aplicacao, CODIGO_ELLO=0, ATIVO=1,
        POSICIONAR_SIMBOLOGIA_3D=posicionar_simbologia_3d(aplicacao),
        FORMATO_PECA=-1, OPCAO_RENDERIZACAO_PLANIFICADA=0,
        INCLUIR_REPRESENTACAO3D_PARAMETRICA=0, CONEXAO_VOLUMETRICA=0,
        INDICE_SIMBOLO3D_SELECIONADO=-1)
    if descricao_simbologia is not None:
        campos['DESCRICAO_DADOS_SIMBOLOGIA'] = descricao_simbologia
    return campos
