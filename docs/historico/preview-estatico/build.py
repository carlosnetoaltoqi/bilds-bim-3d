#!/usr/bin/env python3
"""
build.py — Pipeline: biblioteca .aq → preview HTML + ZIP para bilds.com

MODO PADRÃO (só o .aq)
  python3 scripts/build.py

  Forma, cor e dados saem todos do .aq. A geometria 3D está no BLOB
  SIMBOLOGIA_3D.SIMBOLOGIA_3D, no formato binário OQ3D (ver scripts/oq3d.py) —
  é o mesmo sólido que o AltoQi exporta como IFC. O vínculo peça → geometria
  vem da chave estrangeira PECA_SIMBOLOGIA_3D, então não existe file_map nem
  matching por nome de arquivo. (O modo --ifc, que lia os IFCs da pasta e casava
  nomes, foi removido em 2026-09-05 — I6.) Desde a E2 (2026-09-05) a leitura do .aq,
  o catálogo e as miniaturas vêm de www/apps/ingestao/pipeline/ — este arquivo só
  faz o que é do preview e do ZIP.

MODO LOTE (--all)
  python3 scripts/build.py --all

  Varre input/ e subpastas, gera um ZIP por .aq encontrado, sem perguntar nada
  (fabricante, título e layout são inferidos). A saída espelha a estrutura da
  entrada e bibliotecas que já têm ZIP são puladas — use --force para refazer.

    input/Amanco/linha/pecas.aq  →  output/Amanco/linha/<slug>-<ts>.zip
    input/Dancor/pecas.aq        →  output/Dancor/<slug>-<ts>.zip

config.json (gerado pelo fluxo interativo; editável à mão):
  {
    "slug":        "bombas-de-combate-a-incendio",
    "titulo":      "Bombas de Combate a Incêndio",
    "fabricante":  "Dancor",
    "descricao":   "...",
    "layout":      "series-rows",        // "series-rows" | "catalog-grid"
    "aq_file":     "input/Dancor/pecas.aq"
  }

Saídas (<rel> = pasta do .aq relativa a input/):
  output/geo/<rel>/<slug>/*.json          — geometria por produto
  output/thumbs/<rel>/<slug>/*.webp       — miniatura por geometria (--skip-thumbs pula)
  output/<rel>/<slug>-catalog.json        — dados do catálogo
  output/<rel>/<slug>-AAAAMMDDHHMM.zip    — pacote para upload na bilds.com
  output/preview/<slug>/index.html        — preview estático (local ou Vercel)
  output/preview/<slug>/data/*.json       — geometria servida ao preview
  output/preview/catalogs.json            — índice dos catálogos gerados

Visualização local após o build:
  python3 -m http.server 8080 --directory output/preview
"""
import argparse
import datetime
import json
import os
import shutil
import sys
import zipfile

# O pipeline (leitura do .aq, catálogo, miniaturas) mora no serviço de ingestão —
# www/apps/ingestao/pipeline — desde 2026-09-05 (E2 de docs/arquitetura-www-servico-de-ingestao.md).
# Este build é um consumidor dele: só o que é do ZIP/preview fica aqui.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'biblioteca'))

from bim_pipeline.catalogo.catalogo import build_catalog_from_aq, resumo_diag, slugify, tokenize     # noqa: E402,F401
from bim_pipeline.catalogo.inferencia import auto_config, find_aq_paths, infer_titulo, peek_aq       # noqa: E402,F401
from bim_pipeline.miniaturas.render import (THUMB_EXT, THUMB_H, THUMB_MIME, THUMB_QUALITY, THUMB_W,  # noqa: E402,F401
                                            ThumbsError, _find_node, _node_versao, build_thumbs)

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
THUMBS_DIR = os.path.join(OUTPUT_DIR, 'thumbs')

# Miniaturas: 2× o card de 224×162 do bilds.com, para ficar nítido em DPR 2.


# ─── Nomes e slugs ───────────────────────────────────────────────────────────

# ─── Build do preview HTML ────────────────────────────────────────────────────

def build_preview(catalog, layout, geo_dir=None, thumbs_dir=None):
    """
    Gera output/preview/{slug}/ com index.html, catalog.json, data/ e thumbs/.
    Arquivos compartilhados (vendor/) ficam em output/preview/vendor/.
    Cada catálogo fica em seu próprio subdiretório para não sobrescrever o índice.
    """
    # Sem Jinja2 não há preview possível: os templates usam `{% for %}`, `{% if %}`
    # e filtros, e o antigo "fallback" que só trocava `{{ catalog | tojson }}` por
    # texto entregava um index.html com tags Jinja cruas e nenhum card (I7).
    # Falha alto, como o build_thumbs sem Node — run_build ignorava um `return
    # False` daqui e seguia gerando o ZIP como se o preview existisse.
    if not HAS_JINJA2:
        raise RuntimeError(
            'Jinja2 não está instalado e o preview não pode ser renderizado sem ele. '
            'Instale com `pip install jinja2` (está em requirements.txt) ou rode com '
            '--skip-preview.')

    layouts_dir = os.path.join(TEMPLATES_DIR, 'layouts')
    template_path = os.path.join(layouts_dir, f'{layout}.html')
    if not os.path.exists(template_path):
        raise RuntimeError(
            f'template {layout}.html não encontrado em templates/layouts/ '
            f'(disponíveis: {", ".join(sorted(os.listdir(layouts_dir)))})')

    geo_dir = geo_dir or GEO_DIR
    catalog_slug = catalog['slug']
    catalog_dir = os.path.join(PREVIEW_DIR, catalog_slug)
    os.makedirs(catalog_dir, exist_ok=True)

    # data/ fica dentro do catálogo: é assim que o template resolve ('./data/'),
    # e evita colisão entre bibliotecas — nomes como '50mm.json' se repetem.
    data_dir = os.path.join(catalog_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)

    copiados = set()
    for produto in catalog['produtos']:
        geo_slug = produto['geo'].replace('.json', '')
        if geo_slug in copiados:
            continue
        src = os.path.join(geo_dir, f'{geo_slug}.json')
        if os.path.exists(src):
            shutil.copy(src, os.path.join(data_dir, f'{geo_slug}.json'))
            copiados.add(geo_slug)

    # thumbs/ — copia os WebPs pré-renderizados para o preview usar os mesmos
    # arquivos que o bilds.com consome (não o render dinâmico via Three.js).
    if thumbs_dir and os.path.isdir(thumbs_dir):
        thumbs_dst = os.path.join(catalog_dir, 'thumbs')
        os.makedirs(thumbs_dst, exist_ok=True)
        copiados_th = set()
        for produto in catalog['produtos']:
            nome = produto.get('thumb')
            if not nome or nome in copiados_th:
                continue
            src = os.path.join(thumbs_dir, nome)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(thumbs_dst, nome))
                copiados_th.add(nome)

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
    env = Environment(
        loader=FileSystemLoader(layouts_dir),
        undefined=StrictUndefined,
        # Nomes de série/título vêm do .aq e podem ter aspas (Komeco: `1" x 1"`).
        # Sem escape, `data-filter="{{ f }}"` era truncado e o onclick quebrava.
        # `| tojson` continua seguro: sob autoescape ele escapa <, > e & em \uXXXX.
        autoescape=True,
    )
    tmpl = env.get_template(f'{layout}.html')
    html = tmpl.render(catalog=catalog, items=catalog['produtos'])

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

    # Descarta a entrada atual e as órfãs (slug sem diretório no preview) —
    # sem isso o índice acumula links quebrados a cada troca de slug.
    def _vivo(e):
        s = e.get('slug')
        return bool(s) and os.path.isdir(os.path.join(PREVIEW_DIR, s))

    orfas = [e for e in registry if e.get('slug') != catalog['slug'] and not _vivo(e)]
    if orfas:
        print(f'    Índice: removendo {len(orfas)} entrada(s) órfã(s): '
              f'{", ".join(e.get("slug", "?") for e in orfas)}')
    registry = [e for e in registry if e.get('slug') != catalog['slug'] and _vivo(e)]
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


# ─── Miniaturas pré-renderizadas ──────────────────────────────────────────────

# ─── Empacotamento ZIP ────────────────────────────────────────────────────────

def build_zip(catalog, out_dir=None, geo_dir=None, thumbs_dir=None):
    """
    Gera <out_dir>/<slug>-AAAAMMDDHHMM.zip com:
      manifest.json     — slug, title, manufacturer, description, layout, filters,
                          productCount, thumbCount
      catalog.json      — dados completos dos produtos (campos em português)
      geo/<slug>.json   — geometria de cada produto
      thumbs/<slug>.webp — miniatura pré-renderizada, quando houver (ver build_thumbs)

    `thumbCount` é quantos arquivos entraram em thumbs/. Zero num catálogo com
    produtos é o sinal de que o build correu com --skip-thumbs ou
    --allow-no-thumbs — e de que a página vai renderizar no browser.

    out_dir espelha a pasta do .aq dentro de input/ (ver aq_rel_dir).
    """
    out_dir = out_dir or OUTPUT_DIR
    geo_dir = geo_dir or GEO_DIR
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d%H%M')
    zip_name = f"{catalog['slug']}-{ts}.zip"
    zip_path = os.path.join(out_dir, zip_name)
    # thumbs que existem em disco — decididas antes do manifest para thumbCount
    thumbs = []
    if thumbs_dir and os.path.isdir(thumbs_dir):
        for produto in catalog['produtos']:
            nome = produto.get('thumb')
            if nome and nome not in thumbs and os.path.exists(os.path.join(thumbs_dir, nome)):
                thumbs.append(nome)

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
            'thumbCount':   len(thumbs),
        }
        zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))

        # catalog.json
        zf.writestr('catalog.json', json.dumps(catalog, ensure_ascii=False, separators=(',', ':')))

        # geo files — peças diferentes podem compartilhar a mesma geometria,
        # então cada arquivo entra no ZIP uma única vez
        incluidos = set()
        faltando = 0
        for produto in catalog['produtos']:
            slug = produto['geo'].replace('.json', '')
            if slug in incluidos:
                continue
            geo_path = os.path.join(geo_dir, f'{slug}.json')
            if os.path.exists(geo_path):
                zf.write(geo_path, f'geo/{slug}.json')
                incluidos.add(slug)
            else:
                faltando += 1
                if faltando <= 5:
                    print(f'  AVISO: geo/{slug}.json não encontrado — fora do ZIP')
        if faltando > 5:
            print(f'  AVISO: +{faltando - 5} geometrias ausentes')

        # thumbs — só as que build_thumbs conseguiu gerar; produto sem `thumb`
        # cai no render dinâmico do viewer (e thumbCount denuncia isso)
        for nome in thumbs:
            zf.write(os.path.join(thumbs_dir, nome), f'thumbs/{nome}')

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




def interactive_config(input_dir, existing=None):
    """
    Configura o catálogo interativamente. A geometria e os dados vêm do .aq.
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
    aq_paths = find_aq_paths(input_dir)
    n_aq = len(aq_paths)

    if not aq_paths:
        print(f'  ERRO: nenhuma biblioteca .aq encontrada em {input_dir}')
        print('  Copie o arquivo .aq do fabricante para a pasta input/ e rode de novo.')
        sys.exit(1)

    print(f'  {n_aq} biblioteca(s) .aq — geometria e dados vêm do próprio .aq')
    print()

    # ── Arquivo .aq ──────────────────────────────────────────────
    aq_file = None
    hints   = {}
    if len(aq_paths) == 1:
        aq_file = aq_paths[0]
        print(f'  Lendo biblioteca: {os.path.basename(aq_file)}...')
        hints = peek_aq(aq_file)
        n_gp = len(hints['grupos'])
        curvas_txt = ', com curvas Q-H' if hints['has_curves'] else ', sem curvas Q-H'
        print(f'  → {n_gp} grupo(s) de produtos{curvas_txt}')
        if hints['fabricante']:
            print(f'  → fabricante: {hints["fabricante"]}')
        if hints['titulo']:
            print(f'  → título inferido: {hints["titulo"]}')
        if hints['grupos']:
            print(f'  → grupos: {", ".join(hints["grupos"][:5])}{"..." if n_gp > 5 else ""}')
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

    n_products = hints.get('n_pecas') or 0

    _auto_layout = (
        'series-rows' if hints.get('has_curves') else
        ('catalog-grid' if n_products > 6 else 'series-rows')
    )
    if aq_stale:
        sug_fabricante = hints.get('fabricante') or ''
        sug_layout     = _auto_layout
    else:
        sug_fabricante = ec.get('fabricante') or hints.get('fabricante') or ''
        sug_layout     = ec.get('layout') or _auto_layout

    # ── Perguntas de metadados ───────────────────────────────────
    # Fabricante e título jamais saem vazios: são o cabeçalho da página.
    fabricante = ask('Fabricante', default=sug_fabricante) or sug_fabricante

    _titulo_inf = hints.get('titulo') or infer_titulo(hints.get('grupos', []))
    sug_titulo = _titulo_inf if aq_stale else (ec.get('titulo') or _titulo_inf)
    titulo = ask('Título do catálogo', default=sug_titulo) or sug_titulo

    if not fabricante:
        print('  AVISO: fabricante não identificado — a página ficará sem esse campo.')
    if not titulo:
        titulo = fabricante or 'Catálogo BIM'

    slug = slugify(titulo or fabricante or 'catalogo')
    print(f'  Slug da URL: {slug}')

    descricao = ask('Descrição curta (opcional)', default=ec.get('descricao') or '')

    layout = ask_choice(
        'Layout de exibição:',
        [
            ('series-rows',  'linhas por série — estilo Netflix, ideal para poucas famílias com curva Q-H'),
            ('catalog-grid', 'grade densa com filtros — ideal para muitos itens heterogêneos'),
        ],
        default=sug_layout,
    )

    # ── Monta e salva config ─────────────────────────────────────
    config = {
        'slug':              slug,
        'titulo':            titulo,
        'fabricante':        fabricante,
        'descricao':         descricao,
        'layout':            layout,
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

def aq_rel_dir(aq_path, input_dir):
    """
    Pasta do .aq relativa ao input, para espelhar a estrutura na saída.

      input/Amanco/linha/pecas.aq  →  'Amanco/linha'
      input/pecas.aq               →  ''
    """
    rel = os.path.relpath(os.path.dirname(os.path.abspath(aq_path)),
                          os.path.abspath(input_dir))
    return '' if rel in ('.', os.curdir) else rel


def find_existing_zip(out_dir, slug):
    """ZIP mais recente já gerado para este slug, se houver."""
    if not os.path.isdir(out_dir):
        return None
    hits = sorted(f for f in os.listdir(out_dir)
                  if f.startswith(slug + '-') and f.endswith('.zip'))
    return os.path.join(out_dir, hits[-1]) if hits else None


def run_build(config, aq_path, geo_dir, zip_dir, args):
    """
    Executa o build de um catálogo: geometria → catalog.json → preview → ZIP.
    Retorna (catalog, zip_path) — zip_path é None se --skip-zip.
    """
    os.makedirs(geo_dir, exist_ok=True)

    print('  Extraindo geometria do .aq...')
    catalog, n_geo, diag = build_catalog_from_aq(config, aq_path, geo_dir)
    print(f'    {n_geo} geometrias extraídas')
    resumo_diag(diag)

    print(f'    {len(catalog["produtos"])} produtos, layout: {catalog["layout"]}')
    if not catalog['produtos']:
        print('    ERRO: nenhum produto no catálogo — nada a publicar.')
        return catalog, None

    # Miniaturas antes do catalog.json: build_thumbs anota `thumb` nos produtos,
    # e tanto o arquivo solto quanto o do ZIP precisam sair já com o campo.
    # thumbs/ espelha a árvore de geo/ para não colidir entre bibliotecas.
    thumbs_dir = os.path.join(THUMBS_DIR, os.path.relpath(geo_dir, GEO_DIR))
    if args.skip_thumbs:
        print('  Miniaturas puladas (--skip-thumbs): a página renderiza no browser')
    else:
        print('  Renderizando miniaturas...')
        try:
            build_thumbs(catalog, geo_dir, thumbs_dir, vendor_dir=os.path.join(TEMPLATES_DIR, 'vendor'),
                         progresso=lambda m: print(f'    {m}'))
        except ThumbsError as e:
            if not args.allow_no_thumbs:
                print(f'  ERRO: miniaturas — {e}')
                print('        Sem miniaturas o ZIP sai sem thumbs/ e a página paga o '
                      'render no browser (39,9 s de LCP medidos). Para aceitar isso '
                      'de propósito: --allow-no-thumbs; para nem tentar: --skip-thumbs.')
                raise
            print(f'  AVISO: miniaturas — {e}')
            print('         Aceito por --allow-no-thumbs: produtos sem `thumb` usam '
                  'render dinâmico; thumbCount no manifest mostra quantas saíram.')

    # catalog.json solto acompanha o ZIP, na mesma pasta espelhada
    os.makedirs(zip_dir, exist_ok=True)
    with open(os.path.join(zip_dir, f'{catalog["slug"]}-catalog.json'),
              'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    if not args.skip_preview:
        # build_preview lança em vez de devolver False (I7): sem Jinja2 ou sem o
        # template, o build inteiro para aqui — não sai ZIP sem preview.
        build_preview(catalog, catalog['layout'], geo_dir=geo_dir, thumbs_dir=thumbs_dir)
        update_catalog_registry(catalog)
        print(f'    Preview: output/preview/{catalog["slug"]}/index.html')

    zip_path = None
    if not args.skip_zip:
        zip_path = build_zip(catalog, out_dir=zip_dir, geo_dir=geo_dir,
                             thumbs_dir=thumbs_dir)
    return catalog, zip_path


def run_all(input_dir, args):
    """Processa todos os .aq do input, espelhando a estrutura de pastas na saída."""
    aq_paths = find_aq_paths(input_dir)
    if not aq_paths:
        print(f'Nenhuma biblioteca .aq encontrada em {input_dir}')
        sys.exit(1)

    print(f'\n=== bilds-bim-3d — lote: {len(aq_paths)} biblioteca(s) .aq ===\n')

    feitos, pulados, falhas = [], [], []
    concluidos = 0
    for i, aq_path in enumerate(aq_paths, 1):
        rel_dir = aq_rel_dir(aq_path, input_dir)
        nome = os.path.basename(aq_path)
        print(f'[{i}/{len(aq_paths)}] {os.path.join(rel_dir, nome) if rel_dir else nome}')

        try:
            config, hints = auto_config(aq_path)
        except Exception as e:
            print(f'    ERRO ao ler metadados: {e}\n')
            falhas.append((aq_path, str(e)))
            continue

        base_slug = config['slug']
        zip_dir = os.path.join(OUTPUT_DIR, rel_dir) if rel_dir else OUTPUT_DIR

        # --layout: força layout e sufixo o slug; reutiliza geometria do slug base
        if args.layout:
            suffix = 'grid' if args.layout == 'catalog-grid' else 'series'
            config['slug'] = base_slug + '-' + suffix
            config['layout'] = args.layout
        slug = config['slug']

        ja = find_existing_zip(zip_dir, slug)
        if ja and not args.force:
            print(f'    já processado: {os.path.relpath(ja, ROOT)} — pulando '
                  f'(use --force para refazer)\n')
            pulados.append(aq_path)
            continue

        print(f'    {config["fabricante"]} · {config["titulo"]} '
              f'({hints.get("n_pecas", 0)} peças, {hints.get("n_simbologias", 0)} geometrias)')

        # geo_dir sempre usa o slug base — a geometria é igual para os dois layouts
        geo_dir = os.path.join(GEO_DIR, rel_dir, base_slug) if rel_dir \
            else os.path.join(GEO_DIR, base_slug)
        try:
            catalog, zip_path = run_build(config, aq_path, geo_dir, zip_dir, args)
        except Exception as e:
            print(f'    ERRO no build: {e}\n')
            falhas.append((aq_path, str(e)))
            continue

        if not catalog['produtos']:
            falhas.append((aq_path, 'nenhum produto no catálogo'))
            print()
            continue

        concluidos += 1
        if zip_path:
            print(f'    ZIP: {os.path.relpath(zip_path, ROOT)}')
            feitos.append(zip_path)
        print()

    print('=== Lote concluído ===')
    print(f'  gerados : {concluidos}' + (' (sem ZIP)' if args.skip_zip else ''))
    if pulados:
        print(f'  pulados : {len(pulados)} (já tinham ZIP)')
    if falhas:
        print(f'  falhas  : {len(falhas)}')
        for p, e in falhas:
            print(f'      {os.path.basename(p)}: {e[:70]}')
    for z in feitos:
        print(f'  → {os.path.relpath(z, ROOT)}')
    if falhas:
        sys.exit(1)


def build_parser():
    parser = argparse.ArgumentParser(
        description='bilds-bim-3d — gera catálogo BIM 3D a partir de bibliotecas .aq',
        epilog='Geometria e dados vêm todos do .aq (o modo --ifc foi removido em 2026-09-05, I6).')
    parser.add_argument('--config',       default='config.json', help='Arquivo de configuração')
    parser.add_argument('--input-dir',    default='input',       help='Pasta com o(s) .aq')
    parser.add_argument('--all', '-a',    action='store_true',
                        help='Processa TODOS os .aq de input/ e subpastas, sem perguntar. '
                             'Cada ZIP sai em output/ espelhando a pasta de origem. '
                             'Bibliotecas que já têm ZIP são puladas.')
    parser.add_argument('--force',        action='store_true',
                        help='Com --all: refaz também as bibliotecas que já têm ZIP')
    parser.add_argument('--skip-preview', action='store_true',   help='Pula geração do preview HTML')
    parser.add_argument('--skip-thumbs',  action='store_true',
                        help='Nem tenta renderizar miniaturas (a página volta a gerá-las no browser)')
    parser.add_argument('--allow-no-thumbs', action='store_true',
                        help='Tenta renderizar; se falhar (sem Node/Playwright/Chromium, ou '
                             'geometria que não renderiza), avisa e segue em vez de falhar')
    parser.add_argument('--skip-zip',     action='store_true',   help='Pula geração do ZIP')
    parser.add_argument('--layout',       choices=['series-rows', 'catalog-grid'], default=None,
                        help='Força layout (com --all: sufixo -grid ou -series no slug; '
                             'reutiliza geometria já extraída)')
    # --interactive mantido por compatibilidade, mas agora é sempre o modo padrão
    parser.add_argument('--interactive', '-i', action='store_true', help=argparse.SUPPRESS)
    return parser


def main():
    args = build_parser().parse_args()

    input_dir = os.path.join(ROOT, args.input_dir)

    # ── Lote: todas as bibliotecas do input ───────────────────────────────
    if args.all:
        run_all(input_dir, args)
        return

    # ── Uma biblioteca, com perguntas ─────────────────────────────────────
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

    aq_path = os.path.join(ROOT, config.get('aq_file', ''))
    if not os.path.exists(aq_path):
        print(f'ERRO: biblioteca .aq não encontrada: {aq_path}')
        sys.exit(1)

    rel_dir = aq_rel_dir(aq_path, input_dir)
    zip_dir = os.path.join(OUTPUT_DIR, rel_dir) if rel_dir else OUTPUT_DIR
    geo_dir = os.path.join(GEO_DIR, rel_dir, config['slug']) if rel_dir \
        else os.path.join(GEO_DIR, config['slug'])

    try:
        catalog, zip_path = run_build(config, aq_path, geo_dir, zip_dir, args)
    except ThumbsError:
        print('\n=== Build FALHOU: miniaturas (veja o ERRO acima) ===')
        sys.exit(1)
    if not catalog['produtos']:
        print('\n=== Build FALHOU: nenhum produto ===')
        sys.exit(1)
    print(f'    Local: python3 -m http.server 8080 --directory output/preview')
    print(f'    URL:   http://localhost:8080/{catalog["slug"]}')
    if zip_path:
        print(f'\n    Upload na bilds.com: {os.path.relpath(zip_path, ROOT)}')
    print('\n=== Build concluído ===')


if __name__ == '__main__':
    main()
