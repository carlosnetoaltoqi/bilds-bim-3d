# Aplicação e projeto — como o Builder classifica uma peça

Duas colunas decidem **onde uma peça aparece** no AltoQi Builder: em que disciplina ela é oferecida e
como o programa a trata no lançamento. Errá-las é o defeito mais silencioso da exportação — a peça
abre, desenha, e mesmo assim está no lugar errado do cadastro (peça elétrica sendo oferecida como
conexão hidráulica).

| coluna | tabela | o que é |
|---|---|---|
| `PROJETO_APLICACAO` | `GRUPO_PECA` | **bitmask** de disciplinas em que o grupo é oferecido |
| `TIPO_APLICACAO_PECA` | `PECA` | **enum 1…84**: o papel da peça dentro da disciplina |
| `ENTIDADE_IFC` (+ `SUBTIPO_IFC` e as duas irmãs 2X3) | `GRUPO_PECA` | a classe IFC exportada; anda junto com a aplicação |

Tudo aqui foi medido no **catálogo oficial do Builder** (`Catalog.db`, schema 625, **31.611 peças**,
3.929 grupos, 203 classes) e conferido contra a ajuda do programa (`peca.htm`). O que é inferência e
não medição está marcado.

## `PROJETO_APLICACAO` é bitmask, não enum

Os valores observados são somas: 4, 8, 12, 16, 18, 20, 28, 32, 36, 52, 60, 64, 146, 256, 320, 512,
516, 564, 576, 1022. Os bits, deduzidos pelas aplicações que caem em cada um:

| bit | disciplina | como se sabe |
|---|---|---|
| 4 | **hidráulico** | 4 puro traz aquecedor, placa solar, pressurizador, filtro de piscina |
| 8 | **sanitário / esgoto / pluvial** | 8 puro traz tanque séptico, filtro anaeróbio, valas, sumidouro, ramal de ventilação |
| 16 | **incêndio** | 16 puro traz hidrante, sprinkler, extintor, alarme, iluminação de emergência |
| 32 | **gás** | 32 puro traz regulador de alta e de baixa pressão, central de gás |
| 64 | **elétrico / fiação** (inclui cabeamento e fotovoltaico) | 64 puro traz quadro, tomada, disjuntor, rack, patch cord, inversor, módulo fotovoltaico |
| 256 | **SPDA** | 256 puro traz captor, isolador, haste de aterramento, duto de proteção |
| 512 | **climatização** | 512 puro traz evaporadora, condensadora, exaustor, duto |
| 2 e 128 | **não identificados** | só aparecem em 146 (=2+16+128) e 1022 (tudo), ambos com louça sanitária |

Combinações são a regra, não a exceção: **52 = 4+16+32** é a conexão de PVC/metal que serve água,
incêndio e gás (2.547 peças); **20 = 4+16** são reservatórios; **12 = 4+8** caixa coletora;
**36 = 4+32** aquecedor e distribuidor PEX; **320 = 64+256** aterramento, que é dos dois;
**576 = 64+512** eletrocalha que serve elétrica e climatização.

> **O que nosso escritor grava está errado em dois dos quatro valores.** `aq_writer` usa
> `APLICACAO_AGUA_FRIA = 12` (que é hidráulico **+ sanitário**; água fria pura é **4**) e
> `APLICACAO_INCENDIO = 22` (= 2+4+16, com o bit 2 não identificado; incêndio com água é **20**, e
> incêndio puro é **16**). `APLICACAO_ESGOTO = 8` e `APLICACAO_GAS = 36` batem com o catálogo.

## `TIPO_APLICACAO_PECA` — o enum 1…84

Nomes vindos da tabela "Projeto × Aplicações" de `peca.htm` cruzada com o `NOME_CP` da classe e os
nomes de grupo mais frequentes de cada valor no catálogo. Marcados com ~ os que a ajuda não nomeia
diretamente e cujo nome saiu da classe.

| # | aplicação | projeto(s) | peças | exemplo de grupo |
|---|---|---|---|---|
| 1 | Tubo / conduto (eletrocalha, leito, barramento) | 64, 256, 512, 52 | 2.104 | Suspensão vertical; Tubos |
| 2 | **Conexão** | 64, 52, 8, 16 | 10.467 | Redução concêntrica; Tê |
| 3 | **Registro** / válvula | 52, 60, 20, 4 | 733 | Válvula de gaveta |
| 4 | Peça de utilização | 4, 516 | 439 | Pia de cozinha com Tê de 90º |
| 5 | Tomada d'água | 20, 4, 52 | 68 | Tomadas d'água |
| 6 | Bomba hidráulica | 16, 12, 4, 8 | 588 | (modelos de bomba) |
| 7 | Alimentador predial | 4, 20 | 23 | Alimentador Predial |
| 8 | Aparelho sanitário | 8 | 106 | Pia de Cozinha Residencial |
| 9 | Caixa sifonada | 8 | 21 | Caixa Sifonada; Chuveiro |
| 10 | Ralo / coletor pluvial | 8 | 11 | Ralos pluviais |
| 11 | Caixa de passagem (sanitário) | 8 | 7 | Caixa de passagem; Caixa de gordura |
| 12 | ~Peça de gás — aquecedor com conexão | 32, 36 | 280 | Aquecedor de passagem 30 L/min c/ Tê |
| 13 | Regulador primário (alta pressão) | 32 | 24 | Regulador de alta pressão GN |
| 14 | Alimentador de gás / central | 32 | 17 | Central de gás; Cilindro de gás |
| 15 | Regulador secundário (baixa pressão) | 32 | 72 | Regulador de baixa pressão + UPSO |
| 16 | Hidrante | 16 | 96 | Hidrante — mangueira 2.1/2 |
| 17 | Sprinkler | 16, 52 | 1.445 | Sprinkler DN20 — K242 |
| 18 | Tanque séptico | 8 | 2 | Tanques sépticos |
| 19 | Filtro anaeróbio | 8 | 2 | Filtros |
| 20 | Vala de filtração | 8 | 2 | Valas de filtração |
| 21 | Vala de infiltração | 8 | 1 | Valas de infiltração |
| 22 | Sumidouro | 8 | 1 | Sumidouros |
| 23 | Aquecedor de acumulação (horizontal) | 4 | 36 | Reservatório térmico horizontal |
| 24 | Aquecedor de acumulação (vertical) | 4 | 29 | Reservatório térmico vertical |
| 25 | Aquecedor de passagem | 4 | 32 | (aquecedores a gás) |
| 26 | Placa solar | 4 | 9 | (placas) |
| 27 | Reservatório cilíndrico | 20 | 202 | Caixa d'água tipo taça |
| 28 | Reservatório retangular | 20 | 16 | Caixa d'água |
| 29 | Reservatório de concreto | 20 | 7 | Pré-moldado |
| 30 | ~Caixa de gordura | 8 | 8 | Caixa de gordura |
| 31 | ~Ponto/dispositivo elétrico (tomada, interruptor) | 64, 576 | 4.583 | Tomada — uso específico; Condulete |
| 32 | Quadro de distribuição | 64 | 344 | Caixa de derivação com disjuntor |
| 33 | Quadro transformador | 64 | 5 | Quadro metálico |
| 34 | Quadro de medição | 64 | 3.771 | (barramento blindado) |
| 35 | Transformador / estabilizador | 64 | 7 | Nobreak; Transformador |
| 36 | Entrada de serviço | 64 | 2.532 | Ancoragem poste — medição em poste |
| 37 | Caixa de passagem (elétrica) | 64, 576 | 315 | Aço pintada |
| 38 | Rack | 64 | 305 | Gabinete 19" |
| 39 | Ponto de consolidação | 64 | 8 | Ponto de consolidação |
| 40 | Quadro / entrada telefônica | 64 | 33 | Caixa de distribuição p/ telefonia |
| 41 | Componente (disjuntor, dispositivo de proteção) | 64 | 1.385 | Disjuntor tripolar termomagnético |
| 42 | Bloco de ligação | 64 | 1 | Bloco terminal |
| 43 | Conector | 64 | 19 | Conector fêmea / macho |
| 44 | ~Caixa (acessório de cabeamento) | 64 | 119 | Bastidor; DIO 24 fibras |
| 45 | ~Caixa subterrânea p/ telefonia | 64 | 4 | Caixa subterrânea |
| 46 | Caixa de inspeção (SPDA) | 256 | 40 | Caixa de inspeção |
| 47 | Captor | 256 | 132 | Captor Franklin; Terminal aéreo |
| 48 | Haste de aterramento | 64, 320 | 16 | Haste de aterramento |
| 49 | Isolador | 256 | 50 | Isolador simples |
| 50 | Barramento de equipotencialização | 320, 64 | 14 | Barramento de equipotencialização |
| 51 | Duto de proteção | 256 | 4 | Duto de proteção |
| 52 | ~Curva de transposição | 52, 60 | 18 | Curva de transposição |
| 53 | ~Hidrômetro individual | 20 | 26 | Hidrômetro individual |
| 54 | ~Filtro de água da chuva | 8 | 6 | Filtro de água da chuva |
| 55 | ~Ramal de ventilação | 8 | 39 | Ramais de ventilação |
| 56 | ~Bomba jockey | 16 | 13 | (bombas jockey) |
| 57 | ~Patch cord | 64 | 43 | Patch cord montado |
| 58 | ~Poço de visita / caixa de passagem | 8 | 22 | Poço de visita de esgoto |
| 59 | ~Hidrômetro (cavalete) | 52, 4 | 28 | Hidrômetros |
| 60 | Inversor | 64 | 24 | Inversores trifásicos |
| 61 | Caixa de junção | 64 | 24 | Caixa de junção — sobrepor |
| 62 | Controlador de carga | 64 | 14 | Controlador de carga PWM |
| 63 | ~Captor pontual | 256 | 3 | Captor pontual |
| 64 | ~Extintor | 16 | 8 | Extintores portáteis |
| 65 | ~Alarme de incêndio | 16 | 7 | Alarme de incêndio |
| 66 | ~Iluminação de emergência | 16 | 4 | Iluminação de emergência |
| 67 | ~Sinalização de emergência | 16 | 51 | Saída de emergência |
| 68 | Equipamento (louça, painel, subestação) | 64, 1022, 320, 18 | 134 | Peças sanitárias; painéis metálicos |
| 69 | Evaporadora | 512 | 78 | Cassete 4 vias; evaporadoras split |
| 70 | Condensadora | 512 | 155 | VRF |
| 71 | Exaustor | 512 | 10 | Exaustor |
| 72 | ~Duto (climatização) | 512 | 27 | Duto de alta pressão |
| 73 | Caixa de distribuição (climatização) | 512 | 2 | Caixa de distribuição |
| 74 | Bomba para drenagem | 512 | 4 | Bomba para drenagem |
| 75 | Válvula de bloqueio | 512 | 8 | Válvula de esfera |
| 76 | Bateria | 64 | 37 | Bateria estacionária |
| 77 | Módulo fotovoltaico | 64 | 46 | Módulo fotovoltaico |
| 78 | ~Distribuidor (PEX) | 36 | 84 | Distribuidor 4S |
| 79 | ~Filtro de piscina | 4 | 19 | Filtro de piscina DFR |
| 80 | Caixa coletora | 12 | 36 | Concreto retangular; polietileno |
| 81 | Pressurizador | 4 | 33 | Pressurizador |
| 82 | Válvula redutora de pressão | 4 | 39 | Pré-regulável c/ manômetro |
| 83 | Quadro de transferência | 64 | 10 | Trifásico; monofásico |
| 84 | Gerador de energia | 64 | 24 | Gerador a diesel |

Nem toda aplicação da ajuda tem valor no catálogo, e o contrário também vale: a ajuda **não lista
"Tubo"** (o valor 1, que existe e é usado em 2.104 peças).

## Os dois enums IFC têm nome — a ajuda decodifica os dois

`grupo_de_pecas.htm` lista **as entidades IFC4 que o Builder oferece, na ordem**. Essa ordem é o
`TIPO_ENTIDADE_IFC`: **4096 + o índice na lista**, descontado `IfcFlowSegment` (que só existe do lado
2×3). O `ENTIDADE_IFC` segue uma ordem própria, mas cada código anda colado a um tipo — e é o tipo
que o nomeia.

A decodificação foi conferida contra o nome de grupo de cada código nos 3.929 grupos do catálogo
oficial, **32 verificações independentes, todas certas**: `IfcAlarm` traz "Sirene", `IfcBoiler` traz
"Reservatório térmico", `IfcInterceptor` traz "Caixa de gordura", `IfcElectricTimeControl` traz
"Programador horário", `IfcFlowMeter` traz "Hidrômetro", `IfcCommunicationAppliance` traz "DIO 24
fibras". Com **uma** correção, e ela é da ajuda: o texto lista `IfcSanitaryTerminal` antes de
`IfcStackTerminal` e os dados dizem o contrário (4121 é o terminal de ventilação, 4122 é a pia). A
página é digitada à mão — escreve `IfcElectricDistribuitionBoard`, `IfcFireSuppresionTerminal` e
`IfcFlowMovingDevic` errado —, então um par fora de ordem é o que se espera dela.

**A lista da ajuda acaba antes do programa:** cinco tipos em uso no catálogo (4147, 4152, 4156, 4157,
4161 — dutos, VRF, evaporadora) estão além do fim dela. São entidades que entraram depois que a
página foi escrita, e são justamente as de climatização.

| `ENTIDADE_IFC` | nome IFC4 | tipo | 2×3 | grupos | peças | aplicação dominante | no escritor |
|---|---|---|---|---|---|---|---|
| 2048 | `IfcAlarm` | 4125 | 2089 | 15 | 129 | 31 (100 %) | sim |
| 2049 | `IfcBoiler` | 4115 | 2090 | 9 | 89 | 23 (40 %) | sim |
| 2050 | `IfcBurner` | 4127 | 2087 | 152 | 280 | 12 (100 %) | sim |
| 2051 | `IfcCableCarrierFitting` | 4100 | 2088 | 336 | 5265 | 2 (100 %) | sim |
| 2052 | `IfcCableCarrierSegment` | 4097 | 2086 | 86 | 1224 | 1 (100 %) | sim |
| 2053 | `IfcCableFitting` | 4101 | 2088 | 3 | 47 | 57 (91 %) | sim |
| 2054 | `IfcCableSegment` | 4098 | 2086 | 38 | 209 | 1 (100 %) | sim |
| 2055 | `IfcCommunicationAppliance` | 4112 | 2089 | 24 | 75 | 44 (100 %) | sim |
| 2057 | `— entrou depois da ajuda` | 0 | 2087 | 2 | 6 | 2 (100 %) | **não** |
| 2058 | `IfcElectricAppliance` | 4111 | 2092 | 2 | 6 | 31 (100 %) | **não** |
| 2059 | `IfcElectricDistribuitionBoard` | 4106 | 2091 | 226 | 4008 | 34 (94 %) | sim |
| 2060 | `IfcElectricFlowStorageDevice` | 4128 | 2094 | 3 | 42 | 76 (88 %) | sim |
| 2061 | `IfcElectricTimeControl` | 4107 | 2091 | 4 | 26 | 31 (50 %) | **não** |
| 2063 | `IfcFilter` | 4116 | 2095 | 2 | 7 | 54 (86 %) | **não** |
| 2064 | `IfcFireSuppresionTerminal` | 4120 | 2092 | 271 | 1637 | 17 (88 %) | sim |
| 2065 | `IfcFlowMeter` | 4102 | 2091 | 779 | 2696 | 36 (94 %) | sim |
| 2066 | `IfcInterceptor` | 4124 | 2092 | 2 | 12 | 30 (67 %) | **não** |
| 2067 | `IfcJunctionBox` | 4132 | 2088 | 281 | 3936 | 31 (77 %) | sim |
| 2069 | `IfcLightFixture` | 4109 | 2092 | 203 | 1119 | 31 (100 %) | sim |
| 2070 | `IfcOutlet` | 4108 | 2092 | 4 | 10 | 31 (90 %) | **não** |
| 2071 | `IfcPipeFitting` | 4099 | 2088 | 598 | 4408 | 2 (96 %) | sim |
| 2072 | `IfcPipeSegment` | 4096 | 2086 | 39 | 256 | 1 (100 %) | sim |
| 2073 | `IfcProtectiveDevice` | 4105 | 2091 | 58 | 1504 | 41 (86 %) | sim |
| 2075 | `IfcPump` | 4118 | 2093 | 34 | 621 | 6 (91 %) | sim |
| 2076 | `IfcSanitaryTerminal` | 4122 | 2092 | 223 | 549 | 4 (80 %) | sim |
| 2077 | `IfcSensor` | 4131 | 2089 | 2 | 8 | 31 (100 %) | **não** |
| 2078 | `IfcSolarDevice` | 4114 | 2094 | 5 | 55 | 77 (84 %) | sim |
| 2079 | `IfcStackTerminal` | 4121 | 2092 | 3 | 7 | 2 (100 %) | sim |
| 2080 | `IfcSwitchingDevice` | 4104 | 2091 | 56 | 324 | 31 (77 %) | sim |
| 2081 | `IfcTank` | 4119 | 2094 | 42 | 283 | 27 (71 %) | sim |
| 2082 | `IfcTransformer` | 4113 | 2090 | 1 | 2 | 35 (100 %) | **não** |
| 2083 | `IfcUnitaryControlElement` | 4126 | 2087 | 2 | 6 | 31 (100 %) | **não** |
| 2084 | `IfcValve` | 4103 | 2091 | 163 | 740 | 3 (84 %) | sim |
| 2085 | `IfcWasteTerminal` | 4123 | 2092 | 33 | 79 | 58 (25 %) | sim |
| 2086 | `IfcPipeFitting` | 4099 | 2086 | 34 | 415 | 1 (100 %) | sim |
| 2087 | `IfcDistributionFlowElement` | 4133 | 2087 | 147 | 1024 | 2 (56 %) | sim |
| 2090 | `IfcTransformer` | 4113 | 2090 | 4 | 36 | 60 (61 %) | sim |
| 2092 | `IfcSanitaryTerminal` | 4122 | 2092 | 1 | 14 | 68 (100 %) | **não** |
| 2096 | `— entrou depois da ajuda` | 4147 | 2092 | 7 | 41 | 72 (66 %) | sim |
| 2102 | `— entrou depois da ajuda` | 4152 | 2090 | 4 | 146 | 70 (100 %) | sim |
| 2106 | `— entrou depois da ajuda` | 4156 | 2088 | 25 | 201 | 2 (95 %) | sim |
| 2111 | `— entrou depois da ajuda` | 4161 | 2090 | 6 | 69 | 69 (100 %) | sim |

<!-- 31611 peças, 3929 grupos com entidade; 42 entidades -->

Peça sem entidade não existe: os 3.929 grupos têm todos as seis colunas preenchidas.

## A ponte prática: `ENTIDADE_IFC` → aplicação

É por aqui que uma fonte que não conhece o vocabulário do Builder (IFC, família Revit, catálogo de
plugin) chega na aplicação certa — a classe IFC ela sempre tem. Os pares dominantes no catálogo:

| `ENTIDADE_IFC` | aplicação dominante | peças |
|---|---|---|
| 2051 | 2 conexão (eletrocalha) | 5.246 de 5.265 |
| 2071 | 2 conexão (hidráulica) | 4.216 de 4.408 |
| 2059 | 34 quadro de medição | 3.771 de 4.008 |
| 2067 | 31 dispositivo elétrico | 3.032 de 3.936 |
| 2065 | 36 entrada de serviço | 2.532 de 2.696 |
| 2064 | 17 sprinkler / 16 hidrante | 1.541 de 1.637 |
| 2073 | 41 componente / 47 captor | 1.424 de 1.504 |
| 2052 · 2072 · 2054 · 2086 | 1 tubo/conduto | 100 % |
| 2069 · 2048 · 2077 · 2058 · 2083 | 31 dispositivo elétrico | 100 % |
| 2076 | 4 peça de utilização / 8 aparelho | 541 de 549 |
| 2075 | 6 bomba / 81 pressurizador | 596 de 621 |
| 2084 | 3 registro / 82 VRP | 659 de 740 |
| 2102 · 2111 | 70 condensadora · 69 evaporadora | 100 % |
| 2096 | 72 duto / 71 exaustor / 74 bomba de dreno | 100 % |
| 2090 | 60 inversor / 62 controlador | 100 % |
| 2049 | 23/24/25 aquecedor | 100 % |
| 2081 | 27 reservatório cilíndrico | 202 de 283 |

Desde a ADR-024 o escritor conhece **32** dessas 42 entidades (`cadastro.py`, dicionário `IFC`),
com as sete hidráulicas de antes mais elétrica, SPDA e climatização. As dez que faltam — 2057, 2058
`IfcElectricAppliance`, 2061 `IfcElectricTimeControl`, 2063 `IfcFilter`, 2066 `IfcInterceptor`, 2070
`IfcOutlet`, 2077 `IfcSensor`, 2082 `IfcTransformer`, 2083 `IfcUnitaryControlElement` e 2092
`IfcSanitaryTerminal` — somam 2 a 26 peças cada no catálogo.

**Quem atravessa a ponte (ADR-026).** Só o caminho do `.aq`, e ele está ligado ponta a ponta:
`catalogo.build_catalog_from_aq` grava a `ENTIDADE_IFC` do grupo em cada produto, o criador a guarda
em `bim_products.entidadeIfc` e a devolve no manifesto de exportação — um `.aq` que entra e sai do
pipeline conserva a entidade que trazia. As outras fontes (IFC, família Revit, plugin de CAD) não
declaram entidade: para elas vale o nome, e traduzir a classe IFC do arquivo (`IFCVALVE` → 2084) é a
pendência seguinte.

**Supertipo abstrato não classifica.** As entidades de tipo 4133…4142 (`IfcDistributionFlowElement` e
as outras do fim da lista) dizem só que a peça é uma peça de instalação. Elas deixam o vocabulário
falar primeiro e só valem como rede — e, como rede, valem **conexão**: das 1.024 peças declaradas
com 2087 no catálogo oficial a aplicação dominante é 2 (56 %), e numa biblioteca real de barramento
blindado é 2 em **212 de 212** peças de conexão. Duas medições independentes, que é o que tirou esse
valor do terreno do palpite (ADR-026, emenda de 2026-09-11).

## `POSICIONAR_SIMBOLOGIA_3D` — como a peça se orienta ao ser lançada

É o que faz a peça **já entrar certa no projeto**: o modo diz para onde aponta o eixo X da
simbologia quando o Builder monta o 3D a partir do croqui. A ajuda (`representacao_simbologia_3d.htm`)
descreve sete modos, nesta ordem, que são os valores 0…6 — a ordem foi confirmada por três âncoras
independentes: o valor 3 aparece na tela como "Na horizontal, apontando para a tubulação de entrada"
(visto no Cadastro), e os exemplos da própria ajuda batem com o valor dominante de cada aplicação no
catálogo oficial.

| valor | modo | eixo X aponta para | exemplo da ajuda | aplicação onde domina |
|---|---|---|---|---|
| 0 | No plano formado pelos condutos | entrada/saída; Z é a normal do plano | joelho | conexão (8.039 de 10.467) |
| 1 | No plano dos condutos e do ponto diretor | um dos condutos; Z no ponto diretor | registro | registro (353 de 733) |
| 2 | Na horizontal, apontando para o ponto diretor | ponto diretor; Z global | ponto de lâmpada | dispositivo elétrico (1.780), evaporadora (78 de 78) |
| 3 | Na horizontal, apontando para a **tubulação de entrada** | conduto da entrada; Z global | hidrômetro | bomba (503 de 588) |
| 4 | Na horizontal, apontando para a **tubulação de saída** | conduto da saída; Z global | caixa sifonada | — (263 peças no total) |
| 5 | — indeterminado (só 50 peças no catálogo, nenhuma âncora) | — | — | — |
| 6 | **No plano de lançamento, apontando para o ponto diretor** | plano em que o usuário lança | junção simples | conexão **com ligação 3D** (288 de 332) |

**Peça com "Pontos de ligação 3D: Sim" só aceita dois modos — 2 e 6.** O Cadastro oferece só esses
dois no combo (visto na tela em 2026-09-11) e o catálogo confirma: das **4.206** peças com
`CONEXAO_VOLUMETRICA = 1`, todas usam 2 ou 6 — **nenhuma** usa 0, 1, 3, 4 ou 5. A engenharia do
Builder descreveu a diferença, e a medição bate com a descrição:

| modo | o que significa na prática | quem usa (entre as peças com ligação 3D) |
|---|---|---|
| **2** — na horizontal | a peça fica **sempre de pé**: apoiada no piso ou na face da parede | bomba 26/26, evaporadora 32/32, condensadora 58/58, reservatório 26/26, aquecedor 36/36, elemento genérico 101/102, quadro de medição 2.623/2.966 |
| **6** — no plano de lançamento | a peça fica **como o usuário lançar**: de pé, deitada ou de ponta-cabeça. É a curva entre dois tubos | conexão 288/332, registro 7/12, tomada d'água 6/6, pressurizador 33/33, dispositivo elétrico 17/27 |

Como o pipeline marca a ligação 3D em toda peça com bocal, é esta regra que vale para ela, e não a
tabela por aplicação acima — que descreve a peça **sem** ligação 3D.
`entradas_aq.marcar_pontos_de_ligacao` normaliza o modo junto com a marca
(`cadastro.posicionar_com_ligacao`). **Tubo fica de fora**: a coluna é nula em 2.104 de 2.104 tubos
e tubo com ligação 3D não existe no catálogo — sem medição, a regra forte do tubo prevalece.

Duas coisas medidas que valem como regra:

- **Tubo (aplicação 1) tem a coluna nula** — 2.104 de 2.104. Conduto não tem simbologia a orientar.
- **Conexão sem ligação 3D quer 0** (8.039 de 10.467); com ligação 3D, quer **6**. As duas regras
  convivem porque descrevem peças diferentes: sem pontos de ligação a peça se orienta pelo plano
  dos condutos, com pontos ela se orienta pelo lançamento.

## O que o pipeline faz hoje (ADR-024)

Quem classifica é `bim_pipeline.aq.cadastro`, chamado pelos dois escritores, em três degraus:

1. **A disciplina vem de quem importa, não do nome.** É campo **obrigatório** no formulário de
   importação (`POST /importacoes`, `/importacoes/plugin-autocad`, `/importacoes/familias-revit`),
   pré-preenchido com o palpite da fonte e confirmado por quem importa; fica gravada no catálogo
   (`bim_catalogs.disciplina`) e vale para a biblioteca inteira. A exportação de um catálogo sem
   disciplina — os importados antes desta data — é **recusada**, com a mensagem dizendo o que
   escolher, em vez de exportar peça no projeto errado.
2. **A aplicação vem da entidade IFC quando a fonte a declara** (tabela acima, em `cadastro.IFC`),
   e a disciplina desempata onde a entidade não decide (2073 → 41 componente no elétrico, 47 captor
   no SPDA). Só na falta dela cai no **vocabulário da disciplina escolhida** — são sete tabelas
   agora, uma por disciplina; a hidráulica é a antiga, sem perda.
3. **Sem reconhecer, grava o genérico da disciplina e avisa** — no resumo da exportação e na
   conferência "aplicação e disciplina" do `validar_aq`, que fala alto quando uma disciplina **inteira** ficou no
   genérico. Não aborta: uma biblioteca de 3.000 peças não pode ficar refém de cinco peças
   estranhas, mas o erro não pode mais passar calado, que foi como ele atravessou três aceitações
   no Builder.

Junto vieram as correções que a medição sustentava: `PROJETO_APLICACAO` de água fria passou de 12
(hidráulico + sanitário) para **4** e o de incêndio de 22 para **20**; `POSICIONAR_SIMBOLOGIA_3D`
deixou de ser fixo (3 num escritor, 0 no outro) e sai da aplicação pela tabela medida; e
`INDICE_SIMBOLO3D_SELECIONADO`, que divergia entre os escritores, ficou em **-1**, o *default* do
schema.

O que **continua em aberto** é o que a medição não decide: a peça cuja fonte não declara entidade
IFC e cujo nome está em inglês (`Actuator MP500C-SRD`) cai no genérico e é avisada — o vocabulário
não cobre outra língua, e inventar sinônimos em inglês seria voltar a adivinhar.

## Como medir de novo

Os dois acervos ficam **fora do repositório**, na máquina de quem opera, sob `Documents/BIM/`:

- `Catalog_PC81_Ativo/Catalog.db` — 5,8 GB num arquivo só, SQLite com o mesmo schema do `.aq`.
  Abra **somente-leitura**, use o `text_factory` de `read_aq` (há texto cp1252 apesar de o
  cabeçalho declarar UTF-8) e **nunca** `SELECT *` nas tabelas de geometria — o `WIREFRAME` sozinho
  traz centenas de MB. Só agregados: `COUNT`, `GROUP BY`, e o cruzamento com `ENTRADA_PECA`/
  `ENTRADA_3D` por `EXISTS`.
- `Docs QiBuilder/QiBuilder/` — 2.565 páginas `.htm` (123 MB com imagens, 4,1 MB de texto). Leia
  com `python3 -m bim_pipeline.cli.ferramentas.ajuda_builder --ajuda <esse dir> --indexar <regex>`:
  ele extrai o texto uma vez para um JSONL e busca sobre ele, o que faz 4,1 MB caberem em algumas
  dezenas de linhas. `peca.htm` é a página das propriedades da peça e traz a tabela
  Projeto × Aplicações.

Uma medição inteira destas (as duas tabelas acima) custa poucos minutos e nenhuma leitura de
arquivo grande — o caro é esquecer de filtrar e trazer geometria junto. Antes de somar qualquer
distribuição, confira que os arquivos são mesmo nativos: `aq-formato.md` §"As duas fontes externas
de verdade" traz a assinatura que separa nativa de saída nossa.
