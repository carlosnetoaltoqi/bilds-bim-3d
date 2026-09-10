# ADR-024 — a disciplina da peça vem da fonte; hidráulico deixa de ser o *default*

**Status:** Aceita (2026-09-10) · implementada no mesmo dia

## Decisão

A classificação de uma peça exportada passa a ter três degraus, nesta ordem, e **nenhum deles é
"hidráulico por omissão"**:

1. **Disciplina (`GRUPO_PECA.PROJETO_APLICACAO`)** vem do que a fonte declara — categoria da família
   Revit, entidade do IFC, seção do catálogo de plugin, escolha de quem importa. É bitmask
   (`docs/conhecimento/aplicacoes-builder.md`), não enum.
2. **Aplicação (`PECA.TIPO_APLICACAO_PECA`)** vem da **entidade IFC** quando a fonte a dá, pela
   tabela medida no catálogo oficial do Builder; só na falta dela cai no vocabulário por nome — e
   num vocabulário **da disciplina escolhida no passo 1**, não no de PVC hidráulico.
3. **Sem disciplina reconhecida, avisa** — no resumo da exportação e no `validar_aq` — em vez de
   escolher hidráulico calado.

Os quatro valores de `PROJETO_APLICACAO` do `aq_writer` são corrigidos para o que o catálogo oficial
usa: água fria **4** (era 12, que é hidráulico + sanitário) e incêndio **20** (era 22, que carrega um
bit não identificado); esgoto **8** e gás **36** já estavam certos.

Entra no mesmo pacote o **modo de posicionamento** (`PECA.POSICIONAR_SIMBOLOGIA_3D`), que decide a
orientação da peça ao ser lançada: `catalogo_to_aq` grava 3 ("na horizontal, apontando para a
tubulação de entrada") em toda peça, quando conexão quer 0 ("no plano formado pelos condutos" —
8.039 de 10.467 no catálogo oficial) e tubo quer nulo (2.104 de 2.104). Como as outras duas, é
escolha por aplicação, não valor fixo.

## Por quê

A engenharia do Builder, testando nossas bibliotecas, encontrou **peças elétricas cadastradas com
aplicação hidráulica** — uma biblioteca de válvulas e atuadores de HVAC saiu inteira como "Conexão".
Não é um caso isolado: é o comportamento projetado do classificador atual.

`aq_writer.REGRAS_GRUPO` casa o **nome do grupo** contra um vocabulário de catálogo hidráulico em PVC
(tubo, bomba, ralo, sifão, joelho, luva, redução…) e, **sem regra que case, devolve conexão
genérica**. `aplicacao_de` decide a disciplina por quatro palavras no título — esgoto, incêndio, gás,
senão água fria. Ambos nasceram calibrados contra as primeiras bibliotecas importadas, que eram
hidráulicas; o comentário no código diz isso com todas as letras ("é o vocabulário de um catálogo
hidráulico em PVC"). Enquanto as fontes foram hidráulicas, o *default* acertava; com elétrica, SPDA,
climatização e fotovoltaico ele erra **toda** peça.

A medição que dá o mapa está em `docs/conhecimento/aplicacoes-builder.md`: `PROJETO_APLICACAO` é
bitmask de sete disciplinas identificadas, `TIPO_APLICACAO_PECA` é um enum de 84 valores com papel
definido por disciplina, e a entidade IFC prevê a aplicação com pouca ambiguidade (2067 → dispositivo
elétrico em 3.032 de 3.936 peças; 2052/2072/2054/2086 → tubo em 100 %; 2102 → condensadora em 100 %).
Nosso escritor conhece sete entidades IFC, **todas hidráulicas**.

## Consequências

- Uma biblioteca elétrica exportada daqui deixa de ser oferecida no lançamento hidráulico. É o
  defeito de maior alcance dos que sobraram: não impede a peça de abrir nem de desenhar, e por isso
  passou por três aceitações no Builder sem ser visto.
- O classificador deixa de ser uma tabela só e passa a ser uma por disciplina; o vocabulário
  hidráulico atual vira a tabela da disciplina hidráulica, sem perda.
- Fontes que não declaram disciplina nenhuma (um IFC solto, um STEP) passam a exigir escolha de quem
  importa. É trabalho a mais na tela do criador, e é a decisão certa: o programa não tem como
  adivinhar, e adivinhar errado é o defeito que estamos corrigindo.
- Os `.aq` já entregues continuam com a aplicação errada. Uma ferramenta de conserto é possível pelo
  mesmo caminho das outras (`preencher_*`), mas depende de saber a disciplina de cada biblioteca —
  ou seja, de perguntar — e a decisão de 2026-09-10 foi **não** fazê-la (ver abaixo).

## O que o usuário decidiu (2026-09-10)

As quatro escolhas que faltavam, e que tiram esta ADR de Proposta:

1. **O criador sempre pergunta**, com o campo pré-preenchido pelo palpite da fonte. Não existe
   importação sem disciplina: o campo é obrigatório nos três formulários (`POST /importacoes`,
   `/importacoes/plugin-autocad`, `/importacoes/familias-revit`) e o DTO recusa o corpo sem ele.
   Custa um clique por importação, e nunca mais exporta uma disciplina que ninguém olhou.
2. **Uma disciplina por biblioteca**, sem exceção por grupo. É o mais simples de implementar e de
   explicar; biblioteca mista sai errada em parte das peças, e isso é sabido.
3. **Sem aplicação reconhecida, avisa e grava o genérico da disciplina** — não aborta. Uma
   biblioteca de 3.000 peças não fica refém de cinco peças estranhas, e o aviso sai no resumo da
   exportação e na conferência "aplicação e disciplina" do `validar_aq`.
4. **As sete disciplinas ganham vocabulário**, derivado dos nomes de grupo mais frequentes de cada
   aplicação no catálogo oficial. O hidráulico atual vira o da disciplina hidráulica, sem perda.

E uma quinta, sobre os arquivos já entregues: **não** se faz ferramenta de conserto — os catálogos
seguem no criador e reexportar pelo pipeline corrigido dá o mesmo resultado sem código novo para
manter. O que a exportação faz com um catálogo antigo, sem disciplina gravada, é **recusar** e
pedir — não adivinhar.

## Como ficou implementado

`bim_pipeline/aq/cadastro.py` é o construtor único do cadastro (`GRUPO_PECA` + `PECA`) que os dois
escritores chamam — o que também acaba com as divergências que eles tinham
(`POSICIONAR_SIMBOLOGIA_3D` 0 × 3, `INDICE_SIMBOLO3D_SELECIONADO` -1 × 1, ambas resolvidas pelo
valor medido). `aq_writer` ficou com o que é do **arquivo** (schema, sentinelas, `EscritorAq` em
cp1252); saíram dele `REGRAS_GRUPO`, `classificar_grupo`, `aplicacao_de`, as quatro constantes
`APLICACAO_*` e a tabela de diâmetro em milímetro (esta virou ADR-025).

A disciplina viaja: formulário → DTO → `bim_catalogs.disciplina` → manifesto (contrato
`manifesto-catalogo-aq`, onde é campo obrigatório) → `catalogo_to_aq`/`geo_to_aq`. As três listas
de disciplina (Python, `pacotes/base`, `web`) são cópias deliberadas, e o que as impede de divergir
é `tests/arquitetura/test_disciplinas.py`.
