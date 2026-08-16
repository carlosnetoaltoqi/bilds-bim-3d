#!/usr/bin/env python3
"""
build.py — Pipeline completo: .aq + .IFC → preview HTML + ZIP para bilds.com

Uso:
  python3 scripts/build.py --config config.json

config.json:
  {
    "slug":        "bombas-incendio",
    "titulo":      "Bombas de Combate a Incêndio",
    "fabricante":  "Dancor",
    "descricao":   "Linha CAM-W e TJM para sistemas prediais de combate a incêndio.",
    "layout":      "series-rows",        // "series-rows" | "catalog-grid"
    "aq_file":     "input/biblioteca.aq",
    "ifc_dir":     "input/",
    "file_map":    { "CAM-W10.IFC": "cam-w10", ... },
    "products_override": []              // produtos no IFC mas ausentes no .aq
  }

Saídas:
  output/preview/index.html        — HTML standalone para visualização local/Vercel
  output/preview/catalog.json      — dados do catálogo (copiado)
  output/preview/data/<slug>.json  — geometria de cada produto
  output/preview/vendor/           — Three.js (copiado de templates/vendor/)
  output/bilds-upload.zip          — ZIP para upload na bilds.com

Visualização local após o build:
  python3 -m http.server 8080 --directory output/preview
  Abrir: http://localhost:8080
"""
import argparse
import json
import os
import re
import shutil
import sys
import zipfile

# Adiciona scripts/ ao path para importar os módulos irmãos
sys.path.insert(0, os.path.dirname(__file__))

from parse_ifc import parse_ifc_file
from dedup import dedup
from read_aq import extract as extract_aq, build_product_map

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(ROOT, 'templates')
OUTPUT_DIR = os.path.join(ROOT, 'output')
PREVIEW_DIR = os.path.join(OUTPUT_DIR, 'preview')
GEO_DIR = os.path.join(OUTPUT_DIR, 'geo')


# ─── Matching IFC → AQ ───────────────────────────────────────────────────────

def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def find_aq_product(slug, product_map):
    """
    Tenta associar um slug de IFC a um grupo/peça no product_map do .aq.
    Usa matching por prefixo normalizado.
    Retorna (nome_gp, peca_dict) ou None.
    """
    slug_norm = slugify(slug)
    for nome_gp, group in product_map.items():
        gp_norm = slugify(nome_gp)
        if gp_norm.startswith(slug_norm[:12]) or slug_norm.startswith(gp_norm[:12]):
            pecas = group['pecas']
            if pecas:
                return nome_gp, pecas[0]  # pega a primeira variante do grupo
    return None


# ─── Geração do catalog.json ──────────────────────────────────────────────────

def build_catalog(config, product_map, geo_files):
    """
    Combina dados do .aq com os slugs dos IFCs para gerar catalog.json.

    catalog.json schema:
    {
      "slug": "...",
      "titulo": "...",
      "fabricante": "...",
      "descricao": "...",
      "layout": "series-rows" | "catalog-grid",
      "filtros": ["W", "TJM", ...],
      "produtos": [
        {
          "id": "cam-w10",
          "nome": "CAM-W10 1CV T 220/380V INC FLG IR3",
          "serie": "CAM-W10",
          "geo": "cam-w10.json",
          "potencia": 1.0,
          "conexoes": "1½\" × 1½\"",
          "specs": { "Tensão": "...", "Rotação": "..." },
          "curva": [[vazao, altura, potencia, rend], ...] | null
        }
      ]
    }
    """
    file_map = config.get('file_map', {})
    overrides_by_slug = {p['id']: p for p in config.get('products_override', [])}

    produtos = []
    series_set = set()

    for ifc_name, slug in file_map.items():
        if slug not in geo_files:
            print(f'  AVISO: geo/{slug}.json não encontrado (IFC não foi parseado?)')
            continue

        if slug in overrides_by_slug:
            p = overrides_by_slug[slug].copy()
            p['geo'] = f'{slug}.json'
            produtos.append(p)
            series_set.add(p.get('serie', ''))
            continue

        match = find_aq_product(slug, product_map)
        if match is None:
            print(f'  AVISO: {slug} não encontrado no .aq — usando stub mínimo')
            produtos.append({
                'id': slug,
                'nome': slug.replace('-', ' ').upper(),
                'serie': '',
                'geo': f'{slug}.json',
                'potencia': None,
                'conexoes': '',
                'specs': {},
                'curva': None,
            })
            continue

        nome_gp, peca = match
        serie = nome_gp.split()[0] if ' ' in nome_gp else nome_gp

        # Extrai potência do nome do grupo ou specs
        pot = None
        pot_match = re.search(r'(\d+(?:[.,]\d+)?)\s*CV', nome_gp, re.IGNORECASE)
        if pot_match:
            pot = float(pot_match.group(1).replace(',', '.'))
        elif 'potencia_cv' in peca:
            pot = peca.get('potencia_cv')

        # Curva Q-H: lista de [vazao, altura, potencia, rendimento]
        curva = None
        if peca.get('curva_pts'):
            curva = peca['curva_pts']

        produto = {
            'id': slug,
            'nome': peca['nome'],
            'serie': serie,
            'geo': f'{slug}.json',
            'potencia': pot,
            'conexoes': peca.get('conexoes', ''),
            'specs': peca.get('specs', {}),
            'curva': curva,
        }
        produtos.append(produto)
        series_set.add(serie)

    # Adiciona overrides que não estavam no file_map
    for slug, p in overrides_by_slug.items():
        if slug not in file_map.values():
            p2 = p.copy()
            p2['geo'] = f'{slug}.json'
            produtos.append(p2)
            series_set.add(p.get('serie', ''))

    filtros = sorted([s for s in series_set if s])

    return {
        'slug': config['slug'],
        'titulo': config['titulo'],
        'fabricante': config['fabricante'],
        'descricao': config.get('descricao', ''),
        'layout': config.get('layout', 'series-rows'),
        'filtros': filtros,
        'produtos': produtos,
    }


# ─── Parse dos IFCs ───────────────────────────────────────────────────────────

def run_ifc_parse(config):
    """Parseia todos os IFCs do file_map e salva JSONs deduplicados em output/geo/."""
    file_map = config.get('file_map', {})
    ifc_dir = config.get('ifc_dir', 'input/')
    os.makedirs(GEO_DIR, exist_ok=True)

    parsed = []
    for ifc_name, slug in file_map.items():
        ifc_path = None
        for candidate in [
            os.path.join(ifc_dir, ifc_name),
            os.path.join(ifc_dir, ifc_name.lower()),
        ]:
            if os.path.exists(candidate):
                ifc_path = candidate
                break

        if not ifc_path:
            # Fuzzy: prefixo de 20 chars
            prefix = ifc_name[:20].lower()
            for fname in os.listdir(ifc_dir):
                if fname.lower()[:20] == prefix:
                    ifc_path = os.path.join(ifc_dir, fname)
                    break

        if not ifc_path:
            print(f'  AVISO: {ifc_name} não encontrado em {ifc_dir}')
            continue

        out_path = os.path.join(GEO_DIR, f'{slug}.json')
        print(f'  Parseando: {ifc_name} → {slug}.json')
        try:
            raw = parse_ifc_file(ifc_path)
            n_raw = len(raw['pos']) // 3
            result, orig, dedup_n, pct = dedup(raw)
            with open(out_path, 'w') as f:
                json.dump(result, f, separators=(',', ':'))
            size_kb = os.path.getsize(out_path) / 1024
            print(f'    {orig} → {dedup_n} vértices ({pct:.0f}% redução), {size_kb:.0f}KB')
            parsed.append(slug)
        except Exception as e:
            print(f'  ERRO ao parsear {ifc_name}: {e}')

    return parsed


# ─── Build do preview HTML ────────────────────────────────────────────────────

def build_preview(catalog, layout):
    """
    Gera output/preview/{slug}/ com index.html, catalog.json e data/.
    Arquivos compartilhados (vendor/) ficam em output/preview/vendor/.
    Cada catálogo fica em seu próprio subdiretório para não sobrescrever o índice.
    """
    catalog_slug = catalog['slug']
    catalog_dir = os.path.join(PREVIEW_DIR, catalog_slug)
    os.makedirs(catalog_dir, exist_ok=True)

    # data/ fica no root do preview (compartilhado entre catálogos)
    data_dir = os.path.join(PREVIEW_DIR, 'data')
    os.makedirs(data_dir, exist_ok=True)

    # Copia geo files para /data/ (prefixo do slug garante unicidade)
    for produto in catalog['produtos']:
        geo_slug = produto['geo'].replace('.json', '')
        src = os.path.join(GEO_DIR, f'{geo_slug}.json')
        if os.path.exists(src):
            shutil.copy(src, os.path.join(data_dir, f'{geo_slug}.json'))

    # vendor/ fica no root do preview (compartilhado)
    vendor_src = os.path.join(TEMPLATES_DIR, 'vendor')
    vendor_dst = os.path.join(PREVIEW_DIR, 'vendor')
    if os.path.exists(vendor_src) and os.listdir(vendor_src):
        if not os.path.exists(vendor_dst):
            shutil.copytree(vendor_src, vendor_dst)
    else:
        print('  AVISO: templates/vendor/ vazio — rode scripts/setup_vendor.sh')

    # Salva catalog.json no diretório do catálogo
    cat_path = os.path.join(catalog_dir, 'catalog.json')
    with open(cat_path, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    # Renderiza template HTML
    template_path = os.path.join(TEMPLATES_DIR, 'layouts', f'{layout}.html')
    if not os.path.exists(template_path):
        print(f'  ERRO: template {layout}.html não encontrado em templates/layouts/')
        print(f'  Templates disponíveis: {os.listdir(os.path.join(TEMPLATES_DIR, "layouts"))}')
        return False

    if HAS_JINJA2:
        env = Environment(
            loader=FileSystemLoader(os.path.join(TEMPLATES_DIR, 'layouts')),
            undefined=StrictUndefined,
            autoescape=False,
        )
        tmpl = env.get_template(f'{layout}.html')
        html = tmpl.render(catalog=catalog, items=catalog['produtos'])
    else:
        with open(template_path, encoding='utf-8') as f:
            html = f.read()
        html = html.replace('{{ catalog | tojson | safe }}', json.dumps(catalog, ensure_ascii=False))
        html = html.replace('{{ items | tojson | safe }}', json.dumps(catalog['produtos'], ensure_ascii=False))

    out_html = os.path.join(catalog_dir, 'index.html')
    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(html)

    return True


def update_catalog_registry(catalog):
    """Atualiza output/preview/catalogs.json com a entrada do catálogo gerado."""
    import datetime
    registry_path = os.path.join(PREVIEW_DIR, 'catalogs.json')

    registry = []
    if os.path.exists(registry_path):
        with open(registry_path, encoding='utf-8') as f:
            try:
                registry = json.load(f)
            except json.JSONDecodeError:
                registry = []

    registry = [e for e in registry if e.get('slug') != catalog['slug']]
    registry.append({
        'slug': catalog['slug'],
        'titulo': catalog['titulo'],
        'fabricante': catalog['fabricante'],
        'descricao': catalog.get('descricao', ''),
        'layout': catalog.get('layout', 'series-rows'),
        'n_produtos': len(catalog['produtos']),
        'updated_at': datetime.date.today().isoformat(),
    })

    os.makedirs(PREVIEW_DIR, exist_ok=True)
    with open(registry_path, 'w', encoding='utf-8') as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

    print(f'    Índice: {len(registry)} catálogo(s) registrado(s)')


# ─── Empacotamento ZIP ────────────────────────────────────────────────────────

def build_zip(catalog):
    """
    Gera output/bilds-upload.zip com:
      manifest.json    — slug, titulo, fabricante, descricao, layout
      catalog.json     — dados completos dos produtos
      geo/<slug>.json  — geometria de cada produto
    """
    zip_path = os.path.join(OUTPUT_DIR, 'bilds-upload.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # manifest
        manifest = {
            'slug': catalog['slug'],
            'titulo': catalog['titulo'],
            'fabricante': catalog['fabricante'],
            'descricao': catalog['descricao'],
            'layout': catalog['layout'],
            'filtros': catalog['filtros'],
            'n_produtos': len(catalog['produtos']),
        }
        zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))

        # catalog.json
        zf.writestr('catalog.json', json.dumps(catalog, ensure_ascii=False, separators=(',', ':')))

        # geo files
        for produto in catalog['produtos']:
            slug = produto['geo'].replace('.json', '')
            geo_path = os.path.join(GEO_DIR, f'{slug}.json')
            if os.path.exists(geo_path):
                zf.write(geo_path, f'geo/{slug}.json')
            else:
                print(f'  AVISO: geo/{slug}.json não encontrado — não incluído no ZIP')

    size_kb = os.path.getsize(zip_path) / 1024
    print(f'ZIP: {zip_path} ({size_kb:.0f}KB)')
    return zip_path


# ─── Pipeline principal ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='bilds-bim-3d build pipeline')
    parser.add_argument('--config', default='config.json', help='Arquivo de configuração')
    parser.add_argument('--skip-ifc', action='store_true', help='Pula parse dos IFCs')
    parser.add_argument('--skip-preview', action='store_true', help='Pula geração do preview HTML')
    parser.add_argument('--skip-zip', action='store_true', help='Pula geração do ZIP')
    args = parser.parse_args()

    config_path = os.path.join(ROOT, args.config)
    if not os.path.exists(config_path):
        print(f'Config não encontrado: {config_path}')
        print(f'Copie config.example.json para config.json e edite.')
        sys.exit(1)

    with open(config_path, encoding='utf-8') as f:
        config = json.load(f)

    print(f'\n=== bilds-bim-3d: {config["titulo"]} ===\n')

    # 1. Parse dos IFCs
    if not args.skip_ifc:
        print('1/4 Parseando IFCs...')
        geo_files = run_ifc_parse(config)
        print(f'    {len(geo_files)} geometrias geradas\n')
    else:
        geo_files = [f.replace('.json', '') for f in os.listdir(GEO_DIR)
                     if f.endswith('.json')] if os.path.exists(GEO_DIR) else []

    # 2. Lê o .aq
    aq_path = os.path.join(ROOT, config.get('aq_file', 'input/biblioteca.aq'))
    product_map = {}
    if os.path.exists(aq_path):
        print('2/4 Lendo biblioteca .aq...')
        aq_data = extract_aq(aq_path)
        product_map = build_product_map(aq_data)
        print(f'    {len(product_map)} grupos, '
              f'{sum(len(g["pecas"]) for g in product_map.values())} peças\n')
    else:
        print(f'2/4 .aq não encontrado ({aq_path}) — usando apenas overrides do config\n')

    # 3. Gera catalog.json
    print('3/4 Gerando catalog.json...')
    catalog = build_catalog(config, product_map, set(geo_files))
    cat_out = os.path.join(OUTPUT_DIR, 'catalog.json')
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(cat_out, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f'    {len(catalog["produtos"])} produtos, layout: {catalog["layout"]}\n')

    # 4a. Preview HTML
    if not args.skip_preview:
        print('4/4 Gerando preview HTML...')
        ok = build_preview(catalog, catalog['layout'])
        if ok:
            update_catalog_registry(catalog)
            print(f'    Preview: output/preview/{catalog["slug"]}/index.html')
            print(f'    Local:   python3 -m http.server 8080 --directory output/preview')
            print(f'    URL:     http://localhost:8080/{catalog["slug"]}')
            print()

    # 4b. ZIP para bilds.com
    if not args.skip_zip:
        print('Empacotando ZIP...')
        zip_path = build_zip(catalog)
        print(f'    Upload na bilds.com: {zip_path}\n')

    print('=== Build concluído ===')


if __name__ == '__main__':
    main()
