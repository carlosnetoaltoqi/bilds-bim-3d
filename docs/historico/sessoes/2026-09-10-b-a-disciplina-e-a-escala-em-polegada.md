# 2026-09-10 (parte 3) — a disciplina passa a ser perguntada, e a escala de bitola não era em milímetro

Sessão curta em decisão e longa em consequência: o usuário pediu para **listar o que precisava
decidir** para a exportação `.aq` incorporar tudo o que as duas sessões anteriores aprenderam,
decidir em bloco e implementar de uma vez. São sete decisões, e duas medições no catálogo oficial
mudaram o que ia ser escrito.

## 1. O que já estava medido e não precisava de decisão

Entrou direto, porque a medição no `Catalog.db` (schema 625, 31.611 peças) já decidia:

- `PROJETO_APLICACAO` de água fria **4** (era 12 = hidráulico + sanitário) e de incêndio **20**
  (era 22, com um bit não identificado). Esgoto 8 e gás 36 já estavam certos.
- `POSICIONAR_SIMBOLOGIA_3D` deixa de ser fixo e sai da aplicação: nulo em tubo (2.104/2.104), 0 em
  conexão (8.039/10.467), 1 em registro, 3 em bomba, 2 em dispositivo elétrico e na climatização.
- A ponte `ENTIDADE_IFC` → aplicação vira tabela de verdade: 31 entidades com a tripla
  (`TIPO_ENTIDADE_IFC`, `ENTIDADE_IFC_2X3`) medida, contra as 7 que o escritor conhecia — todas
  hidráulicas.
- `LIGACAO_EP` continua 0: sem resposta da engenharia não há o que decidir.

## 2. As sete decisões do usuário

| # | Pergunta | Decisão |
|---|---|---|
| 1 | De onde vem a disciplina, e quando o criador pergunta? | **Sempre pergunta**, campo obrigatório pré-preenchido pelo palpite da fonte |
| 2 | Em que granularidade? | **Uma por biblioteca**, sem exceção por grupo |
| 3 | Sem aplicação reconhecida? | **Avisa e grava o genérico** da disciplina — não aborta |
| 4 | Que vocabulários entram? | **As sete disciplinas** |
| 5 | A escala de `DIAMETRO_EP` incompleta? | **Medir no `Catalog.db` primeiro** |
| 6 | Consertar os `.aq` já entregues? | **Não** — reexportar da fonte |
| 7 | Unificar os dois escritores? | **Sim**, num construtor só |

## 3. A medição que derrubou uma premissa (ADR-025)

A decisão 5 mandou medir antes de perguntar à engenharia, e a medição respondeu mais do que se
esperava: **a escala não é em milímetro, é em polegada**. Cruzando `ENTRADA_PECA.DIAMETRO_EP` com
`PECA.NOME_PECA` nas 33.041 entradas do catálogo oficial, os códigos 0…17 são o índice de
1/4", 3/8", 1/2", 5/8", 3/4", 1", 1.1/4", 1.1/2", 2", 2.1/2", 3", 4", 5", 6", 8", 10", 12" — com
centenas de peças em cada um.

Duas consequências:

- **`60 → 10` era invenção.** Estava na nossa tabela por interpolação sobre amostra pequena; no
  catálogo inteiro, 60 mm aparece **só** no código 9.
- **Milímetro é ambíguo de propósito.** 40 mm é 1.1/4" (7) em PVC soldável e 1.1/2" (8) em esgoto;
  50 mm é 8 ou 9; 75 mm é 10 ou 11. Nossa tabela era a do esgoto, e errava toda bitola de soldável
  por um degrau. Agora a série sai do título da biblioteca e, sem ela, essas três bitolas saem
  **sem código, com aviso** — a sentinela, como fazem as conexões nativas.

O primeiro cruzamento tentado (código × `DIAMETRO_PECA`) não deu nada, porque `DIAMETRO_PECA`
guarda ora medida real, ora o próprio código. Foi o **nome da peça** que separou as duas coisas —
vale como método: quando a coluna numérica não fala, o nome fala.

## 4. Os seis prints do Builder — ADR-023 aceita

No meio da sessão o usuário mandou seis telas do Cadastro com as bibliotecas exportadas depois da
correção. Dentro da **mesma biblioteca nossa** (válvulas e atuadores de HVAC, de famílias Revit):

- peça com entradas → **"Pontos de ligação 3D: Sim"**, e a linha *Entradas* some da lista;
- peça com `Entradas: 0` → o campo aparece **desabilitado**, em cinza, com "Não".

O par fecha o ADR-023 e confirma a ajuda: a propriedade é **alternativa** a *Entradas*. O que não
deu para fazer: cruzar peça a peça o valor gravado com o rótulo — os `.aq` do teste já não estavam
em `Downloads/teste-geometria-aq/`. A leitura se apoia no contraste dentro de um arquivo só.

As mesmas telas trouxeram a prova visual do ADR-024: atuadores de HVAC e um aquecedor a gás com
**"Aplicação: Conexão"**.

Também saiu daí uma confirmação lateral: nenhuma das peças das telas está no `Catalog.db`, e as
31.611 peças oficiais têm `PECA.BIBLIOTECA` **vazia** — a assinatura que separa nativa de saída
nossa (`aq-formato.md`) vale também contra o catálogo oficial.

## 5. O que foi escrito

- **`biblioteca/bim_pipeline/aq/cadastro.py`** (novo, ~470 linhas): o construtor único do cadastro.
  Sete disciplinas com máscara, 31 entidades IFC com tripla e aplicação, sete vocabulários,
  posicionamento por aplicação, a escala em polegada, e o `Diagnostico` que coleta o que a
  exportação não soube decidir.
- **`aq_writer.py`** perdeu `REGRAS_GRUPO`, `classificar_grupo`, `aplicacao_de`, as quatro
  `APLICACAO_*`, as constantes `IFC_*`/`SUB_*`/`APL_*` e o `CODIGO_DIAMETRO`. Ficou com o que é do
  **arquivo**: schema, sentinelas, `EscritorAq` em cp1252.
- **Os dois escritores** chamam `cadastro.linha_grupo`/`linha_peca`. As divergências que tinham
  (`POSICIONAR_SIMBOLOGIA_3D` 0 × 3, `INDICE_SIMBOLO3D_SELECIONADO` -1 × 1) acabaram na raiz.
- **A disciplina viaja**: formulário (três telas, campo obrigatório com palpite) → DTO → 
  `bim_catalogs.disciplina` → manifesto (contrato, campo obrigatório) → escritor. Exportar catálogo
  sem disciplina é **recusado** com a mensagem dizendo o que escolher.
- **`validar_aq`** ganhou a conferência "aplicação e disciplina": máscara com bits conhecidos, aplicação no enum 1…84,
  posicionamento nulo só em tubo, e **aviso** quando uma disciplina inteira ficou no genérico.
- **Testes**: `tests/biblioteca/test_cadastro.py` (8) e `tests/arquitetura/test_disciplinas.py` (4,
  a paridade das três listas de disciplina). Suíte em 268 na coleta (era 240), verde.

Um defeito real apareceu ao escrever os testes: `\bTUBO\b` não casa com "Tubos", e "Tubos" é o nome
de grupo mais comum do catálogo oficial. O vocabulário passou a aceitar plural em `S`.

## 6. Onde a próxima sessão começa

1. **Reexportar as bibliotecas** pelo pipeline corrigido, informando a disciplina de cada uma, e
   abrir no Builder para conferir que a aplicação agora sai certa (a de HVAC é o caso de teste: tem
   de deixar de dizer "Conexão"). É a aceitação do ADR-024 e do ADR-025 de uma vez — e, no mesmo
   arquivo, dá para conferir se o `POSICIONAR_SIMBOLOGIA_3D` por aplicação orienta a peça certo no
   lançamento, que é o que os prints **não** permitiram concluir (as telas mostram três modos
   diferentes em bibliotecas diferentes, sem os arquivos para cruzar).
2. **Uma pergunta a menos para a engenharia**: a escala de diâmetros saiu por medição. Sobra
   `LIGACAO_EP` — o que é "Ligação" na aba de entradas do Cadastro.
3. As pendências que não dependem disso seguem onde estavam: aceitação dos `.aq` de plugin web e de
   famílias Revit, leitura humana dos documentos de `docs/conhecimento/`, revogar o secret da APS,
   LICENSE.

## 7. Estado verificável ao encerrar

| O quê | Estado | Como conferir |
|---|---|---|
| suíte | 268 na coleta (240 antes); 247 passam, 19 pulam por fixture ausente | `python3 -m pytest tests/biblioteca tests/arquitetura -m "not thumbs" -q` |
| build TS | os 9 workspaces compilam | `pnpm -r build` |
| ADRs | até ADR-025; 023 e 024 aceitas | `ls docs/decisoes/` |
| catálogo antigo sem disciplina | exportação recusa e diz o que escolher | `GET /exportar/catalogo/:id` |
