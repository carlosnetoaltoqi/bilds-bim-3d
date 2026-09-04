# 2026-09-02 — Ambos os layouts para cada biblioteca + cores por fabricante no índice

**Data:** 2026-09-02 · Registro **extraído do `CLAUDE.md`** em 2026-09-04 (S7.8, I22) — esta
sessão não tinha arquivo próprio; o texto abaixo é o que havia lá, sem alteração.

---

`build.py` ganhou `--layout series-rows|catalog-grid`: quando combinado com `--all`,
força o layout especificado e sufixo o slug (`-grid` ou `-series`) sem re-extrair
geometria (usa o geo_dir do slug base). Rodado duas vezes com `--skip-zip` →
45 entradas no `catalogs.json` (15 auto + 15 -grid + 15 -series), 7.516 arquivos
na Vercel (3× os 4.318 anteriores).

`index.html` atualizado: linhas ordenadas por fabricante → título → layout, com
banda de cor alternada branco / azul claro (`#EEF3FF`) por grupo de fabricante.
6 fabricantes → 3 grupos brancos (Akato, Dancor, Komeco) e 3 azuis (Amanco,
Intelbras, Maxbar).

Commit `117a9f1`.
