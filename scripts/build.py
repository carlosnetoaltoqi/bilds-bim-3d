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
import datetime
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


def tokenize(s):
    """Tokens alfanuméricos em minúsculas extraídos de qualquer string."""
    return set(re.findall(r'[a-z0-9]+', s.lower()))


def find_aq_product(slug, product_map, ifc_path_hint=None):
    """
    Associa um IFC a um grupo/peça no product_map do .aq.

    Se ifc_path_hint for fornecido (caminho relativo do IFC, ex:
    'Curvas/Curva 45 curta SN/100mm.ifc'), usa todos os componentes do
    caminho como tokens de busca — útil quando a hierarquia de pastas
    encode informação do produto ausente no slug isolado.

    Estratégia:
    1. Fuzzy por cobertura: score = fração dos tokens do GRUPO_PECA
       cobertos pelos tokens do caminho completo.
       Prioriza grupo com cobertura máxima e mais tokens (mais específico).
       Dentro do grupo, seleciona a PECA com maior sobreposição com
       os tokens do nome do arquivo (sem extensão).
       Tenta primeiro cobertura 100%, relaxa para 75% se nada encontrado.
    2. Fallback por prefixo/número para IFCs flat sem hierarquia de pastas.

    Retorna (nome_gp, peca_dict) ou None.
    """
    if ifc_path_hint:
        # Tokens de todos os componentes do caminho (sem extensão do arquivo)
        path_no_ext = re.sub(r'\.[a-zA-Z0-9]+$', '', ifc_path_hint.replace('\\', '/'))
        query_tokens = tokenize(path_no_ext.replace('/', ' '))
        # Leaf: nome do arquivo sem extensão — usado para escolher PECA no grupo
        leaf_no_ext = path_no_ext.split('/')[-1]
        leaf_tokens = tokenize(leaf_no_ext)
    else:
        query_tokens = tokenize(slug)
        leaf_tokens = query_tokens

    # Passo 1: fuzzy por cobertura — tenta 100%, depois relaxa para 75%
    for min_score in (1.0, 0.75):
        best_score = -1.0
        best_spec = 0
        best_match = None

        for nome_gp, group in product_map.items():
            pecas = group.get('pecas', [])
            if not pecas:
                continue
            gp_tokens = tokenize(nome_gp)
            if not gp_tokens:
                continue
            covered = len(query_tokens & gp_tokens)
            gp_score = covered / len(gp_tokens)
            if gp_score < min_score:
                continue
            # Preferir o grupo mais específico (maior número de tokens cobertos)
            if gp_score > best_score or (gp_score == best_score and len(gp_tokens) > best_spec):
                # Dentro do grupo: PECA com maior sobreposição com o nome do arquivo
                peca_best = pecas[0]
                peca_best_score = -1.0
                for peca in pecas:
                    p_toks = tokenize(peca.get('nome', ''))
                    p_score = len(leaf_tokens & p_toks) / max(len(p_toks), 1)
                    if p_score > peca_best_score:
                        peca_best_score = p_score
                        peca_best = peca
                best_score = gp_score
                best_spec = len(gp_tokens)
                best_match = (nome_gp, peca_best)

        if best_match:
            return best_match

    # Passo 2: fallback por prefixo/número (IFCs flat sem hierarquia)
    slug_norm = slugify(slug)
    nums_slug = re.findall(r'\d+', slug_norm)
    for nome_gp, group in product_map.items():
        gp_norm = slugify(nome_gp)
        nums_gp = re.findall(r'\d+', gp_norm)
        prefix_match = (gp_norm.startswith(slug_norm[:12]) or slug_norm.startswith(gp_norm[:12])
                        or gp_norm in slug_norm)
        num_match = (bool(nums_gp) and nums_slug[:len(nums_gp)] == nums_gp)
        if prefix_match or num_match:
            pecas = group['pecas']
            if pecas:
                return nome_gp, pecas[0]
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

        match = find_aq_product(slug, product_map, ifc_path_hint=ifc_name)
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

        # Nome completo: combina grupo + peça quando o grupo não está no nome da peça
        nome_peca = peca['nome']
        if nome_gp.lower() not in nome_peca.lower():
            nome_peca = f'{nome_gp} {nome_peca}'

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
            'nome': nome_peca,
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
    Gera output/<slug>-AAAAMMDDHHMM.zip com:
      manifest.json    — slug, title, manufacturer, description, layout, filters, productCount
      catalog.json     — dados completos dos produtos (campos em português)
      geo/<slug>.json  — geometria de cada produto
    """
    ts = datetime.datetime.now().strftime('%Y%m%d%H%M')
    zip_name = f"{catalog['slug']}-{ts}.zip"
    zip_path = os.path.join(OUTPUT_DIR, zip_name)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # manifest: campos em inglês conforme contrato da API bilds.com
        manifest = {
            'slug':         catalog['slug'],
            'title':        catalog['titulo'],
            'manufacturer': catalog['fabricante'],
            'description':  catalog.get('descricao', ''),
            'layout':       catalog['layout'],
            'filters':      catalog['filtros'],
            'productCount': len(catalog['produtos']),
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


# ─── Modo interativo ─────────────────────────────────────────────────────────

def ask(prompt, default=None):
    """Pergunta ao usuário com sugestão de default."""
    full = f'  {prompt} [{default}]: ' if default else f'  {prompt}: '
    resp = input(full).strip()
    return resp if resp else (default or '')


def ask_choice(prompt, choices, default=None):
    """Pergunta com opções numeradas. Mostra padrão em destaque."""
    print(f'\n  {prompt}')
    for i, c in enumerate(choices, 1):
        marker = ' ◀ padrão' if c[0] == default else ''
        print(f'    {i}. {c[0]} — {c[1]}{marker}')
    while True:
        resp = input(f'  Escolha [1-{len(choices)}]: ').strip()
        if not resp and default:
            return default
        if resp.isdigit() and 1 <= int(resp) <= len(choices):
            return choices[int(resp) - 1][0]
        print(f'  Digite um número entre 1 e {len(choices)}.')


def peek_aq(aq_path):
    """
    Lê o .aq rapidamente para extrair hints antes das perguntas.
    Retorna dict: fabricante, grupos (list[str]), has_curves (bool)
    """
    from read_aq import open_aq
    hints = {'fabricante': '', 'grupos': [], 'has_curves': False}
    try:
        con, tmp = open_aq(aq_path)
        cur = con.cursor()
        try:
            cur.execute(
                "SELECT BIBLIOTECA FROM PECA "
                "WHERE BIBLIOTECA IS NOT NULL AND BIBLIOTECA != '' LIMIT 1"
            )
            r = cur.fetchone()
            if r:
                hints['fabricante'] = r[0].strip()
        except Exception:
            pass
        try:
            cur.execute('SELECT NOME_GP FROM GRUPO_PECA WHERE ATIVO=1 ORDER BY ID_GRUPO_PECA')
            hints['grupos'] = [r[0] for r in cur.fetchall()]
        except Exception:
            pass
        try:
            cur.execute('SELECT 1 FROM ITEM_CURVA_BOMBA LIMIT 1')
            hints['has_curves'] = cur.fetchone() is not None
        except Exception:
            pass
        con.close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        pass
    return hints


def scan_input(input_dir):
    """
    Detecta arquivos e modo de mapeamento IFC → produto.

    Três modos:
    - 'flat'     : IFCs direto em input_dir — cada .ifc = um produto (Dancor)
    - 'subdir'   : subdirs imediatos com IFCs — cada subdir = um produto
    - 'recursive': IFCs em qualquer nível — cada .ifc = um produto (Amanco)

    Retorna (ifc_entries, mode, aq_paths)
      ifc_entries: lista de (display_name, suggested_slug)
        - modo flat/subdir: display_name é o basename
        - modo recursive: display_name é o caminho relativo a partir de input_dir
      aq_paths: lista de caminhos absolutos para .aq (busca recursiva)
    """
    try:
        entries = os.listdir(input_dir)
    except FileNotFoundError:
        return [], 'flat', []

    # .aq: busca recursiva para pegar bibliotecas em subdirs (ex: Amanco)
    aq_paths = []
    for root, dirs, files in os.walk(input_dir):
        dirs.sort()
        for f in sorted(files):
            if f.lower().endswith('.aq'):
                aq_paths.append(os.path.join(root, f))

    ifc_flat = sorted(f for f in entries if f.lower().endswith('.ifc'))

    # Detecta subdirs imediatos que contêm IFCs
    subdir_counts = {}
    for d in sorted(entries):
        dpath = os.path.join(input_dir, d)
        if os.path.isdir(dpath):
            n = sum(1 for f in os.listdir(dpath) if f.lower().endswith('.ifc'))
            if n > 0:
                subdir_counts[d] = n

    if ifc_flat:
        entries_out = [
            (f, slugify(os.path.splitext(f)[0])[:40])
            for f in ifc_flat
        ]
        return entries_out, 'flat', aq_paths
    elif subdir_counts:
        entries_out = [
            (f'{d}/ ({subdir_counts[d]} IFCs)', slugify(d))
            for d in subdir_counts
        ]
        return entries_out, 'subdir', aq_paths
    else:
        # Busca recursiva: cada IFC é um produto; display_name = path relativo
        all_ifcs = []
        for root, dirs, files in os.walk(input_dir):
            dirs.sort()
            rel_root = os.path.relpath(root, input_dir)
            for f in sorted(files):
                if f.lower().endswith('.ifc'):
                    rel_path = os.path.join(rel_root, f) if rel_root != '.' else f
                    all_ifcs.append(rel_path)

        # Calcular prefixo comum de diretório para stripping nos slugs
        def common_dir_prefix(paths):
            if not paths:
                return ''
            parts_list = [p.replace(os.sep, '/').split('/')[:-1] for p in paths]
            common = parts_list[0]
            for parts in parts_list[1:]:
                common = [c for c, p in zip(common, parts) if c == p]
            return '/'.join(common) + '/' if common else ''

        import hashlib
        prefix = common_dir_prefix(all_ifcs)
        seen_slugs = {}
        entries_out = []
        for rel_path in all_ifcs:
            slug_base = rel_path.replace(os.sep, '/').replace(prefix, '', 1)
            slug_base = os.path.splitext(slug_base)[0].replace('/', '-')
            slug = slugify(slug_base)[:55]
            # garantir unicidade: sufixo de 4 chars do hash do path
            h = hashlib.md5(rel_path.encode()).hexdigest()[:4]
            if slug in seen_slugs and seen_slugs[slug] != rel_path:
                slug = slug[:50] + '-' + h
            seen_slugs[slug] = rel_path
            entries_out.append((rel_path, slug))
        return entries_out, 'recursive', aq_paths


def match_slug_to_aq(slug, grupos):
    """Tenta encontrar um NOME_GP do .aq que corresponda ao slug."""
    slug_norm = slugify(slug)
    best = None
    best_score = 0
    for g in grupos:
        g_norm = slugify(g)
        # Score: tamanho do prefixo comum
        score = 0
        for a, b in zip(slug_norm, g_norm):
            if a == b:
                score += 1
            else:
                break
        if score > best_score and score >= 3:
            best_score = score
            best = g
    return best


def interactive_config(input_dir, existing=None):
    """
    Configura o catálogo interativamente.
    existing: dict com valores do config.json atual (usados como defaults).
    """
    ec = existing or {}

    print('\n' + '─' * 60)
    print('  bilds-bim-3d — configuração do catálogo')
    print('─' * 60)
    if ec:
        print('  (valores entre colchetes são do config.json atual)')
    print()

    # ── Scan do input_dir ────────────────────────────────────────
    ifc_entries, mode, aq_paths = scan_input(input_dir)

    if not ifc_entries:
        print(f'  AVISO: nenhum IFC encontrado em {input_dir}')
        print(f'  O build usará os arquivos já presentes em output/geo/')
        print()

    n_ifc = len(ifc_entries)
    n_aq  = len(aq_paths)
    mode_labels = {'flat': 'arquivos individuais', 'subdir': 'subdirs de categoria',
                   'recursive': 'busca recursiva'}
    mode_label = mode_labels.get(mode, mode)
    print(f'  Encontrado(s): {n_ifc} produto(s) como {mode_label}, {n_aq} biblioteca(s) .aq')
    print()

    # ── Arquivo .aq ──────────────────────────────────────────────
    aq_file = None
    hints   = {}
    if not aq_paths:
        print('  Nenhuma biblioteca .aq — catálogo sem dados hidráulicos do AltoQi.')
        print()
    elif len(aq_paths) == 1:
        aq_file = aq_paths[0]
        print(f'  Lendo biblioteca: {os.path.basename(aq_file)}...')
        hints = peek_aq(aq_file)
        n_gp = len(hints['grupos'])
        curvas_txt = ', com curvas Q-H' if hints['has_curves'] else ', sem curvas Q-H'
        print(f'  → {n_gp} grupo(s) de produtos{curvas_txt}')
        if hints['fabricante']:
            print(f'  → fabricante detectado: {hints["fabricante"]}')
        print()
    else:
        print('  Múltiplas bibliotecas .aq:')
        for i, p in enumerate(aq_paths, 1):
            print(f'    {i}. {os.path.basename(p)}')
        while True:
            r = input(f'  Qual usar? [1-{len(aq_paths)}]: ').strip()
            if r.isdigit() and 1 <= int(r) <= len(aq_paths):
                aq_file = aq_paths[int(r) - 1]
                break
        print(f'  Lendo {os.path.basename(aq_file)}...')
        hints = peek_aq(aq_file)
        print()

    # ── Sugestões inteligentes ───────────────────────────────────
    # Detectar mudança de biblioteca .aq: hints prevalecem sobre config stale
    aq_stale = bool(
        aq_file and ec.get('aq_file') and
        os.path.abspath(aq_file) != os.path.abspath(
            os.path.join(ROOT, ec['aq_file']) if not os.path.isabs(ec['aq_file']) else ec['aq_file']
        )
    )
    if aq_stale:
        print('  AVISO: biblioteca .aq diferente do config.json anterior — reiniciando sugestões.\n')

    if aq_stale:
        sug_fabricante = hints.get('fabricante') or ''
        n_products     = n_ifc
        sug_layout     = (
            'series-rows' if hints.get('has_curves') else
            ('catalog-grid' if n_products > 6 else 'series-rows')
        )
    else:
        sug_fabricante = ec.get('fabricante') or hints.get('fabricante') or ''
        n_products     = n_ifc or len(ec.get('file_map', {}))
        sug_layout     = ec.get('layout') or (
            'series-rows' if hints.get('has_curves') else
            ('catalog-grid' if n_products > 6 else 'series-rows')
        )

    # ── Perguntas de metadados ───────────────────────────────────
    fabricante = ask('Fabricante', default=sug_fabricante)

    sug_titulo = (
        hints['grupos'][0].rsplit(' ', 1)[0] if hints.get('grupos') else ''
    ) if aq_stale else (
        ec.get('titulo') or (hints['grupos'][0].rsplit(' ', 1)[0] if hints.get('grupos') else '')
    )
    titulo = ask('Título do catálogo', default=sug_titulo)

    sug_slug = ec.get('slug') or slugify(
        (fabricante + '-' + titulo.split()[0]) if titulo else fabricante or 'catalogo'
    )
    slug = ask('Slug da URL', default=sug_slug)

    descricao = ask('Descrição curta (opcional)', default=ec.get('descricao') or '')

    layout = ask_choice(
        'Layout de exibição:',
        [
            ('series-rows',  'linhas por série — estilo Netflix, ideal para poucas famílias com curva Q-H'),
            ('catalog-grid', 'grade densa com filtros — ideal para muitos itens heterogêneos'),
        ],
        default=sug_layout,
    )

    # ── Mapeamento produto → slug ────────────────────────────────
    file_map = {}
    existing_fm = {} if aq_stale else ec.get('file_map', {})

    if ifc_entries and n_ifc > 50:
        # Muitos produtos: aceitar slugs automáticos sem prompt por item
        print(f'\n  {n_ifc} produto(s) detectados — aceitando slugs automáticos\n')
        for display, sug_slug_prod in ifc_entries:
            file_map[display] = existing_fm.get(display, '') or sug_slug_prod
    elif ifc_entries:
        print(f'\n  Mapeamento de {n_ifc} produto(s) para slug:')
        print('  (Enter para aceitar; o slug vira o nome do arquivo geo e da URL)\n')
        for display, sug_slug_prod in ifc_entries:
            existing_slug = existing_fm.get(display, '')
            if not existing_slug and hints.get('grupos'):
                matched_gp = match_slug_to_aq(sug_slug_prod, hints['grupos'])
                if matched_gp:
                    sug_slug_prod = slugify(matched_gp)[:40]
            default_slug = existing_slug or sug_slug_prod
            prod_slug = ask(display, default=default_slug)
            if prod_slug:
                file_map[display] = prod_slug

    # ── Monta e salva config ─────────────────────────────────────
    config = {
        'slug':              slug,
        'titulo':            titulo,
        'fabricante':        fabricante,
        'descricao':         descricao,
        'layout':            layout,
        'ifc_dir':           input_dir,
        'file_map':          file_map,
        'products_override': ec.get('products_override', []),
    }
    if aq_file:
        config['aq_file'] = aq_file
    elif ec.get('aq_file'):
        config['aq_file'] = ec['aq_file']

    config_path = os.path.join(ROOT, 'config.json')
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f'\n  config.json salvo → {config_path}')
    print('─' * 60 + '\n')
    return config


# ─── Pipeline principal ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='bilds-bim-3d build pipeline')
    parser.add_argument('--config',       default='config.json', help='Arquivo de configuração')
    parser.add_argument('--input-dir',    default='input',       help='Pasta com arquivos .IFC e .aq')
    parser.add_argument('--skip-ifc',     action='store_true',   help='Pula parse dos IFCs')
    parser.add_argument('--skip-preview', action='store_true',   help='Pula geração do preview HTML')
    parser.add_argument('--skip-zip',     action='store_true',   help='Pula geração do ZIP')
    # --interactive mantido por compatibilidade, mas agora é sempre o modo padrão
    parser.add_argument('--interactive', '-i', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()

    input_dir = os.path.join(ROOT, args.input_dir)

    # Carrega config.json existente como defaults (se houver)
    existing = None
    config_path = os.path.join(ROOT, args.config)
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding='utf-8') as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = None

    config = interactive_config(input_dir, existing)

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
