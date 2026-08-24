# bilds-bim-3d

Pipeline para gerar catálogos BIM interativos com viewer 3D a partir de arquivos `.aq` e `.IFC` do AltoQi.

## Início rápido

```bash
# 1. Clone e configure
git clone https://github.com/carlosnetoaltoqi/bilds-bim-3d.git
cd bilds-bim-3d

# 2. Instale dependências Python
pip install -r requirements.txt

# 3. Baixe Three.js (uma vez)
bash scripts/setup_vendor.sh

# 4. Coloque seus arquivos em input/
#    .IFC — um por produto
#    .aq  — biblioteca AltoQi

# 5. Rode o build em modo interativo
python3 scripts/build.py --interactive
# O CLI detecta os arquivos e faz perguntas sobre o catálogo

# 6. Visualize localmente
python3 -m http.server 8080 --directory output/preview
# Abrir: http://localhost:8080/{slug-do-catalogo}
```

## Saídas

| Arquivo | Uso |
|---|---|
| `output/preview/index.html` | Índice dos catálogos — listagem de todos os builds |
| `output/preview/catalogs.json` | Registro automático de catálogos gerados |
| `output/preview/{slug}/index.html` | Preview do catálogo (gerado pelo build) |
| `output/preview/data/{slug}.json` | Geometria 3D de cada produto |
| `output/<slug>-AAAAMMDDHHMM.zip` | Upload no dashboard.bilds.com |

## Layouts

| `series-rows` | Linhas por série, estilo Netflix. Para catálogos com poucas famílias de bombas/equipamentos. |
|---|---|
| `catalog-grid` | Grid denso com filtros. Para catálogos com muitos itens heterogêneos (conexões, fitting, válvulas). |

Configure em `config.json`: `"layout": "series-rows"` ou `"layout": "catalog-grid"`.

## Opções do build.py

```bash
python3 scripts/build.py --interactive           # configura via perguntas (recomendado)
python3 scripts/build.py --config config.json    # usa config.json existente
python3 scripts/build.py --skip-ifc              # pula parse dos IFCs (re-usa output/geo/)
python3 scripts/build.py --skip-preview          # só gera catalog.json e ZIP
python3 scripts/build.py --skip-zip              # só gera preview
```

## Preview via Vercel

Após o build, commite o `output/preview/` e faça deploy com o CLI da Vercel:

```bash
git add output/preview/
git commit -m "build: catálogo {slug}"

# Deploy — rodar SEMPRE da raiz do repo
vercel --prod --yes
```

A página de índice fica em `bilds-bim-3d.vercel.app` e cada catálogo em `bilds-bim-3d.vercel.app/{slug}`.

> **Atenção:** nunca passar `output/preview` como argumento posicional para o `vercel` CLI.
> Isso cria um projeto novo indesejado. O `vercel.json` na raiz já aponta para `output/preview/`.

## Requisitos

- Python 3.8+
- `pip install -r requirements.txt` (instala Jinja2 + ifcopenshell)
- bash (para setup_vendor.sh)
- curl (para setup_vendor.sh)

> `ifcopenshell` é necessário para parsear IFCs com geometria B-rep paramétrica (IFCADVANCEDBREP), como os exportados pelo AltoQi Hidráulico/Elétrico. IFCs tessellados (exportados pelo CATIA/3DEXPERIENCE) funcionam sem ele.
