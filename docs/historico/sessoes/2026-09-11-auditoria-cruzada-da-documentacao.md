# 2026-09-11 — Auditoria cruzada: documentação × código × ajuda × catálogo oficial

Sessão de **conferência**, não de feature. Cada afirmação dos documentos de `docs/conhecimento/`
é cruzada com três fontes independentes, nesta ordem de autoridade quando discordam:

1. **O código** — o que o pipeline realmente grava (é o que o Builder vai ler).
2. **A ajuda do Builder** — o que a propriedade *significa*. Só as páginas atuais (ver achado 1).
3. **O catálogo oficial** (`Catalog.db`, schema 625: 31.611 peças, 3.929 grupos, 203 classes) — a
   distribuição real, amostra ~20× maior que as bibliotecas nativas de onde os docs saíram.

O que se confirma fica; o que diverge é corrigido **no documento de origem**, sem narrativa
(CLAUDE.md §"documentação primeiro", regra 4). Este arquivo é a trilha, não a verdade.

## Método de consulta (para repetir)

- Ajuda: `python3 -m bim_pipeline.cli.ferramentas.ajuda_builder '<regex>' [--pagina x] [--paginas]`.
- Catálogo: conexão **somente-leitura** (`file:…?mode=ro`), `text_factory` cp1252, **só agregados**
  (`COUNT`/`GROUP BY`) — nunca `SELECT *` em tabela com geometria.

---

## Achado 1 — a ajuda mistura páginas de versões antigas com as atuais ✅ corrigido

Das 2.565 páginas `.htm`, **281 não são alcançáveis** nem pelo sumário (`contents_data.js`) nem por
link de quem é alcançável — sucata de versões passadas, em pares de nome quase igual
(`Angulo_rotacao.htm` × `Angulo_de_rotacao.htm`). Outras 76 só se alcançam por link (janela de
propriedade; valem como fonte). O índice do `ferramentas.ajuda_builder` tratava todas como iguais.

**Consequência:** qualquer busca podia citar o programa de outra época sem aviso.

**Corrigido:** o índice classifica cada página em `toc` (2.208) / `link` (76) / `orfa` (281), a busca
pula a órfã por padrão (`--incluir-orfas` traz de volta) e marca `[link]` o que não está no sumário.
Commit `8a53a74`, com teste. As quatro páginas que sustentam ADR-020 a ADR-025 (`peca.htm`,
`entradas_3d.htm`, `representacao_simbologia_3d.htm`, `editar_simbologia_3d.htm`) estão **todas no
sumário** — nenhuma decisão tomada até aqui se apoiou em sucata.

## Achado 2 — `aq-formato.md` §Enums trata `PROJETO_APLICACAO` como enum, e com os valores que a ADR-024 corrigiu

O documento dizia "**8** esgoto · **12** água fria · **22** incêndio · **36** gás · **64/76**
elétrico". São dois problemas no mesmo parágrafo: a coluna é **bitmask** (`aplicacoes-builder.md`), e
12 e 22 são justamente os dois valores que a ADR-024 apontou como defeito do escritor (água fria é
**4**; incêndio com água é **20**). Medido agora: os 3.929 grupos do catálogo usam **exatamente os
20 valores** que `aplicacoes-builder.md` lista, o que confirma aquele documento por inteiro.

## Achado 3 — `2090` não é aquecedor a gás: é inversor / controlador de carga

`aq-formato.md` dava a tripla `2090 / 4138 / 2090` como "aquecedor a gás". No catálogo oficial os
quatro grupos com `ENTIDADE_IFC = 2090` são **inversores e controladores de carga** (fotovoltaico),
com `TIPO_ENTIDADE_IFC = 4113` — e o valor **4138 não existe** em nenhuma das 3.929 linhas, nem como
tipo 2×3. O **código já está certo** (`cadastro.py:165`, `2090: (4113, 2090, 2, 60)  # inversor`, e o
aquecedor é `2049`); quem ficou para trás foi o documento.

## Achado 4 — "as três colunas IFC andam sempre juntas, em combinações fixas" é forte demais

Medido: **42** entidades distintas em **52** combinações — dez entidades aparecem com mais de um par
`(tipo, 2×3)`. O par dominante é sólido (nas 32 entidades que o código conhece, **todas as 32**
batem com o dominante do catálogo), mas "fixas" não descreve o que existe. O documento também não
diz que as seis colunas IFC são de **`GRUPO_PECA`**, não de `PECA`.

## Achado 5 — a ajuda decodifica os dois enums IFC, e os dois nomes que faltavam

`grupo_de_pecas.htm` (no sumário) lista **as entidades IFC4 que o Builder oferece, em ordem**. Essa
ordem é o `TIPO_ENTIDADE_IFC`: **4096 + o índice na lista**, descontado `IfcFlowSegment` (que só
existe no lado 2×3). A decodificação foi conferida contra o nome de grupo real de cada código no
catálogo oficial — 32 verificações semânticas independentes, e **todas passam**: 4125 = `IfcAlarm`
("Sirene"), 4115 = `IfcBoiler` ("Reservatório térmico"), 4127 = `IfcBurner` ("Fritadeira
industrial"), 4100 = `IfcCableCarrierFitting` ("T vertical de eletrocalha"), 4101 = `IfcCableFitting`
("Patch cord"), 4112 = `IfcCommunicationAppliance` ("DIO 24 fibras"), 4128 =
`IfcElectricFlowStorageDevice` ("Bateria estacionária"), 4107 = `IfcElectricTimeControl`
("Programador horário"), 4102 = `IfcFlowMeter` ("Hidrômetro"), 4124 = `IfcInterceptor` ("Caixa de
gordura"), 4132 = `IfcJunctionBox` ("Condulete"), 4131 = `IfcSensor` ("Detetor"), 4123 =
`IfcWasteTerminal` ("Caixa sifonada") e assim por diante.

Com **uma** exceção, e ela é da ajuda: o texto lista `IfcSanitaryTerminal` antes de
`IfcStackTerminal`, mas os dados dizem o contrário (4121 é o terminal de ventilação, 4122 é a pia).
A página é uma lista digitada à mão — traz `IfcElectricDistribuitionBoard`,
`IfcFireSuppresionTerminal` e `IfcFlowMovingDevic` escritos errado —, então um par fora de ordem é o
que se espera dela. Invertido esse par, a decodificação fecha 100 %.

**O `ENTIDADE_IFC` não segue a mesma ordem** (2048…2111 numa ordem própria), mas cada código anda
colado a um tipo, e é o tipo que o nomeia. Cinco tipos do catálogo (**4147, 4152, 4156, 4157,
4161** — dutos, VRF, evaporadora) estão **além do fim da lista da ajuda**: são entidades que
entraram no programa depois que a página foi escrita. Ou seja, a ajuda é atual mas **incompleta**,
e a diferença é exatamente a climatização.

Com isso, o `4138` que o `aq-formato.md` atribuía ao "aquecedor a gás" seria `IfcFlowStorageDevice` —
que não aparece em nenhum dos 3.929 grupos. O achado 3 fica duplamente confirmado.

## Achado 6 — o degrau 1 da ADR-024 está morto: ninguém preenche `entidadeIfc`

`classificar()` decide em três degraus, e o primeiro é "a entidade IFC que a fonte declara". Medido
no repositório inteiro: `entidadeIfc` é **lido** em `catalogo_to_aq.py:179`, `geo_to_aq.py:111`, está
no contrato (`manifesto-catalogo-aq.schema.json`) e no tipo TypeScript (`pacotes/base`) — e **não é
escrito por nenhuma fonte**. Nem o leitor de `.aq` (`read_aq`/`catalogo.py` não carregam
`GRUPO_PECA.ENTIDADE_IFC` para o catálogo), nem o IFC, nem a família Revit, nem o plugin de CAD. O
único lugar que exercita o degrau é o teste `test_a_entidade_ifc_da_fonte_vence_o_nome`.

**Consequência prática:** toda exportação classifica pelo **nome**, degrau 2. E um `.aq` nativo que
entre e saia do pipeline **perde a entidade que já tinha** — é reclassificada pelo vocabulário. O
caso mais barato de corrigir é esse: a entidade está lá, basta não jogá-la fora.

## Achado 7 — entidade genérica não deveria vencer o nome

Quando a entidade é declarada, ela **curto-circuita** o vocabulário (`return` imediato). Isso está
certo para `IfcValve` ou `IfcPump`, que dizem o que a peça é; está errado para as genéricas.
Medidas as quatro divergências entre a aplicação que o código fixa por entidade e a dominante do
catálogo, três são genéricas ou de amostra pequena:

| entidade | código fixa | catálogo | leitura |
|---|---|---|---|
| 2087 `IfcDistributionFlowElement` (genérica) | 68 equipamento | **2 conexão** (56 % de 1.024 peças) | a entidade não diz nada; o nome deveria decidir |
| 2085 `IfcWasteTerminal` | 9 caixa sifonada | 58 poço de visita (25 % de 79) | ninguém domina; ralo, caixa e poço convivem |
| 2049 `IfcBoiler` | 25 aquecedor de passagem | 23 acumulação horizontal (40 % de 89) | escolha entre irmãos 23/24/25, aceitável |
| 2079 `IfcStackTerminal` | 55 ramal de ventilação | 2 conexão (100 % de 7) | amostra de 3 grupos |

`2087` é, além disso, o **genérico da climatização** no degrau 3 — a mesma entidade serve de
"não sei" e de fato declarado.

## Achado 8 — dez entidades do catálogo estão fora da tabela do código

`2057`, `2058` (`IfcElectricAppliance`), `2061` (`IfcElectricTimeControl`), `2063` (`IfcFilter`),
`2066` (`IfcInterceptor`), `2070` (`IfcOutlet`), `2077` (`IfcSensor`), `2082` (`IfcTransformer`),
`2083` (`IfcUnitaryControlElement`), `2092` (`IfcSanitaryTerminal`). Todas de pouca peça (2 a 26),
mas hoje uma fonte que declare qualquer uma delas cai no degrau 3 com aviso de genérico.

## Achado 9 — o que a medição **confirmou** (nada a corrigir)

- **ADR-022**: `SECAO`/`DIAMETRO_INTERNO` nulas em **15.321 de 15.321** peças com `ENTRADA_PECA`.
- **ADR-023**: `CONEXAO_VOLUMETRICA = 1` → tem `ENTRADA_3D` em **4.206 de 4.206**. A volta não vale
  (1.210 peças têm entrada com a coluna em 0), que é exatamente o que a ADR afirma.
- `PROJETO_APLICACAO`: os 3.929 grupos usam **os 20 valores** que `aplicacoes-builder.md` lista.
- `TIPO_APLICACAO_PECA`: **1…84, todos os 84 em uso** — a tabela do documento está completa.
- As **32** triplas IFC do `cadastro.py` batem com o par dominante do catálogo, uma a uma.
- Schema **625** tem `ENTRADA_3D.DIAMETRO` (a tabela de versões do `aq-formato.md` segue válida).
- Sentinelas: `-DBL_MAX` em 25.294/31.611 `DIAMETRO_PECA` e 14.031 `COMPRIMENTO_PECA`;
  `-2147483647` em 26.223/33.041 `SECAO_EP`. Só `TIPO_CONFIGURACAO_GP` desmente o "todas as linhas"
  do documento: **3.534 de 3.929** (90 %).

## Achado 10 — `SUBTIPO_IFC_2X3` não é "sempre igual" ao `SUBTIPO_IFC`

Difere em **438 dos 3.929 grupos** (11 %). Os dois escritores gravam os dois iguais, o que continua
dentro do observado — a correção é do texto, não do código. `aq-formato.md` ajustado.

---

## O que virou código: ADR-026 (achados 6, 7 e 8)

Aceita e implementada no mesmo dia, com a suíte em **271** na coleta (era 268) e `pnpm -r build`
verde nos 9 workspaces:

- `catalogo.build_catalog_from_aq` grava `entidadeIfc` no produto; `bim_products` ganha a coluna;
  a exportação a devolve no manifesto. O round-trip deixa de perder a entidade de origem — provado
  em `test_catalogo_to_aq` (`[2071, 2071, 2075]`, e a série "Junção Ímpar" não tem nome de bomba).
- `TIPOS_SUPERTIPO` (4133…4142): supertipo abstrato não vence o nome, só serve de rede.
- Nove entidades novas em `cadastro.IFC` (41 de 42). A 2057 ficou fora: `TIPO_ENTIDADE_IFC = 0` nos
  dois grupos que a usam é cadastro incompleto do próprio catálogo oficial.

Pendência que a ADR-026 **não** resolve, registrada nela: traduzir a classe IFC de um arquivo IFC
importado (`IFCVALVE` → 2084) exige fechar a tabela nome → código para as entidades de climatização,
que são justamente as que a ajuda não lista.

---

## Achado 11 — o catálogo oficial guarda geometria num **segundo** container, que não é OQ3D

Primeira vez que o leitor OQ3D correu contra as **6.132 simbologias nativas** do catálogo oficial —
a maior amostra de geometria que existe aqui. Resultado: **4.908 são OQ3D clássico e 1.224 (20 %)
não são**. Estas abrem com um dicionário de classes (`TStreamableObjectsContainer`, seguido de
`TCoordinateTransformation3D_2014_06_09`, `TFace2D_2014_06_09`, `TCircularFace2D_2015_02_10`,
`TExtrusionPath`, `T3DSegment`) e referenciam as instâncias **por índice** — a varredura por
marcador não acha nada nelas.

Duas medições que evitam a pista falsa:

- **Não é o cabeçalho.** Ignorar a assinatura e mandar o parser em frente devolve **zero
  triângulos**, inclusive nos 11 de 42 blobs em container cujo grafo tem `TQi3DIndexedTriangleMeshData`
  no dicionário. O nome está lá como declaração; a instância é um índice.
- **A maioria nem é malha:** é face 2D mais caminho de extrusão — geometria paramétrica, que teria
  de ser tesselada.

**Relevância medida, não suposta:** nas 14 bibliotecas de fabricante do acervo (schemas 552, 562,
572, 582, 594, 595, 607, 615) são **zero** blobs em container. Ele só aparece no catálogo do próprio
Builder, schema **625**. Ou seja: risco de biblioteca nova, não defeito de hoje — e viés a lembrar,
porque 20 % da geometria do catálogo oficial é invisível para nós ao medir.

**Feito:** o erro passou a dizer o nome do formato em vez de "sem assinatura OQ3D" (que faz pensar
em arquivo corrompido, outra causa e outro conserto), com teste; `oq3d.md` ganhou a seção,
`diagnostico.md` o sintoma.

## Achado 12 — a tabela de versões de schema tinha o limite no lugar errado

`aq-formato.md` dava 552–582 sem `ENTRADA_3D.DIAMETRO`, com o 595 numa linha à parte que sugeria
tê-la. Medido nas 15 bibliotecas: **552, 562, 572, 582, 594 e 595 não têm**; **607, 615 e 625 têm**.
`PECA` tem as mesmas 33 colunas em todas, `CONEXAO_VOLUMETRICA` inclusive.

## Achado 13 — a `IMAGEM` (ADR-020) ganha a confirmação mais forte que havia

**6.132 de 6.132** simbologias do catálogo oficial têm `IMAGEM` preenchida — e também `WIREFRAME`,
que o Builder gera sozinho (ADR-021). A medição antiga era sobre ~1.400 simbologias de fabricante.

## Achado 14 — `aq-escrita.md`: a tabela IFC repetia os exageros, e a lista de abortos estava curta

- "andam sempre juntos" e "`cadastro.IFC`, 31 entidades" (hoje 41 de 42) — corrigidos, e a tabela
  ganhou o **nome IFC4** de cada código, que a decodificação do achado 5 permitiu.
- `2052` era descrito como "conduto/tubo genérico": é `IfcCableCarrierSegment`, segmento de
  eletrocalha. `2065` era "entrada de serviço": a entidade é `IfcFlowMeter` (hidrômetro) — a
  *aplicação* é que é entrada de serviço.
- `SUBTIPO_IFC_2X3` "sempre igual": 438 dos 3.929 grupos divergem.
- **Erros que abortam a exportação: o documento listava 5, o código levanta 8.** Faltavam os três
  que mais importam ao operador: biblioteca **sem disciplina** (ADR-024, o primeiro a ser checado),
  produto com `geo` vazio e ponto de curva Q-H inválido.

## Achado 15 — `POSICIONAR_SIMBOLOGIA_3D` se reproduz número a número

Remedido hoje, contra o que `aplicacoes-builder.md` e `aq-escrita.md` afirmam: tubo **nulo em
2.104 de 2.104**; conexão **0 em 8.039 de 10.467**; registro 1 (353 de 733); bomba 3 (503 de 588);
dispositivo elétrico 2 (1.780 de 4.583); evaporadora 2 (78 de 78). Nada a corrigir.

## Achado 16 — a escala de bitola (ADR-025) é **hidráulica**; no elétrico o código é outro bicho

Os 17 códigos foram reconferidos um a um contra o nome da peça: **16 batem**. O 4 (5/8") parece
divergir só porque seus nomes são adaptadores ("20 mm × 3/4""); as oito peças com nome puro em
polegada dizem 5/8".

O que apareceu de novo veio da tabela **milímetro → código**: nove entradas dela "divergem", e
todas com o mesmo destino, o código **2**. A causa não é a tabela — é a disciplina. Das entradas
com `DIAMETRO_EP = 2`, **10.097 são da máscara 64 (elétrico)**, contra 32 do sanitário e 16 da
hidráulica; dentro do elétrico, 2 responde por 10.097 de 13.665 entradas, com bitolas nominais de
20 a 150 mm caindo todas nele. Ou seja, no cadastro elétrico o campo não guarda bitola em polegada.

**Pendência (não mexida):** `entradas_aq` converte raio medido → código em **qualquer** disciplina.
Para biblioteca elétrica isso não tem respaldo — o catálogo grava 2 em três quartos dos casos. Como
a escolha "copiar o 2" é palpite sobre valor não documentado, fica para decisão, com a medição
acima. Documentos já corrigidos: `aq-escrita.md` e a ADR-025 ganharam a nota de escopo.

## Achado 17 — o detector de bocais contra o catálogo oficial: 0 de 331, e o número é informativo

Primeira corrida do detector de ADR-021 fora das bibliotecas de fabricante. Amostra de 38
simbologias do catálogo oficial (placement identidade, OQ3D clássico): **331 entradas nativas,
zero reencontradas** no critério de 0,5 cm do documento. Antes de concluir qualquer coisa, as duas
explicações fáceis foram testadas e caíram:

- **Não é frame nem unidade.** Em peça após peça, duas das três coordenadas batem na casa do
  milímetro — nativa `(15,0, −3,1, 2,8)` contra nossa `(14,9, −9,3, 2,7)`. Malha e entrada estão no
  mesmo referencial.
- **Não é só "amostra elétrica" às cegas** — foi medido: das 1.558 simbologias com `ENTRADA_3D` no
  catálogo, **1.251 (80 %) são de grupo elétrico** (máscara 64), contra 96 hidráulicas e 56
  sanitárias. E **318 das 331 entradas** da amostra caíram em peça onde o detector não acha
  candidato nenhum, que é o comportamento pretendido: ali "ponto de ligação" é entrada de cabo.

Sobram **13 entradas** em sifão sanitário, com candidato: a distância mediana ao candidato mais
próximo é **4,01 cm** (nenhuma abaixo de 1 cm, 2 abaixo de 3 cm, todas abaixo de 10 cm) — a entrada
nativa está recuada dentro da bolsa, o mesmo padrão já conhecido das bombas de incêndio.

**Leitura:** o placar de ADR-021 continua valendo para o que entra no pipeline (biblioteca de
fabricante: 21/21 e 14/16). O que o catálogo oficial acrescenta é a previsão de que **nossa entrada
fica na face do bocal e a de um cadastro feito à mão fica centímetros para dentro** — diferença que
o usuário vai ver no Builder e que não é defeito de nenhum dos dois. `geometria.md` §Bocais ganhou a
linha e a leitura.
