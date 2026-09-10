# ADR-024 — a disciplina da peça vem da fonte; hidráulico deixa de ser o *default*

**Status:** Proposta (2026-09-10)

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
  ou seja, de perguntar.
- **Fica proposta, não aceita:** o mapa está medido, mas a decisão toca a interface do criador (quem
  escolhe a disciplina e quando) e isso é do usuário.
