#!/usr/bin/env python3
"""
build.py — Pipeline: biblioteca .aq → preview HTML + ZIP para bilds.com

MODO PADRÃO (só o .aq)
  python3 scripts/build.py

  Forma, cor e dados saem todos do .aq. A geometria 3D está no BLOB
  SIMBOLOGIA_3D.SIMBOLOGIA_3D, no formato binário OQ3D (ver scripts/oq3d.py) —
  é o mesmo sólido que o AltoQi exporta como IFC. O vínculo peça → geometria
  vem da chave estrangeira PECA_SIMBOLOGIA_3D, então não existe file_map nem
  matching por nome de arquivo.

MODO LOTE (--all)
  python3 scripts/build.py --all

  Varre input/ e subpastas, gera um ZIP por .aq encontrado, sem perguntar nada
  (fabricante, título e layout são inferidos). A saída espelha a estrutura da
  entrada e bibliotecas que já têm ZIP são puladas — use --force para refazer.

    input/Amanco/linha/pecas.aq  →  output/Amanco/linha/<slug>-<ts>.zip
    input/Dancor/pecas.aq        →  output/Dancor/<slug>-<ts>.zip

MODO COMPATIBILIDADE (--ifc)
  python3 scripts/build.py --ifc

  Volta a ler os IFCs da pasta input/ para a geometria, usando o .aq apenas
  para os dados de produto. Útil quando a biblioteca traz IFCs de peças que não
  estão cadastradas no banco, ou para conferir uma contra a outra.
  Combinável com --all: aí o file_map de cada biblioteca é montado a partir dos
  IFCs que estiverem na pasta do próprio .aq.

config.json (gerado pelo fluxo interativo; editável à mão):
  {
    "slug":        "bombas-de-combate-a-incendio",
    "titulo":      "Bombas de Combate a Incêndio",
    "fabricante":  "Dancor",
    "descricao":   "...",
    "layout":      "series-rows",        // "series-rows" | "catalog-grid"
    "aq_file":     "input/Dancor/pecas.aq",
    "ifc_dir":     "input/",             // usado só com --ifc
    "file_map":    { "CAM-W10.IFC": "cam-w10", ... },   // idem
    "products_override": []              // peças no IFC e ausentes no .aq
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
import re
import shutil
import subprocess
import sys
import unicodedata
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
THUMBS_DIR = os.path.join(OUTPUT_DIR, 'thumbs')

# Miniaturas: 2× o card de 224×162 do bilds.com, para ficar nítido em DPR 2.
THUMB_W, THUMB_H = 448, 324
THUMB_MIME, THUMB_EXT, THUMB_QUALITY = 'image/webp', 'webp', 0.85


# ─── Matching IFC → AQ ───────────────────────────────────────────────────────

def slugify(s):
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
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


# ─── Catálogo a partir do .aq (caminho padrão) ───────────────────────────────

def _potencia_de(nome_gp, peca):
    """Potência em CV a partir do nome do grupo ou dos dados da peça."""
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*CV', nome_gp or '', re.IGNORECASE)
    if m:
        return float(m.group(1).replace(',', '.'))
    return peca.get('potencia_cv')


def build_catalog_from_aq(config, aq_path, geo_dir):
    """
    Gera catalog.json e os JSONs de geometria direto do .aq — sem IFC.

    O vínculo peça → geometria vem de PECA_SIMBOLOGIA_3D (chave estrangeira),
    então não há file_map nem matching por nome. Peças sem simbologia 3D são
    puladas: na prática são tubos (cilindro paramétrico gerado pelo AltoQi) e
    kits de aparelho sanitário, que não têm forma fixa.

    Retorna (catalog, n_geometrias, n_sem_3d).
    """
    from read_aq import extract as extract_aq, extract_simbologias
    import oq3d

    aq_data = extract_aq(aq_path)
    simbologias, sim_por_peca = extract_simbologias(aq_path)

    grupos_by_id = {g['ID_GRUPO_PECA']: g for g in aq_data['grupos']}

    props_by_peca = {}
    for p in aq_data['propriedades']:
        props_by_peca.setdefault(p['ID_PECA'], {})[p['propriedade']] = p['VALOR']

    curvas_by_peca = {}
    for pt in aq_data['curvas']:
        curvas_by_peca.setdefault(pt['ID_PECA'], []).append([
            round(pt['vazao'], 3), round(pt['altura'], 3),
            round(pt['potencia_ponto'] or 0, 3), round(pt['rendimento'] or 0, 1),
        ])

    os.makedirs(geo_dir, exist_ok=True)

    # Uma geometria por simbologia; várias peças podem compartilhá-la.
    # O nome da simbologia costuma ser só a dimensão ("100MM"), que se repete
    # entre grupos — por isso o grupo entra no slug quando há colisão.
    geo_por_sim = {}
    usados = set()
    for sid in sorted(simbologias):
        blob = simbologias[sid]['blob']
        if not blob or not oq3d.is_oq3d(blob):
            continue
        try:
            data = oq3d.to_buffers(blob)
        except oq3d.OQ3DError as e:
            print(f'  AVISO: simbologia {sid} ilegível ({e})')
            continue
        if not data['pos']:
            continue

        sim = simbologias[sid]
        name = slugify(sim['nome'])[:60]
        if not name or name in usados:
            name = slugify(f"{sim['grupo']} {sim['nome']}")[:60]
        if not name:
            name = f'sim-{sid}'
        base = name
        n = 2
        while name in usados:
            name = f'{base}-{n}'
            n += 1
        usados.add(name)

        # Mesma deduplicação do caminho IFC: o OQ3D indexa dentro de cada malha,
        # mas as malhas de uma peça repetem vértices entre si (~79% de redução).
        data, _, _, _ = dedup(data)
        with open(os.path.join(geo_dir, name + '.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, separators=(',', ':'))
        geo_por_sim[sid] = name

    # O nome da peça só recebe o prefixo do grupo quando sozinho é ambíguo —
    # e a decisão é POR GRUPO, para todas as peças dele saírem no mesmo padrão.
    # "100mm" se repete entre Cap/Luva/Joelho e "3CV T 220/380V" entre as séries
    # CAM: ambos precisam do grupo. Já "Interruptor inteligente 1 tecla - EWS
    # 1001 BR" é único, e prefixar com a categoria ("Pontos de comando") só
    # poluiria o nome exibido.
    grupos_por_nome = {}
    for p in aq_data['pecas']:
        n = (p['NOME_PECA'] or '').strip().lower()
        grupos_por_nome.setdefault(n, set()).add(p['ID_GRUPO_PECA'])

    grupo_precisa_prefixo = set()
    for p in aq_data['pecas']:
        n = (p['NOME_PECA'] or '').strip()
        if len(n) < 4 or len(grupos_por_nome.get(n.lower(), ())) > 1:
            grupo_precisa_prefixo.add(p['ID_GRUPO_PECA'])

    produtos = []
    series_set = set()
    sem_3d = 0
    ids_usados = set()

    for p in aq_data['pecas']:
        pid = p['ID_PECA']
        sid = sim_por_peca.get(pid)
        geo = geo_por_sim.get(sid) if sid else None
        if not geo:
            sem_3d += 1
            continue

        nome_gp = grupos_by_id.get(p['ID_GRUPO_PECA'], {}).get('NOME_GP', '')
        nome_peca = (p['NOME_PECA'] or '').strip()
        if (nome_gp and p['ID_GRUPO_PECA'] in grupo_precisa_prefixo
                and nome_gp.lower() not in nome_peca.lower()):
            nome_peca = f'{nome_gp} {nome_peca}'.strip()
        if not nome_peca:
            nome_peca = nome_gp or f'Peça {pid}'

        pid_slug = slugify(nome_peca) or f'peca-{pid}'
        base_slug = pid_slug
        n = 2
        while pid_slug in ids_usados:
            pid_slug = f'{base_slug}-{n}'
            n += 1
        ids_usados.add(pid_slug)

        serie = nome_gp or 'Outros'
        produtos.append({
            'id': pid_slug,
            'nome': nome_peca,
            'serie': serie,
            'geo': f'{geo}.json',
            'potencia': _potencia_de(nome_gp, p),
            'conexoes': p.get('DESCRICAO_DADOS') or '',
            'specs': props_by_peca.get(pid, {}),
            'curva': curvas_by_peca.get(pid),
        })
        series_set.add(serie)

    catalog = {
        'slug': config['slug'],
        'titulo': config['titulo'],
        'fabricante': config['fabricante'],
        'descricao': config.get('descricao', ''),
        'layout': config.get('layout', 'catalog-grid'),
        'filtros': sorted(s for s in series_set if s),
        'produtos': produtos,
    }
    return catalog, len(geo_por_sim), sem_3d


# ─── Parse dos IFCs ───────────────────────────────────────────────────────────

def run_ifc_parse(config, geo_dir=None):
    """Parseia todos os IFCs do file_map e salva JSONs deduplicados em geo_dir."""
    file_map = config.get('file_map', {})
    ifc_dir = config.get('ifc_dir', 'input/')
    geo_dir = geo_dir or GEO_DIR
    os.makedirs(geo_dir, exist_ok=True)

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

        out_path = os.path.join(geo_dir, f'{slug}.json')
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

def build_preview(catalog, layout, geo_dir=None, thumbs_dir=None):
    """
    Gera output/preview/{slug}/ com index.html, catalog.json, data/ e thumbs/.
    Arquivos compartilhados (vendor/) ficam em output/preview/vendor/.
    Cada catálogo fica em seu próprio subdiretório para não sobrescrever o índice.
    """
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

NODE_MINIMO = 20  # exigência do Playwright


def _node_versao(exe):
    """Major do Node em `exe`, ou None se não executar."""
    try:
        out = subprocess.run([exe, '--version'], capture_output=True,
                             text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.match(r'v(\d+)\.', out.stdout.strip())
    return int(m.group(1)) if m else None


def _find_node():
    """
    Node com major >= NODE_MINIMO, ou None.

    Existe porque é comum a máquina ter dois Node: o do apt em /usr/bin (velho)
    e um do nvm (novo). O nvm só entra no PATH de shell interativo — um
    subprocess do Python normalmente pega o do apt. Sem esta busca, quem roda o
    build fora de um shell com nvm carregado recebe "Playwright requires
    Node.js 20 or higher" sem pista de que existe um Node bom instalado.

    Ordem: $BILDS_NODE > `node` do PATH > maior versão em ~/.nvm.
    """
    forcado = os.environ.get('BILDS_NODE')
    if forcado:
        return forcado if (_node_versao(forcado) or 0) >= NODE_MINIMO else None

    if (_node_versao('node') or 0) >= NODE_MINIMO:
        return 'node'

    nvm = os.path.expanduser('~/.nvm/versions/node')
    candidatos = []
    if os.path.isdir(nvm):
        for v in os.listdir(nvm):
            exe = os.path.join(nvm, v, 'bin', 'node')
            major = _node_versao(exe) if os.path.exists(exe) else None
            if major and major >= NODE_MINIMO:
                candidatos.append((major, exe))
    return max(candidatos)[1] if candidatos else None


def build_thumbs(catalog, geo_dir, thumbs_dir):
    """
    Pré-renderiza uma miniatura por geometria e anota `thumb` nos produtos.

    Por que existe: sem isso o browser do visitante baixa o JSON de geometria de
    cada card visível (324 KB a 3,5 MB cada, servidos sem compressão) e roda um
    render WebGL só para desenhar o thumbnail. Medido em produção na página da
    Dancor: o elemento LCP É essa miniatura, com 7.230 ms de render delay, e as
    geometrias respondem por 57% do peso da página.

    O render roda no Chromium via scripts/thumbs.mjs, com o mesmo Three.js e a
    mesma câmera dos layouts — a imagem pré-gerada é a que a página produziria.

    Uma miniatura por GEOMETRIA, não por produto: 856 produtos da Amanco
    compartilham 448 geometrias.

    Degrada em silêncio: sem Node, sem playwright ou sem browser, o passo é
    pulado e os produtos ficam sem `thumb`. O bilds.com cai no render dinâmico
    de hoje, que continua funcionando.

    Retorna a quantidade de miniaturas geradas.
    """
    geos = []
    for produto in catalog['produtos']:
        g = produto.get('geo')
        if g and g not in geos and os.path.exists(os.path.join(geo_dir, g)):
            geos.append(g)
    if not geos:
        return 0

    os.makedirs(thumbs_dir, exist_ok=True)
    cfg = {
        'root': ROOT,
        'geoDir': os.path.abspath(geo_dir),
        'outDir': os.path.abspath(thumbs_dir),
        'geos': geos,
        'width': THUMB_W, 'height': THUMB_H,
        'mime': THUMB_MIME, 'quality': THUMB_QUALITY, 'ext': THUMB_EXT,
    }
    cfg_path = os.path.join(thumbs_dir, '.thumbs-config.json')
    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f)

    node = _find_node()
    if not node:
        atual = _node_versao('node')
        print(f'  AVISO: miniaturas puladas — Playwright exige Node >= {NODE_MINIMO}'
              + (f', e o do PATH é v{atual}' if atual else ', e não há node no PATH'))
        print('         Use `nvm use 20` (ou superior), ou aponte BILDS_NODE '
              'para um executável compatível.')
        os.remove(cfg_path)
        return 0

    driver = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'thumbs.mjs')
    try:
        proc = subprocess.run([node, driver, cfg_path],
                              capture_output=True, text=True, timeout=1800)
    except FileNotFoundError:
        print('  AVISO: node não encontrado — miniaturas puladas '
              '(a página cai no render dinâmico)')
        return 0
    except subprocess.TimeoutExpired:
        print('  AVISO: render de miniaturas excedeu 30 min — pulado')
        return 0
    finally:
        if os.path.exists(cfg_path):
            os.remove(cfg_path)

    if proc.returncode == 1:
        print(f'  AVISO: miniaturas puladas — {proc.stderr.strip()[:160]}')
        return 0

    ok, erros = {}, []
    for linha in proc.stdout.splitlines():
        try:
            r = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if 'error' in r:
            erros.append((r['geo'], r['error']))
        else:
            ok[r['geo']] = r['bytes']

    for produto in catalog['produtos']:
        stem = os.path.splitext(produto.get('geo', ''))[0]
        if stem in ok:
            produto['thumb'] = f'{stem}.{THUMB_EXT}'

    if erros:
        print(f'  AVISO: {len(erros)} miniatura(s) falharam '
              f'(esses produtos usam render dinâmico)')
        for g, e in erros[:3]:
            print(f'      {g}: {e[:70]}')

    if ok:
        media = sum(ok.values()) / len(ok) / 1024
        print(f'    {len(ok)} miniaturas ({media:.0f} KB em média)')
    return len(ok)


# ─── Empacotamento ZIP ────────────────────────────────────────────────────────

def build_zip(catalog, out_dir=None, geo_dir=None, thumbs_dir=None):
    """
    Gera <out_dir>/<slug>-AAAAMMDDHHMM.zip com:
      manifest.json     — slug, title, manufacturer, description, layout, filters, productCount
      catalog.json      — dados completos dos produtos (campos em português)
      geo/<slug>.json   — geometria de cada produto
      thumbs/<slug>.webp — miniatura pré-renderizada, quando houver (ver build_thumbs)

    out_dir espelha a pasta do .aq dentro de input/ (ver aq_rel_dir).
    """
    out_dir = out_dir or OUTPUT_DIR
    geo_dir = geo_dir or GEO_DIR
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d%H%M')
    zip_name = f"{catalog['slug']}-{ts}.zip"
    zip_path = os.path.join(out_dir, zip_name)
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
        # simplesmente cai no render dinâmico do viewer
        if thumbs_dir and os.path.isdir(thumbs_dir):
            enviadas = set()
            for produto in catalog['produtos']:
                nome = produto.get('thumb')
                if not nome or nome in enviadas:
                    continue
                src = os.path.join(thumbs_dir, nome)
                if os.path.exists(src):
                    zf.write(src, f'thumbs/{nome}')
                    enviadas.add(nome)

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




_AQ_NOISE = {'pecas', 'peca', 'biblioteca', 'lib', 'catalogo', 'catalog',
             'bim', 'ifc', 'altoqi', 'arquivo', 'dados', 'base'}


# Palavras que ficam em minúscula no meio de um título
_MINUSCULAS = {'de', 'da', 'do', 'das', 'dos', 'e', 'em', 'com', 'para', 'a', 'o'}


def _tokens_from_aq_filename(aq_path):
    """
    Tokens significativos do nome do arquivo .aq, com o case original preservado.

    O case importa: 'CFTV' e 'PPCI' são siglas e devem continuar em caixa alta;
    'EquipamentoDeRede' é CamelCase e precisa ser separado em palavras.
    """
    stem = os.path.splitext(os.path.basename(aq_path))[0]
    stem = re.sub(r'\.\d+$', '', stem)                         # remove ".1" final
    brutos = re.split(r'[_\-\s]+', stem)

    tokens = []
    for t in brutos:
        if not t or t.lower() in _AQ_NOISE or re.match(r'^\d{2,4}$', t):
            continue                                           # ruído, ano ou versão
        # CamelCase → palavras, sem quebrar siglas ('EquipamentoDeRede', não 'CFTV')
        if not t.isupper():
            t = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', t)
        tokens.extend(p for p in t.split() if p)
    return tokens


def _format_titulo(tokens):
    """
    Junta tokens num título legível: siglas em caixa alta, preposições em
    minúscula, o resto capitalizado.

      ['CFTV']                            → 'CFTV'
      ['Equipamento','De','Rede','Rack']  → 'Equipamento de Rede Rack'
      ['PPCI','incendio']                 → 'PPCI Incendio'
    """
    saida = []
    for i, t in enumerate(tokens):
        if t.isupper() and len(t) > 1:
            saida.append(t)                                    # sigla: preserva
        elif i > 0 and t.lower() in _MINUSCULAS:
            saida.append(t.lower())
        else:
            saida.append(t[:1].upper() + t[1:] if t.islower() else t.capitalize())
    return ' '.join(saida)


_GENERIC_DIRS = {'input', 'biblioteca', 'bibliotecas', 'bim', 'ifc', 'aq',
                 'downloads', 'arquivos', 'temp', 'tmp', '.', ''}


def peek_aq(aq_path):
    """
    Lê o .aq para extrair fabricante, título e pistas de layout.

    Fabricante e título NUNCA podem sair em branco ou em forma de slug: são o
    cabeçalho da página publicada. A cascata abaixo sempre produz algo legível.

    Fabricante, em ordem de confiança:
      1. Prefixo de CLASSE_SIMBOLOGIA_3D.NOME_CLASSE ("AMANCO - PVC Esgoto SN")
      2. PECA.BIBLIOTECA (quase sempre vazia na prática)
      3. Pasta avô, quando descritiva
      4. Pasta pai, quando bate com o primeiro token do nome do arquivo
      5. Primeiro token do nome do arquivo

    Título, em ordem:
      1. Pasta pai, quando descritiva e diferente do fabricante
         (input/Amanco/PVC Esgoto SN, SR e Silentium/pecas.aq)
      2. Tokens do nome do arquivo, menos o fabricante — exceto quando o
         único token restante é um bloco todo-minúsculo > 10 chars (palavra
         composta sem separador, ex: 'barramentoblindado'); nesse caso pula.
      3. Prefixo comum das linhas do banco (CLASSE_SIMBOLOGIA_3D.NOME_CLASSE)
      4. Último recurso: o próprio fabricante
    """
    from read_aq import peek_metadata

    meta = peek_metadata(aq_path)
    hints = {
        'fabricante': meta['fabricante'],
        'titulo': '',
        'grupos': meta['grupos'],
        'has_curves': meta['has_curves'],
        'linhas': meta['linhas'],
        'n_pecas': meta['n_pecas'],
        'n_simbologias': meta['n_simbologias'],
        'schema': meta['schema'],
    }

    parent_dir = os.path.basename(os.path.dirname(os.path.abspath(aq_path)))
    grandpa_dir = os.path.basename(
        os.path.dirname(os.path.dirname(os.path.abspath(aq_path))))
    fn_tokens = _tokens_from_aq_filename(aq_path)

    def _is_generic(d):
        return d.lower() in _GENERIC_DIRS

    # ── Fabricante ────────────────────────────────────────────────────────
    if not hints['fabricante'] and not _is_generic(grandpa_dir):
        hints['fabricante'] = grandpa_dir
    if not hints['fabricante'] and fn_tokens:
        # A pasta pai é o fabricante quando repete o primeiro token do arquivo
        # (input/Intelbras/pecas_Intelbras_....aq)
        if not _is_generic(parent_dir) and slugify(parent_dir) == slugify(fn_tokens[0]):
            hints['fabricante'] = parent_dir
        else:
            hints['fabricante'] = _format_titulo([fn_tokens[0]])

    fab_slug = slugify(hints['fabricante']) if hints['fabricante'] else ''

    # ── Título ────────────────────────────────────────────────────────────
    if not _is_generic(parent_dir) and slugify(parent_dir) != fab_slug:
        hints['titulo'] = parent_dir

    if not hints['titulo'] and fn_tokens:
        fab_tokens = set(tokenize(hints['fabricante'])) if hints['fabricante'] else set()
        rest = [t for t in fn_tokens if t.lower() not in fab_tokens]
        # Token único todo-minúsculo longo é palavra composta sem separador no
        # filename (ex: 'barramentoblindado'). O CamelCase split não ajuda aqui;
        # deixa o título vazio para cair no passo seguinte (linhas do banco).
        if rest and not (len(rest) == 1 and rest[0].islower() and len(rest[0]) > 10):
            hints['titulo'] = _format_titulo(rest)

    if not hints['titulo'] and hints['linhas']:
        hints['titulo'] = _common_prefix(hints['linhas']) or hints['linhas'][0]

    if not hints['titulo']:
        hints['titulo'] = hints['fabricante'] or 'Catálogo BIM'

    return hints


def _common_prefix(nomes):
    """Prefixo comum, por palavra: ['PVC Esgoto SN','PVC Esgoto SR'] → 'PVC Esgoto'."""
    if not nomes:
        return ''
    partes = [n.split() for n in nomes]
    comum = []
    for i in range(min(len(p) for p in partes)):
        w = partes[0][i]
        if all(p[i].lower() == w.lower() for p in partes):
            comum.append(w)
        else:
            break
    return ' '.join(comum)


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
    elif subdir_counts and all(n == 1 for n in subdir_counts.values()):
        # subdir mode: cada subdir tem exatamente 1 IFC → subdir = nome do produto
        entries_out = [
            (f'{d}/{next(f for f in os.listdir(os.path.join(input_dir, d)) if f.lower().endswith(".ifc"))}',
             slugify(d))
            for d in subdir_counts
        ]
        return entries_out, 'flat', aq_paths
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


def infer_titulo(grupos):
    """Extrai o prefixo comum entre todos os nomes de grupo como título do catálogo.
    Dancor: ['Bombas de Combate a Incêndio CAM-W10', 'Bombas de Combate a Incêndio CAM-W14', ...]
             → 'Bombas de Combate a Incêndio'
    Catálogos heterogêneos: prefixo curto → retorna ''
    """
    if not grupos:
        return ''
    if len(grupos) == 1:
        parts = grupos[0].split()
        return ' '.join(parts[:-1]) if len(parts) > 1 else grupos[0]
    words_list = [g.split() for g in grupos]
    common = words_list[0]
    for words in words_list[1:]:
        common = [c for c, w in zip(common, words) if c.lower() == w.lower()]
    title = ' '.join(common).strip()
    return title if len(title) > 3 else ''


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


def interactive_config(input_dir, existing=None, com_ifc=False):
    """
    Configura o catálogo interativamente.
    com_ifc: quando False (padrão), a geometria vem do .aq e os IFCs são
             ignorados — não há file_map a montar.
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
    if not com_ifc:
        ifc_entries = []          # geometria vem do .aq; IFCs ignorados

    n_ifc = len(ifc_entries)
    n_aq  = len(aq_paths)

    if not aq_paths:
        print(f'  ERRO: nenhuma biblioteca .aq encontrada em {input_dir}')
        print('  Copie o arquivo .aq do fabricante para a pasta input/ e rode de novo.')
        sys.exit(1)

    if com_ifc:
        mode_labels = {'flat': 'arquivos individuais', 'subdir': 'subdirs de categoria',
                       'recursive': 'busca recursiva'}
        print(f'  Modo --ifc: {n_ifc} produto(s) como '
              f'{mode_labels.get(mode, mode)}, {n_aq} biblioteca(s) .aq')
        if not ifc_entries:
            print('  AVISO: nenhum IFC encontrado — usando output/geo/ existente')
    else:
        print(f'  {n_aq} biblioteca(s) .aq — geometria e dados vêm do próprio .aq')
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

    # No modo padrão o tamanho do catálogo vem do .aq, não da contagem de IFCs
    n_products = n_ifc if com_ifc else (hints.get('n_pecas') or 0)
    if not n_products:
        n_products = len(ec.get('file_map', {}))

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


def auto_config(aq_path, input_dir, com_ifc=False):
    """
    Config inferido sem perguntar nada — usado no modo --all.

    Com --ifc, o file_map é montado a partir da pasta do próprio .aq (e não do
    input inteiro), para não misturar IFCs de bibliotecas diferentes.
    """
    hints = peek_aq(aq_path)
    titulo = hints['titulo']
    fabricante = hints['fabricante']
    n = hints.get('n_pecas') or 0
    layout = ('series-rows' if hints.get('has_curves')
              else ('catalog-grid' if n > 6 else 'series-rows'))

    aq_dir = os.path.dirname(os.path.abspath(aq_path))
    file_map = {}
    if com_ifc:
        ifc_entries, _, _ = scan_input(aq_dir)
        file_map = {display: slug for display, slug in ifc_entries}

    return {
        'slug': slugify(titulo or fabricante or 'catalogo'),
        'titulo': titulo,
        'fabricante': fabricante,
        'descricao': '',
        'layout': layout,
        'aq_file': aq_path,
        'ifc_dir': aq_dir if com_ifc else input_dir,
        'file_map': file_map,
        'products_override': [],
    }, hints


def run_build(config, aq_path, geo_dir, zip_dir, args):
    """
    Executa o build de um catálogo: geometria → catalog.json → preview → ZIP.
    Retorna (catalog, zip_path) — zip_path é None se --skip-zip.
    """
    os.makedirs(geo_dir, exist_ok=True)

    if args.ifc:
        if not args.skip_ifc:
            print('  Parseando IFCs...')
            geo_files = run_ifc_parse(config, geo_dir)
            print(f'    {len(geo_files)} geometrias geradas')
        else:
            geo_files = [f[:-5] for f in os.listdir(geo_dir) if f.endswith('.json')] \
                        if os.path.isdir(geo_dir) else []
        print('  Lendo biblioteca .aq...')
        aq_data = extract_aq(aq_path)
        product_map = build_product_map(aq_data)
        print(f'    {len(product_map)} grupos, '
              f'{sum(len(g["pecas"]) for g in product_map.values())} peças')
        catalog = build_catalog(config, product_map, set(geo_files))
    else:
        print('  Extraindo geometria do .aq...')
        catalog, n_geo, sem_3d = build_catalog_from_aq(config, aq_path, geo_dir)
        print(f'    {n_geo} geometrias extraídas'
              + (f'; {sem_3d} peças sem 3D (tubos/kits) puladas' if sem_3d else ''))

    print(f'    {len(catalog["produtos"])} produtos, layout: {catalog["layout"]}')
    if not catalog['produtos']:
        print('    ERRO: nenhum produto no catálogo — nada a publicar.')
        return catalog, None

    # Miniaturas antes do catalog.json: build_thumbs anota `thumb` nos produtos,
    # e tanto o arquivo solto quanto o do ZIP precisam sair já com o campo.
    # thumbs/ espelha a árvore de geo/ para não colidir entre bibliotecas.
    thumbs_dir = os.path.join(THUMBS_DIR, os.path.relpath(geo_dir, GEO_DIR))
    if not args.skip_thumbs:
        print('  Renderizando miniaturas...')
        build_thumbs(catalog, geo_dir, thumbs_dir)

    # catalog.json solto acompanha o ZIP, na mesma pasta espelhada
    os.makedirs(zip_dir, exist_ok=True)
    with open(os.path.join(zip_dir, f'{catalog["slug"]}-catalog.json'),
              'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    if not args.skip_preview:
        if build_preview(catalog, catalog['layout'], geo_dir=geo_dir, thumbs_dir=thumbs_dir):
            update_catalog_registry(catalog)
            print(f'    Preview: output/preview/{catalog["slug"]}/index.html')

    zip_path = None
    if not args.skip_zip:
        zip_path = build_zip(catalog, out_dir=zip_dir, geo_dir=geo_dir,
                             thumbs_dir=thumbs_dir)
    return catalog, zip_path


def run_all(input_dir, args):
    """Processa todos os .aq do input, espelhando a estrutura de pastas na saída."""
    _, _, aq_paths = scan_input(input_dir)
    if not aq_paths:
        print(f'Nenhuma biblioteca .aq encontrada em {input_dir}')
        sys.exit(1)

    print(f'\n=== bilds-bim-3d — lote: {len(aq_paths)} biblioteca(s) .aq ===\n')

    feitos, pulados, falhas = [], [], []
    for i, aq_path in enumerate(aq_paths, 1):
        rel_dir = aq_rel_dir(aq_path, input_dir)
        nome = os.path.basename(aq_path)
        print(f'[{i}/{len(aq_paths)}] {os.path.join(rel_dir, nome) if rel_dir else nome}')

        try:
            config, hints = auto_config(aq_path, input_dir, com_ifc=args.ifc)
        except Exception as e:
            print(f'    ERRO ao ler metadados: {e}\n')
            falhas.append((aq_path, str(e)))
            continue

        slug = config['slug']
        zip_dir = os.path.join(OUTPUT_DIR, rel_dir) if rel_dir else OUTPUT_DIR

        ja = find_existing_zip(zip_dir, slug)
        if ja and not args.force:
            print(f'    já processado: {os.path.relpath(ja, ROOT)} — pulando '
                  f'(use --force para refazer)\n')
            pulados.append(aq_path)
            continue

        print(f'    {config["fabricante"]} · {config["titulo"]} '
              f'({hints.get("n_pecas", 0)} peças, {hints.get("n_simbologias", 0)} geometrias)')

        geo_dir = os.path.join(GEO_DIR, rel_dir, slug) if rel_dir \
            else os.path.join(GEO_DIR, slug)
        try:
            catalog, zip_path = run_build(config, aq_path, geo_dir, zip_dir, args)
        except Exception as e:
            print(f'    ERRO no build: {e}\n')
            falhas.append((aq_path, str(e)))
            continue

        if zip_path:
            print(f'    ZIP: {os.path.relpath(zip_path, ROOT)}')
            feitos.append(zip_path)
        print()

    print('=== Lote concluído ===')
    print(f'  gerados : {len(feitos)}')
    if pulados:
        print(f'  pulados : {len(pulados)} (já tinham ZIP)')
    if falhas:
        print(f'  falhas  : {len(falhas)}')
        for p, e in falhas:
            print(f'      {os.path.basename(p)}: {e[:70]}')
    for z in feitos:
        print(f'  → {os.path.relpath(z, ROOT)}')


def main():
    parser = argparse.ArgumentParser(
        description='bilds-bim-3d — gera catálogo BIM 3D a partir de bibliotecas .aq',
        epilog='Por padrão lê só o .aq. Use --ifc para também parsear os IFCs da pasta.')
    parser.add_argument('--config',       default='config.json', help='Arquivo de configuração')
    parser.add_argument('--input-dir',    default='input',       help='Pasta com o(s) .aq (e IFCs, se --ifc)')
    parser.add_argument('--all', '-a',    action='store_true',
                        help='Processa TODOS os .aq de input/ e subpastas, sem perguntar. '
                             'Cada ZIP sai em output/ espelhando a pasta de origem. '
                             'Bibliotecas que já têm ZIP são puladas.')
    parser.add_argument('--force',        action='store_true',
                        help='Com --all: refaz também as bibliotecas que já têm ZIP')
    parser.add_argument('--ifc',          action='store_true',
                        help='Também lê os IFCs da pasta (modo antigo). '
                             'Sem esta flag, a geometria vem toda do .aq.')
    parser.add_argument('--skip-preview', action='store_true',   help='Pula geração do preview HTML')
    parser.add_argument('--skip-thumbs',  action='store_true',
                        help='Pula o render das miniaturas (a página volta a gerá-las no browser)')
    parser.add_argument('--skip-zip',     action='store_true',   help='Pula geração do ZIP')
    parser.add_argument('--skip-ifc',     action='store_true',   help=argparse.SUPPRESS)
    # --interactive mantido por compatibilidade, mas agora é sempre o modo padrão
    parser.add_argument('--interactive', '-i', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()

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

    config = interactive_config(input_dir, existing, com_ifc=args.ifc)

    modo = 'aq + IFC' if args.ifc else 'somente .aq'
    print(f'\n=== bilds-bim-3d: {config["titulo"]} ({modo}) ===\n')

    aq_path = os.path.join(ROOT, config.get('aq_file', ''))
    if not os.path.exists(aq_path):
        print(f'ERRO: biblioteca .aq não encontrada: {aq_path}')
        sys.exit(1)

    rel_dir = aq_rel_dir(aq_path, input_dir)
    zip_dir = os.path.join(OUTPUT_DIR, rel_dir) if rel_dir else OUTPUT_DIR
    geo_dir = os.path.join(GEO_DIR, rel_dir, config['slug']) if rel_dir \
        else os.path.join(GEO_DIR, config['slug'])

    catalog, zip_path = run_build(config, aq_path, geo_dir, zip_dir, args)
    if catalog['produtos']:
        print(f'    Local: python3 -m http.server 8080 --directory output/preview')
        print(f'    URL:   http://localhost:8080/{catalog["slug"]}')
    if zip_path:
        print(f'\n    Upload na bilds.com: {os.path.relpath(zip_path, ROOT)}')
    print('\n=== Build concluído ===')


if __name__ == '__main__':
    main()
