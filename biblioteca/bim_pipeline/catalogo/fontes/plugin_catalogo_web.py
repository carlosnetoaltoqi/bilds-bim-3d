#!/usr/bin/env python3
"""
catallog.py — de um plugin de AutoCAD da plataforma Catallog (Collabo) a um catálogo do
bilds-bim-3d: descobre o catálogo web que o plugin abre, baixa os arquivos 3D de uma categoria
(IGES) e os metadados dos produtos, tessela e devolve o catálogo no MESMO JSON que o
`catalogo_de_aq.py` devolve — para o serviço de ingestão publicar como publica uma biblioteca.

COMO O PLUGIN FUNCIONA (estudo em `eng-reversa/tupy/estudo/01-plugin-tupycad-e-catalogo-web.md`,
S7.17, com o TupyCAD 2.0.0): a DLL .NET (35 KB) é uma casca — abre uma paleta com a página web
do catálogo (`PLUGIN_HOST`, ex. https://tupycad.catallog.digital) e expõe três callbacks
JavaScript (`InsertBlockFromURL`, `RequestDownload`, `GetPluginVersion`). A geometria NÃO está
na DLL; está no catálogo web, um arquivo por produto, e a API é pública:

  GET  /api/marketplace/v1/settings/                              título, formulário de download
  GET  /api/marketplace/v2/categories/?product_type=group          categorias
  GET  /api/marketplace/v2/products/?category_slugs=<cat>&product_type=group   grupos (famílias)
  GET  /api/marketplace/v2/products/<slug>/?product_type=group     detalhe do grupo: `resources`
                                                                  (o .rfa da família) e `components`
  GET  /api/marketplace/v1/products/<slug>/resources/              arquivos de um produto (.igs, .dxf)
  GET  /api/marketplace/v2/products/<slug>/?product_type=product&fields=…   nome, código, atributos,
                                                                  HTML `details` (tabela dimensional)
  POST /api/crm/v1/form/  {form_id, resource_uuid, origin, fields, page_name, page_url,
                           component_uuid}                        o formulário de download → {url}
  GET  <url>                                                       o arquivo

O FORMULÁRIO é captura de lead (nome, e-mail, telefone, empresa, cargo). Este módulo o envia
com os dados da pessoa que está importando — `lead` — uma vez por arquivo, como o navegador
faz. Não invente dados: os Termos de Uso do site proíbem redistribuição, e a importação é para
estudo/uso próprio de quem preenche. Sem `binary_file_id` no corpo: `null` faz o servidor
procurar um BinaryFile e responder 400.

O QUE VIRA PEÇA: cada IGES baixado. Por grupo, `igs_por_grupo` produtos têm o IGES baixado
(1 = o primeiro que tem; -1 = todos; 0 = nenhum). O `.rfa` do grupo (Revit) é baixado e lido
pelo `rfa_partatom.py` — a geometria dele é proprietária, mas o `PartAtom` traz a lista de
tipos (DN32…DN200), que vira a spec "Tipos Revit". DXF (vistas 2D) só com `dxf=True`.

GEOMETRIA: `step_to_geo.converter` (IGES: costura das faces soltas + orientação pelo volume).
Um JSON por peça em `geo_dir`, nome = código comercial (`<codigo>.json`).

SAÍDA (`--saida`): o JSON do `catalogo_de_aq.py` — `{config, catalog, n_geometrias, diag, hints}` —
com `hints.origem` (host, categoria, arquivos, bytes). Os arquivos baixados ficam em `--downloads`
com um `manifesto.json` (grupo, produto, tipo, tamanho, SHA-256, URL) — o import é idempotente
sobre ele. Progresso no stderr; erros acusam e saem com 1.

Uso:
    python3 catallog.py inspecionar TupyCAD.dll                # host, título, categorias → stdout JSON
    python3 catallog.py importar --host https://… --categoria tupygrooved-173 --lead lead.json \
        --downloads DIR --geo-dir DIR --saida catalogo.json [--igs-por-grupo 1] [--dxf] [--deflexao 0.2] \
        [--limite N] [--sair-com-stdin]
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))

UA = 'Mozilla/5.0 (bilds-bim-3d; www/apps/ingestao/pipeline/catallog.py)'
CAMPOS_LEAD = ('full_name', 'email', 'mobile', 'company', 'position')
PAUSA_S = 1.0
RE_URL = re.compile(r'https?://[A-Za-z0-9.-]+(?::\d+)?(?:/[^\s"\'<>]*)?')


class CatallogError(SystemExit):
    def __init__(self, msg):
        super().__init__(f'catallog: {msg}')


def avisar(msg):
    print(msg, file=sys.stderr, flush=True)


# ─── A DLL do plugin ──────────────────────────────────────────────────────────

def strings_utf16(data, minimo=4):
    """Literais .NET (#US heap) e VERSIONINFO são UTF-16LE: sequências de (byte, 0x00)."""
    out = []
    for m in re.finditer(rb'(?:[\x20-\x7e\xa0-\xff]\x00){%d,}' % minimo, data):
        out.append(m.group(0).decode('utf-16-le', 'ignore'))
    return out


def inspecionar_dll(caminho):
    """Host do catálogo, nome e versão do plugin a partir das strings da DLL."""
    with open(caminho, 'rb') as f:
        data = f.read()
    if data[:2] != b'MZ':
        raise CatallogError(f'{os.path.basename(caminho)} não é um executável Windows (PE) — envie a DLL do plugin')
    lits = strings_utf16(data)
    urls = [u for s in lits for u in RE_URL.findall(s)]
    hosts = []
    for u in urls:
        p = urllib.parse.urlsplit(u)
        h = f'{p.scheme}://{p.netloc}'
        if h not in hosts:
            hosts.append(h)
    if not hosts:
        raise CatallogError(f'{os.path.basename(caminho)}: nenhuma URL nas strings — não é um plugin Catallog/Collabo?')
    preferidos = [h for h in hosts if re.search(r'catallog|collabo', h, re.I)]
    host = (preferidos or hosts)[0]

    def depois_de(marca):
        for i, s in enumerate(lits):
            if s == marca and i + 1 < len(lits):
                return lits[i + 1].strip()
        return None
    versao = next((s for s in lits if re.fullmatch(r'\d+\.\d+\.\d+(\.\d+)?', s)), None)
    return {
        'arquivo': os.path.basename(caminho),
        'bytes': len(data),
        'host': host,
        'hosts': hosts,
        'plugin': depois_de('FileDescription') or depois_de('ProductName'),
        'empresa': depois_de('CompanyName'),
        'versao': versao,
        'dotnet': b'.NET' in data or b'mscorlib' in data,
    }


# ─── A API do catálogo ────────────────────────────────────────────────────────

class Catallog:
    def __init__(self, host, pausa=PAUSA_S, ua=UA):
        self.host = host.rstrip('/')
        self.pausa = pausa
        self.ua = ua

    def _req(self, url, data=None, tent=3):
        hdr = {'User-Agent': self.ua, 'Accept': 'application/json'}
        body = None
        if data is not None:
            body = json.dumps(data).encode('utf-8')
            hdr['Content-Type'] = 'application/json'
        for i in range(tent):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=hdr), timeout=120) as r:
                    return r.status, r.read(), dict(r.headers)
            except urllib.error.HTTPError as e:
                if e.code < 500 or i == tent - 1:
                    raise CatallogError(f'HTTP {e.code} em {url}: {e.read()[:300]!r}')
            except (urllib.error.URLError, TimeoutError) as e:
                if i == tent - 1:
                    raise CatallogError(f'falha de rede em {url}: {e}')
            time.sleep(2 * (i + 1))

    def get_json(self, path, **q):
        url = self.host + path + (('?' + urllib.parse.urlencode(q)) if q else '')
        _, raw, _ = self._req(url)
        try:
            return json.loads(raw)
        except ValueError:
            raise CatallogError(f'{url} não devolveu JSON (é um catálogo Catallog?)')

    def settings(self):
        return self.get_json('/api/marketplace/v1/settings/', _lang='pt')

    def titulo(self, settings=None):
        s = settings or self.settings()
        meta = (s.get('meta') or {})
        return (meta.get('pt') or meta.get('en') or next(iter(meta.values()), {})).get('title') or self.host

    def categorias(self):
        d = self.get_json('/api/marketplace/v2/categories/', product_type='group', _lang='pt')
        return d if isinstance(d, list) else d.get('results', [])

    def grupos(self, categoria):
        d = self.get_json('/api/marketplace/v2/products/', limit=100, category_slugs=categoria,
                          fields='id,old_id,name,slug,code,hierarchy,product_type,brand,components',
                          order='position,name', product_type='group', _lang='pt')
        return d['results'] if isinstance(d, dict) else d

    def detalhe_grupo(self, slug):
        return self.get_json(f'/api/marketplace/v2/products/{slug}/', product_type='group', _lang='pt')

    def detalhe_produto(self, slug):
        return self.get_json(f'/api/marketplace/v2/products/{slug}/', product_type='product', _lang='pt',
                             fields='id,slug,name,code,details,description,images,hierarchy,attributes,brand,categories,product_type,is_available,extra_settings,resources')

    def recursos_produto(self, slug):
        return self.get_json(f'/api/marketplace/v1/products/{slug}/resources/')

    def pedir_url(self, lead, recurso, componente_uuid, page_url, page_name, form_padrao=None):
        corpo = {
            'form_id': recurso.get('form_uuid') or form_padrao,
            'resource_uuid': recurso['id'],
            'origin': 'component-file-download',
            'fields': {k: lead[k] for k in CAMPOS_LEAD},
            'page_name': page_name,
            'page_url': page_url,
            'component_uuid': componente_uuid,
        }
        _, raw, _ = self._req(self.host + '/api/crm/v1/form/', data=corpo)
        resp = json.loads(raw)
        url = resp.get('url') if isinstance(resp, dict) else None
        if not url:
            raise CatallogError(f'o formulário não devolveu a url para {recurso.get("title")!r}: {raw[:300]!r}')
        return url if url.startswith('http') else self.host + url

    def baixar(self, url, esperado=None):
        _, raw, hdr = self._req(url)
        if not raw:
            raise CatallogError(f'arquivo vazio: {url}')
        if esperado and len(raw) != esperado:
            raise CatallogError(f'{url.rsplit("/", 1)[-1]}: {len(raw)} bytes, o catálogo declara {esperado}')
        return raw, hdr.get('Content-Type', '')


def validar_lead(lead):
    faltam = [k for k in CAMPOS_LEAD if not str((lead or {}).get(k) or '').strip()]
    if faltam:
        raise CatallogError(f'dados do formulário de download incompletos — faltam {faltam}')
    if '@' not in lead['email']:
        raise CatallogError('e-mail do formulário inválido')
    return {k: str(lead[k]).strip() for k in CAMPOS_LEAD}


# ─── Plano e download ─────────────────────────────────────────────────────────

def nome_seguro(s):
    s = ''.join(c if c.isalnum() or c in ' ._-()' else '_' for c in s).strip()
    return ' '.join(s.split())[:120]


def planejar(cli, categoria, igs_por_grupo=1, dxf=False, progresso=avisar):
    """Grupos da categoria (com detalhe) e o plano `[(grupo, produto|None, recurso)]`."""
    grupos = cli.grupos(categoria)
    if not grupos:
        raise CatallogError(f'categoria {categoria!r} sem grupos em {cli.host}')
    progresso(f'{categoria}: {len(grupos)} grupo(s) em {cli.host}')
    plano = []
    for gi, g in enumerate(grupos, start=1):
        det = cli.detalhe_grupo(g['slug'])
        g['_detalhe'] = det
        progresso(f"  lendo grupo {gi}/{len(grupos)} — {g['name']} ({len(det.get('components') or [])} produto(s))")
        for r in det.get('resources') or []:
            plano.append((g, None, r))
        n_igs = 0
        for c in det.get('components') or []:
            if igs_por_grupo == 0 or (igs_por_grupo > 0 and n_igs >= igs_por_grupo):
                break
            rs = cli.recursos_produto(c['slug'])
            igs = [r for r in rs if r.get('type_key') == '.igs']
            if not igs:
                continue
            prod = cli.detalhe_produto(c['slug'])
            for r in igs:
                plano.append((g, prod, r))
            if dxf:
                plano.extend((g, prod, r) for r in rs if r.get('type_key') == '.dxf')
            n_igs += 1
            time.sleep(0.3)
        time.sleep(0.3)
    return grupos, plano


def baixar_plano(cli, plano, lead, destino, limite=0, progresso=avisar, form_padrao=None):
    """Baixa o que falta do plano para `destino`, mantendo `destino/manifesto.json`. Devolve o manifesto."""
    lead = validar_lead(lead)
    os.makedirs(destino, exist_ok=True)
    man_path = os.path.join(destino, 'manifesto.json')
    manifesto = {'host': cli.host, 'arquivos': []}
    if os.path.exists(man_path):
        with open(man_path, encoding='utf-8') as f:
            manifesto = json.load(f)
    ja = {a['resource_id'] for a in manifesto['arquivos'] if os.path.exists(os.path.join(destino, a['arquivo']))}
    novos = [p for p in plano if p[2]['id'] not in ja]
    progresso(f'{len(plano)} arquivo(s) no plano, {len(plano) - len(novos)} já baixado(s), {len(novos)} a baixar')
    baixados = 0
    for g, p, r in novos:
        pasta = nome_seguro(f"{g.get('code') or ''} {g['name']}")
        rel = os.path.join(pasta, (nome_seguro(r['title']) or r['id']) + r['type_key'])
        if p is None:
            page_url, page_name, comp = f"{cli.host}/pt/group/{g['slug']}", g['name'], g['_detalhe']['id']
        else:
            page_url, page_name, comp = f"{cli.host}/pt/product/{p['slug']}", p['name'], p['id']
        url = cli.pedir_url(lead, r, comp, page_url, page_name, form_padrao)
        raw, ctype = cli.baixar(url, r.get('size_in_bytes'))
        abs_ = os.path.join(destino, rel)
        os.makedirs(os.path.dirname(abs_), exist_ok=True)
        with open(abs_, 'wb') as f:
            f.write(raw)
        manifesto['arquivos'].append({
            'grupo': {k: g.get(k) for k in ('id', 'code', 'name', 'slug')},
            'produto': ({k: p.get(k) for k in ('id', 'code', 'name', 'slug')} if p else None),
            'produto_detalhe': p,
            'resource_id': r['id'], 'tipo': r['type_key'], 'titulo': r['title'], 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest(), 'content_type': ctype, 'url': url, 'arquivo': rel,
            'baixado_em': time.strftime('%Y-%m-%dT%H:%M:%S'),
        })
        with open(man_path, 'w', encoding='utf-8') as f:
            json.dump(manifesto, f, ensure_ascii=False, indent=1)
        baixados += 1
        progresso(f'  {baixados}/{len(novos)} {rel} ({len(raw) / 1e6:.2f} MB)')
        if limite and baixados >= limite:
            progresso(f'limite {limite} atingido')
            break
        time.sleep(cli.pausa)
    return manifesto


def gravar_grupos(grupos, destino):
    with open(os.path.join(destino, 'grupos.json'), 'w', encoding='utf-8') as f:
        json.dump([g.get('_detalhe') or g for g in grupos], f, ensure_ascii=False, indent=1)


# ─── Metadados → specs ────────────────────────────────────────────────────────

def _texto(h):
    t = re.sub(r'<br\s*/?>', ' ', h or '')
    t = re.sub(r'</(p|li|tr|h\d|div)>', ' ', t)
    t = re.sub(r'<[^>]+>', '', t)
    return ' '.join(html.unescape(t).split())


def secoes_details(details):
    """`<h5 class="tabs-detail-title">…Título</h5>…<div class="tabs-detail-content">…</div>` → {título: html}."""
    out = {}
    for m in re.finditer(r'tabs-detail-title">.*?</span>\s*(.*?)</h5>.*?tabs-detail-content">(.*?)</div>\s*</div>', details or '', re.S):
        out[_texto(m.group(1))] = m.group(2)
    return out


def tabela(html_tabela):
    """
    `(colunas, dados)` de uma tabela HTML. O cabeçalho da Tupy tem DUAS linhas com `colspan`/`rowspan`
    ("Diâmetro nominal" colspan=2 sobre "Polegada" e "mm"; "Dimensões em mm" sobre "L"; "Peso em g"
    rowspan=2) — as colunas-folha saem da expansão: célula que atravessa todas as linhas do cabeçalho
    é uma coluna; as outras cedem lugar às `colspan` células da linha de baixo. Uma só linha de
    cabeçalho (ou nenhuma) também funciona. Linhas de dados: texto por célula.
    """
    linhas = []
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', html_tabela or '', re.S):
        cels = []
        for attrs, conteudo in re.findall(r'<t([hd][^>]*)>(.*?)</t[hd]>', tr, re.S):
            cs = re.search(r'colspan="?(\d+)', attrs)
            rs = re.search(r'rowspan="?(\d+)', attrs)
            cels.append({'t': _texto(conteudo), 'cs': int(cs.group(1)) if cs else 1, 'rs': int(rs.group(1)) if rs else 1,
                         'th': attrs.startswith('h')})
        if cels:
            linhas.append(cels)
    eh_cab = lambda l: all(c['th'] for c in l) or (any(re.search(r'[A-Za-zÀ-ÿ]', c['t']) for c in l) and not re.match(r'^\d', l[0]['t'] or 'x'))
    cab = []
    while linhas and eh_cab(linhas[0]):
        cab.append(linhas.pop(0))
    dados = [[c['t'] for c in l] for l in linhas]
    if not cab:
        return [], dados
    n = len(cab)

    def folhas(linha_i, cels):
        out = []
        for c in cels:
            if c['rs'] >= n - linha_i or linha_i == n - 1:
                out.extend([c['t']] * c['cs'] if linha_i == n - 1 else [c['t']])
            else:
                # cede `cs` colunas às células da linha seguinte
                prox = cab[linha_i + 1]
                pegar, cons = c['cs'], 0
                sub = []
                while prox and cons < pegar:
                    s = prox.pop(0)
                    sub.extend(folhas(linha_i + 1, [s]))
                    cons += s['cs']
                out.extend(sub)
        return out
    colunas = folhas(0, [dict(c) for c in cab[0]]) if n > 1 else [c['t'] for c in cab[0] for _ in range(c['cs'])]
    return colunas, dados


def specs_do_produto(prod, grupo, partatom=None):
    specs = {'Código': str(prod.get('code') or '')}
    for a in prod.get('attributes') or []:
        vals = [v['value'] for v in a.get('values') or []]
        if vals:
            specs[a['attribute']['name']] = ', '.join(vals)
    for a in (grupo or {}).get('attributes') or []:
        nome = a['attribute']['name']
        vals = [v['value'] for v in a.get('values') or []]
        if vals and nome not in specs and nome != 'Diâmetro nominal':
            specs[nome] = ', '.join(vals)

    secs = secoes_details(prod.get('details'))
    if 'Dimensionais' in secs:
        colunas, dados = tabela(secs['Dimensionais'])
        imp = (specs.get('Tamanho (imperial)') or '').split(',')[0].strip()
        alvo = next((l for l in dados if len(dados) == 1 or (imp and imp in l)), None)
        if alvo:
            pares = []
            for i, v in enumerate(alvo):
                rot = colunas[i] if i < len(colunas) else f'c{i + 1}'
                if rot.lower() in ('polegada', 'mm') or v in (imp, specs.get('Tamanho (métrico)')):
                    continue
                pares.append(f'{rot} {v}')
            pesos = [p for p in pares if 'peso' in p.lower()]
            dims = [p for p in pares if p not in pesos]
            if dims:
                specs['Dimensões (mm)'] = '; '.join(dims)
            if pesos:
                specs['Peso (g)'] = re.sub(r'(?i)peso( em g)?\s*', '', pesos[0]).strip()
    for chave, rot in (('Material', 'Material'), ('Normas de fabricação', 'Normas'), ('Rosca', 'Rosca'),
                       ('Proteção superficial', 'Proteção superficial'), ('Tabela de pressão', 'Pressão')):
        if chave in secs:
            t = _texto(secs[chave])
            if t:
                specs[rot] = t[:400]
    if partatom:
        pa = partatom.get('partatom') or {}
        if pa.get('titulo'):
            specs['Família Revit'] = f"{pa['titulo']} ({partatom.get('revit') or 'Revit'})"
        tipos = [t['titulo'].rsplit(' - ', 1)[-1] for t in pa.get('tipos') or []]
        if tipos:
            specs['Tipos Revit'] = ', '.join(tipos)
    return {k: v for k, v in specs.items() if v}


def slugify(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode()
    return re.sub(r'^-|-$', '', re.sub(r'[^a-z0-9]+', '-', s.lower()))


# ─── Downloads → catálogo (o JSON do catalogo_de_aq.py) ───────────────────────

def catalogo_de_downloads(downloads, geo_dir, deflexao=0.2, forcar=False, progresso=avisar,
                          titulo=None, fabricante=None, extra_specs=None, origem=None):
    """
    Tessela cada IGES do `manifesto.json` (uma geometria por peça em `geo_dir/<codigo>.json`) e monta
    o catálogo. Lê o `PartAtom` dos `.rfa` quando o `olefile` está instalado (senão, avisa e segue).
    """
    from bim_pipeline.conversores import step_iges as step_to_geo
    try:
        from bim_pipeline.conversores import rfa_partatom
    except ImportError:
        rfa_partatom = None

    with open(os.path.join(downloads, 'manifesto.json'), encoding='utf-8') as f:
        man = json.load(f)
    grupos = {}
    gpath = os.path.join(downloads, 'grupos.json')
    if os.path.exists(gpath):
        with open(gpath, encoding='utf-8') as f:
            grupos = {g['slug']: g for g in json.load(f)}
    os.makedirs(geo_dir, exist_ok=True)

    avisos = []
    partatoms = {}
    for a in man['arquivos']:
        if a['tipo'] != '.rfa':
            continue
        if rfa_partatom is None or not rfa_partatom.HAS_OLEFILE:
            if 'olefile não instalado — os tipos das famílias Revit ficaram de fora' not in avisos:
                avisos.append('olefile não instalado — os tipos das famílias Revit ficaram de fora')
            continue
        try:
            info, _png = rfa_partatom.ler(os.path.join(downloads, a['arquivo']))
            partatoms.setdefault(a['grupo']['slug'], info)
        except Exception as e:   # um .rfa estranho não derruba o catálogo
            avisos.append(f"{a['arquivo']}: não li o PartAtom ({e})")

    produtos, series, com_peca = [], [], set()
    t_geo = 0.0
    for a in man['arquivos']:
        if a['tipo'] != '.igs':
            continue
        prod = a['produto_detalhe'] or a['produto']
        grupo = grupos.get(a['grupo']['slug']) or a['grupo']
        codigo = str(prod.get('code') or prod['slug'])
        geo_path = os.path.join(geo_dir, f'{codigo}.json')
        if forcar or not os.path.exists(geo_path):
            t0 = time.time()
            geo = step_to_geo.converter(os.path.join(downloads, a['arquivo']), deflexao)
            with open(geo_path, 'w', encoding='utf-8') as f:
                json.dump({k: geo[k] for k in ('pos', 'col', 'idx')}, f, separators=(',', ':'))
            t_geo += time.time() - t0
            progresso(f"  {codigo}: {len(geo['idx']) // 3} △, {geo.get('volume_cm3', 0):.0f} cm³"
                      f"{', ' + str(geo['arestas_livres']) + ' aresta(s) livre(s)' if geo.get('arestas_livres') else ''}, {time.time() - t0:.1f} s")
            if geo.get('arestas_livres'):
                avisos.append(f"{codigo}: casca com {geo['arestas_livres']} aresta(s) livre(s) após a costura")
        specs = specs_do_produto(prod, grupo, partatoms.get(a['grupo']['slug']))
        specs['Fonte 3D'] = os.path.basename(a['arquivo'])
        specs['URL'] = f"{man.get('host', '')}/pt/product/{prod['slug']}"
        specs.update(extra_specs or {})
        serie = grupo['name']
        if serie not in series:
            series.append(serie)
        produtos.append({
            'id': prod['slug'], 'nome': prod['name'], 'serie': serie, 'geo': f'{codigo}.json',
            'potencia': None, 'conexoes': serie, 'specs': specs, 'curva': None, 'codigo': codigo,
        })
        com_peca.add(a['grupo']['slug'])

    sem = [g['name'] for s, g in grupos.items() if s not in com_peca]
    if sem:
        avisos.append(f"{len(sem)} grupo(s) sem IGES ficaram fora: {', '.join(sem)}")
    marca = next((p.get('brand', {}).get('name') for a in man['arquivos'] for p in [a.get('produto_detalhe') or {}] if p.get('brand')), None)
    fabricante = fabricante or marca or 'Catallog'
    cat_nome = None
    for g in grupos.values():
        h = (g.get('hierarchy') or [[]])[0]
        if h and h[0].get('type') == 'category':
            cat_nome = h[0]['name']
            break
    titulo = titulo or cat_nome or 'Catálogo'
    descricao = ' '.join((next((g.get('description') for g in grupos.values() if g.get('description')), '') or '').split())[:500]
    slug = slugify(titulo) or 'catalogo'
    config = {'slug': slug, 'titulo': titulo, 'fabricante': fabricante, 'descricao': descricao, 'layout': 'catalog-grid'}
    bytes_ = sum(a['bytes'] for a in man['arquivos'])
    return {
        'config': config,
        'catalog': {**config, 'filtros': series, 'produtos': produtos},
        'n_geometrias': len(produtos),
        'diag': {'pecas_sem_simbologia': 0, 'pecas_sim_descartada': 0, 'sim_sem_blob': 0, 'sim_nao_oq3d': 0,
                 'sim_ilegivel': [], 'sim_vazia': [], 'avisos': avisos},
        'hints': {'n_pecas': len(produtos), 'n_simbologias': len(produtos), 'schema': 'catallog', 'grupos': series,
                  'linhas': [titulo], 'has_curves': False,
                  'origem': {**(origem or {}), 'host': man.get('host'), 'arquivos': len(man['arquivos']), 'bytes': bytes_,
                             'grupos': len(grupos), 'grupos_sem_igs': sem, 'segundos_tesselacao': round(t_geo, 1)}},
    }


def importar(host, categoria, lead, downloads, geo_dir, igs_por_grupo=1, dxf=False, deflexao=0.2,
             limite=0, progresso=avisar, plugin=None):
    cli = Catallog(host)
    s = cli.settings()
    form_padrao = (s.get('forms') or {}).get('download')
    titulo_site = cli.titulo(s)
    grupos, plano = planejar(cli, categoria, igs_por_grupo, dxf, progresso)
    baixar_plano(cli, plano, lead, downloads, limite, progresso, form_padrao)
    gravar_grupos(grupos, downloads)
    extra = {'Catálogo': f'{titulo_site} ({host})'}
    if plugin:
        extra['Plugin AutoCAD'] = ' '.join(str(x) for x in (plugin.get('plugin'), plugin.get('versao')) if x) or plugin.get('arquivo', '')
    cat = next((c['name'] for c in grupos[0].get('hierarchy', [[]])[0] if c.get('type') == 'category'), None) if grupos else None
    return catalogo_de_downloads(downloads, geo_dir, deflexao, progresso=progresso, titulo=cat, extra_specs=extra,
                                 origem={'categoria': categoria, 'titulo_site': titulo_site, 'plugin': plugin})


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    i = sub.add_parser('inspecionar', help='DLL do plugin → host, título do catálogo e categorias (JSON no stdout)')
    i.add_argument('dll')
    i.add_argument('--sem-rede', action='store_true', help='só o que está na DLL')
    m = sub.add_parser('importar', help='baixa uma categoria e devolve o catálogo (JSON em --saida)')
    m.add_argument('--host', required=True)
    m.add_argument('--categoria', required=True)
    m.add_argument('--lead', required=True, help='JSON com full_name, email, mobile, company, position')
    m.add_argument('--downloads', required=True)
    m.add_argument('--geo-dir', required=True)
    m.add_argument('--saida', required=True)
    m.add_argument('--igs-por-grupo', type=int, default=1)
    m.add_argument('--dxf', action='store_true')
    m.add_argument('--deflexao', type=float, default=0.2)
    m.add_argument('--limite', type=int, default=0)
    m.add_argument('--plugin', help='JSON do `inspecionar`, para registrar nome/versão do plugin nas specs')
    m.add_argument('--sair-com-stdin', action='store_true', help='termina com 2 quando o processo pai fecha o stdin')
    args = ap.parse_args()

    if args.cmd == 'inspecionar':
        info = inspecionar_dll(args.dll)
        if not args.sem_rede:
            cli = Catallog(info['host'])
            s = cli.settings()
            info['titulo'] = cli.titulo(s)
            info['formulario_download'] = (s.get('forms') or {}).get('download')
            cats = []
            for c in cli.categorias():
                gs = cli.grupos(c['slug'])
                cats.append({'slug': c['slug'], 'name': c['name'], 'grupos': len(gs),
                             'grupos_nomes': [g['name'] for g in gs]})
                time.sleep(0.2)
            info['categorias'] = cats
        print(json.dumps(info, ensure_ascii=False))
        return

    if args.sair_com_stdin:
        from bim_pipeline.processo import vigiar_stdin
        vigiar_stdin()
    with open(args.lead, encoding='utf-8') as f:
        lead = json.load(f)
    plugin = None
    if args.plugin:
        with open(args.plugin, encoding='utf-8') as f:
            plugin = json.load(f)
    resultado = importar(args.host, args.categoria, lead, os.path.abspath(args.downloads), os.path.abspath(args.geo_dir),
                         args.igs_por_grupo, args.dxf, args.deflexao, args.limite, plugin=plugin)
    with open(args.saida, 'w', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False)
    o = resultado['hints']['origem']
    avisar(f"pronto — {resultado['n_geometrias']} peça(s) de {o['grupos']} grupo(s), {o['arquivos']} arquivo(s), "
           f"{o['bytes'] / 1e6:.0f} MB → {args.saida}")


if __name__ == '__main__':
    main()
