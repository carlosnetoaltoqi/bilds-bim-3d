# 2026-09-02 — Build completo das 15 bibliotecas e fix de thumbs na Vercel

**Data:** 2026-09-02 · Registro **extraído do `CLAUDE.md`** em 2026-09-04 (S7.8, I22) — esta
sessão não tinha arquivo próprio; o texto abaixo é o que havia lá, sem alteração.

---

Pipeline estático rodado sobre todos os `.aq` de `input/` — 15 bibliotecas de 6
fabricantes (Akato, Amanco, Dancor, Intelbras ×7, Komeco ×4, Maxbar). Todos os 15
ZIPs gerados e preview publicado em https://bilds-bim-3d.vercel.app via
`vercel --prod --yes` (677 MB de geometria, não vai ao git).

**Bug corrigido:** thumbs quebradas na Vercel. `./thumbs/` resolvia para `/thumbs/`
(raiz) quando `cleanUrls: true` serve a página em `/<slug>` sem barra final — mesmo
root cause do bug de `./data/` já documentado. Corrigido nos dois layouts com
`THUMB_BASE = '/' + CATALOG.slug + '/thumbs/'`. Commit `4da3ab2`.
