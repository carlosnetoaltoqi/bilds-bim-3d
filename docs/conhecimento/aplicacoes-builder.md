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

Nosso escritor já conhece sete dessas entidades (`IFC_TUBO` 2072, `IFC_CONEXAO` 2071, `IFC_BOMBA`
2075, `IFC_APARELHO` 2076, `IFC_VALVULA` 2084, `IFC_TERMINAL` 2085, `IFC_TERMINAL_VENT` 2079) — todas
hidráulicas. Não conhece nenhuma elétrica, de SPDA ou de climatização.

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
| 5 | No plano de lançamento, apontando para o ponto diretor | plano do cursor | — | — (50 peças) |
| 6 | Alinhada ao conduto com saída lateral de trecho reto | conduto da entrada; Y para o lado do outro conduto | junção simples | — (1.397 peças) |

Duas coisas medidas que valem como regra:

- **Tubo (aplicação 1) tem a coluna nula** — 2.104 de 2.104. Conduto não tem simbologia a orientar.
- **Conexão quer 0**, não 3. Nosso `catalogo_to_aq` grava **3** em toda peça ("apontando para a
  tubulação de entrada"), o que num joelho ou num tê orienta a peça pelo conduto de entrada em vez
  do plano dos dois condutos; `geo_to_aq` grava 0, que é o valor certo para conexão. É defeito de
  orientação no lançamento, não de desenho: a peça aparece, torta.

## Onde nosso pipeline erra hoje

`aq_writer.REGRAS_GRUPO` classifica **pelo nome do grupo**, com um vocabulário que é de catálogo
hidráulico em PVC (tubo, bomba, ralo, sifão, joelho, luva…), e **sem regra que case, a peça vira
conexão genérica**. `aplicacao_de` escolhe a disciplina por quatro palavras no título (esgoto,
incêndio, gás, senão água fria). O resultado com um catálogo elétrico ou de climatização é o que a
engenharia do Builder observou: **peça elétrica cadastrada como conexão hidráulica**. Não é um bug
pontual — é o padrão errado, herdado de as primeiras bibliotecas importadas serem hidráulicas.

A correção é ADR-024. Três regras que a medição acima sustenta:

1. **A disciplina vem da fonte, não do nome.** Uma família Revit traz a categoria; um IFC traz a
   entidade; um catálogo de plugin traz a seção. É daí que sai `PROJETO_APLICACAO`, e o *default*
   não pode ser hidráulico.
2. **A aplicação vem da entidade IFC quando ela existe** (tabela acima), e só cai no vocabulário por
   nome quando não existe — e aí o vocabulário tem de ser o da disciplina escolhida no passo 1.
3. **Sem disciplina reconhecida, é melhor falhar ou avisar do que chutar hidráulico.** Peça no lugar
   errado do cadastro é defeito que só aparece quando um projetista não acha a peça.

## Como medir de novo

O `Catalog.db` fica em `Documents/BIM/Catalog_PC81_Ativo/` na máquina do usuário (5,8 GB, fora do
repositório). É SQLite com o mesmo schema do `.aq` — abra somente-leitura, use `text_factory` do
`read_aq` (há texto cp1252 apesar do cabeçalho dizer UTF-8) e **nunca** `SELECT *` nas tabelas de
geometria. A ajuda do Builder (`Documents/BIM/Docs QiBuilder/QiBuilder/`, 2.565 `.htm`, 4,1 MB de
texto) responde o que as colunas significam; `peca.htm` é a página das propriedades da peça.
