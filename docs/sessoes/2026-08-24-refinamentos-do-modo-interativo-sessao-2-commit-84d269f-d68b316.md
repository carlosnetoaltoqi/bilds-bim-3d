# 2026-08-24 — Refinamentos do modo interativo (sessão 2, commit 84d269f → d68b316)

**Data:** 2026-08-24 · Registro **extraído do `CLAUDE.md`** em 2026-09-04 (S7.8, I22) — esta
sessão não tinha arquivo próprio; o texto abaixo é o que havia lá, sem alteração.

---

**Slug removido do fluxo interativo**

A pergunta `Slug da URL [...]` foi removida — o slug é calculado automaticamente de
`slugify(titulo)` e apenas exibido. O usuário não precisa confirmar nem editar.

Motivação: slug é derivado do título; pedir os dois é redundante. Para alterar o slug
basta alterar o título.

**peek_aq usa hierarquia de pastas como fonte primária de título e fabricante**

Antes, `peek_aq` usava o campo `BIBLIOTECA` do banco e o filename do `.aq` como fallback,
produzindo títulos de baixa qualidade (ex: `"Esgoto Sn Sr Silentium"` do filename).

Correção: lê `parent_dir` (pasta pai do `.aq`) como título e `grandpa_dir` (avô) como
fabricante, antes de qualquer fallback por filename. Pasta pai é o nome real da linha de produto.

```
input/Amanco/PVC Esgoto SN, SR e Silentium/pecas.aq
              ↑ grandpa → fabricante        ↑ parent → título
```

Resultado: título sugerido passa a ser `"PVC Esgoto SN, SR e Silentium"` (correto) em vez de
`"Esgoto Sn Sr Silentium"` (ruim). Diretórios genéricos (`input`, `bim`, `.`) são ignorados.

**Regra de commits estabelecida**

Mensagens de commit devem descrever features e decisões, nunca associar a fabricantes ou
dados de input (fabricantes são variáveis e efêmeros).
- Correto: `feat(peek_aq): inferir título da pasta pai do .aq`
- Errado: `feat: pipeline validado com Amanco 502 IFCs`

**Ponto estável: commit `ff49845`** — pipeline completo, documentação autocontida, preview dos dois catálogos no repo.
Para retornar: `git checkout ff49845`.
