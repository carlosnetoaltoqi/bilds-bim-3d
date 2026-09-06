> **HISTÓRICO — arquivado em 2026-09-06 (S8/F1, ADR-009).** Estudo da S7.17 (2026-09-05) sobre um plugin de
> CAD que é casca de um catálogo web. O conhecimento técnico está em `docs/conhecimento/plugin-cad-catalogo-web.md`
> e `step-iges.md`; o adaptador é `bim_pipeline.catalogo.fontes.plugin_catalogo_web`. Ficam aqui o registro,
> os JSONs públicos capturados e as duas CLIs de conveniência da época (`exemplos/`, não executadas).
> `downloads/`, `saida/` e `dados/lead.local.json` são locais e gitignored — a autorização de uso
> cobre só o escopo registrado no estudo.

# eng-reversa/tupy — do plugin TupyCAD (AutoCAD) a uma biblioteca `.aq`

Estudo da S7.17 (2026-09-05): o plugin de AutoCAD da Tupy (plataforma Catallog) não carrega
geometria — abre um catálogo web cuja API é pública e serve um **IGES** por produto (e um `.rfa`
Revit por família). O IGES entra no pipeline do projeto pelo `step_to_geo.py` (costura das faces
soltas + orientação pelo volume) e sai em `.aq` pelo `catalogo_to_aq.py`. Resultado:
`saida/Tupy-TupyGrooved.aq` — 10 peças de 10 famílias TupyGrooved, validado pelos leitores do
projeto (ainda **não** aberto no AltoQi Builder).

O que foi para o produto está em `www/apps/ingestao/pipeline/{catallog,rfa_partatom,step_to_geo}.py`
e no botão **"Importar plugin do AutoCAD"** do web. Aqui ficam o estudo e as ferramentas que o produziram.

| Onde | O quê |
|---|---|
| `estudo/01-plugin-tupycad-e-catalogo-web.md` | **o estudo**: DLL, API do catálogo, formulário de download, Termos de Uso e o escopo autorizado, IGES/RFA/DXF, costura, validação do `.aq` |
| `tools/tupy_baixar.py` | plano por grupo e download idempotente (CLI fina sobre `catallog.py`); `--so-listar` mostra sem baixar |
| `tools/tupy_catalogo.py` | `downloads/` → `saida/{geo/,catalogo.json,manifesto-aq.json,Tupy-TupyGrooved.aq}` |
| `dados/` | JSONs públicos levantados (grupos e produtos de TupyGrooved nos dois hosts, settings, o formulário); `lead.local.json` (gitignored — dados pessoais do formulário) |
| `downloads/` (gitignored) | 22 arquivos, 39 MB: 11 `.rfa`, 10 `.igs`, 1 ZIP de DXF; `manifesto.json` (SHA-256, URL) e `grupos.json`; `.partatom.json`/`.preview.png` ao lado de cada `.rfa` |
| `saida/` (gitignored) | geometrias, catálogo, manifesto e o `.aq` |

Refazer tudo (≈ 3 min de download + 2 min de tesselação):

```bash
python3 eng-reversa/tupy/tools/tupy_baixar.py --lead eng-reversa/tupy/dados/lead.local.json
python3 www/apps/ingestao/pipeline/rfa_partatom.py eng-reversa/tupy/downloads/*/*.rfa
python3 eng-reversa/tupy/tools/tupy_catalogo.py
```

O download passa pelo formulário de lead do site com os dados de `lead.local.json` — use os
seus. Escopo autorizado: a categoria TupyGrooved; os Termos de Uso do catálogo proíbem
redistribuição (estudo, §2.2).
