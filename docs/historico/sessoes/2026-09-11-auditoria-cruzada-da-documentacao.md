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
