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

# 5. Configure o catálogo
cp config.example.json config.json
# Edite config.json com seus dados

# 6. Rode o build
python3 scripts/build.py --config config.json

# 7. Visualize localmente
python3 -m http.server 8080 --directory output/preview
# Abrir: http://localhost:8080
```

## Saídas

| Arquivo | Uso |
|---|---|
| `output/preview/index.html` | Preview local ou via Vercel |
| `output/bilds-upload.zip` | Upload no dashboard.bilds.com |

## Layouts

| `series-rows` | Linhas por série, estilo Netflix. Para catálogos com poucas famílias de bombas/equipamentos. |
|---|---|
| `catalog-grid` | Grid denso com filtros. Para catálogos com muitos itens heterogêneos (conexões, fitting, válvulas). |

Configure em `config.json`: `"layout": "series-rows"` ou `"layout": "catalog-grid"`.

## Opções do build.py

```bash
python3 scripts/build.py --config config.json    # pipeline completo
python3 scripts/build.py --skip-ifc              # pula parse dos IFCs (re-usa output/geo/)
python3 scripts/build.py --skip-preview          # só gera catalog.json e ZIP
python3 scripts/build.py --skip-zip              # só gera preview
```

## Preview via Vercel

```bash
# Deploy manual do preview
vercel deploy output/preview/ --prod
```

## Requisitos

- Python 3.8+
- `pip install jinja2`
- bash (para setup_vendor.sh)
- curl (para setup_vendor.sh)
