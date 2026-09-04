# 2026-08-24 — interactive_config: aq_stale, scan_input e inferência do .aq (commits c443f26…2a16399)

**Data:** 2026-08-24 · Registro **extraído do `CLAUDE.md`** em 2026-09-04 (S7.8, I22) — esta
sessão não tinha arquivo próprio; o texto abaixo é o que havia lá, sem alteração.

---

**Bug 7 — scan_input modo subdir com múltiplos IFCs quebrava o parse (commit f738987)**

`input/Dancor/` com 14 IFCs era detectado como modo `subdir` (1 produto = subdir inteiro).
O display name `"Dancor/ (14 IFCs)"` ia como chave do `file_map`; o parser tentava abrir
esse string como arquivo → AVISO + ZIP 0KB.

Correção: modo `subdir` só ativo quando cada subdir tem **exatamente 1 IFC**; caso contrário
cai em modo `recursive` (cada IFC = um produto).

**Bug 8 — aq_stale não resetava titulo/slug (commit 5e38b65)**

Quando o .aq mudava (ex: Amanco → Dancor), `fabricante` era resetado mas `titulo` e `slug`
continuavam vindo do `config.json` stale. Slugs errados (ex: `"amanco-conexoes"`) persistiam
para o novo catálogo.

Correção: quando `aq_stale=True`, `sug_titulo` e `sug_slug` derivam apenas dos hints/filename
do novo .aq, não do `ec` (config existente).

**Bug 9 — fabricante e título não inferidos do filename do .aq (commit 2a16399)**

Campo `BIBLIOTECA` na Dancor .aq está vazio → `hints['fabricante'] = ''` → prompt sem default.

Correção: `peek_aq()` analisa o filename após falha no banco:
- `pecas_dancor_bombas_incendio_2026_04.1.aq` → remove ruído (`pecas`, anos `2026`, versão `04`)
- 1º token restante = fabricante (`Dancor`)
- Tokens restantes = título (`Bombas Incendio`)

Resultado: usuário passa por `--interactive` (hoje a flag é aceita e ignorada — L1 da auditoria) só com Enter em todos os campos.

**Bug 10 — slugify não normalizava acentos (commit 8b4272a)**

`re.sub(r'[^a-z0-9]+', '-', s.lower())` convertia `ê` em `-` (não é ASCII).
`"Incêndio"` → `"inc-ndio"`. Corrigido com NFD + strip combining marks:
```python
s = unicodedata.normalize('NFD', s)
s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
```
Agora: `"Bombas de Combate a Incêndio"` → `"bombas-de-combate-a-incendio"`.

**Bug 11 — slug derivava de fabricante+1ªpalavra, não do título completo (commits 8b4272a, fbbf292)**

`sug_slug` usava `f"{fabricante}-{titulo.split()[0]}"` → `"dancor-bombas"` em vez de
`"bombas-de-combate-a-incendio"`. Além disso, `ec.get('slug')` tomava precedência e
exibia o slug antigo do `config.json` mesmo após o usuário alterar o título.

Correção: `sug_slug = slugify(titulo or fabricante or 'catalogo')` — sempre re-calculado
a partir do título confirmado na pergunta anterior, sem herdar valor do config.
