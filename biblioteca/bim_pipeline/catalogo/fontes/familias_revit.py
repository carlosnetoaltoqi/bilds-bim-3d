#!/usr/bin/env python3
"""
familias_revit.py — de famílias Revit (`.rfa`, soltas, numa pasta ou num `.zip`) a um catálogo do
bilds-bim-3d, no MESMO JSON que o `catalogo_de_aq.py` devolve — para o criador publicar como publica
uma biblioteca, e para o catálogo virar `.aq` pelo caminho já existente (`catalogo_para_aq`).

O QUE UM `.rfa` DÁ SEM O REVIT (`docs/conhecimento/revit-familias.md`, `conversores/rfa_partatom.py`):
o título da família, a categoria (nome ou código OmniClass), a versão do Revit, a miniatura e a
TABELA DE TIPOS com todos os parâmetros — inclusive `Manufacturer`, `Model`, dimensões com unidade e
materiais. Quando a família tem *type catalog* (`<mesmo nome>.txt` ao lado), ele é a fonte dos tipos:
o `.rfa` costuma guardar um só tipo-molde e o `.txt` traz os cento e sessenta.

O QUE NÃO DÁ: a geometria. Fica em `Partitions/<n>`, gzip de um binário proprietário que nenhum
leitor fora do Revit decodifica; o Revit não exporta uma família para IFC sem carregá-la num projeto;
um `.rvt` (projeto) não tem `PartAtom` e não entrega as famílias embutidas. Daí a regra HÍBRIDA:

  1. Se existe um arquivo de geometria IRMÃO da família (mesmo nome, `.ifc`/`.stp`/`.step`/`.igs`/`.iges`
     — exportado do Revit via projeto, ou baixado do portal do fabricante, que costuma oferecer IFC ao
     lado do RFA), a geometria REAL vem dele pelos conversores da biblioteca, compartilhada por todos
     os tipos da família (uma simbologia, N peças — como o `.aq` faz).
  2. Senão, cada tipo ganha uma FORMA REPRESENTATIVA por parâmetro (`geometria/perfis.py`): seção I/U/L,
     tubo retangular ou redondo, caixa, chapa perfilada — as cotas da seção são DADO (vêm dos parâmetros
     do tipo); o comprimento do trecho e o que a família não cota são INVENÇÃO, na tabela `PROPORCOES`,
     e a ressalva vai gravada na série ("… (forma representativa)") e na spec "Geometria 3D", como manda
     `docs/conhecimento/formas-representativas.md`.
  3. Tipo sem parâmetro dimensional reconhecível fica FORA (avisado no diagnóstico): sem geometria não há
     peça no `.aq` (`aq-escrita.md`).

PROJETOS `.rvt` (ADR-019): um projeto não tem `PartAtom`, mas fabricantes distribuem modelos de amostra com as
famílias já colocadas. Um `.rvt` entra por um IFC: o IRMÃO de mesmo nome quando existe (grátis), ou a tradução
`.rvt → IFC` pela Autodesk Platform Services (`conversores/aps.py`) quando quem importa autoriza (`--aps-credenciais`
ou `--aps`; cada projeto custa um job, com cache por SHA-256). Do IFC, `conversores/ifc_elementos.py` separa os
elementos e cada TIPO de família ("Família:Tipo") vira um produto com a geometria real da primeira instância;
os psets do Revit (Identity Data etc.) viram specs. Sem IFC irmão e sem APS, o projeto fica fora com aviso.

COMPATIBILIDADE COM O `.aq`: todo texto que vai para nome, série, chave e valor de spec passa por
`cp1252_seguro` — o escritor do `.aq` é estrito e aborta num caractere fora do cp1252.

SAÍDA (`--saida`): `{config, catalog, n_geometrias, diag, hints}` com `hints.schema = 'familias-revit'` e
`hints.origem` (arquivos, famílias, tipos, quantas com geometria irmã, quantas representativas, versões).
Um `<geo>.json` por geometria em `--geo-dir`. Progresso no stderr; erro sai com 1.

Uso:
    python3 -m bim_pipeline.cli.familias_revit inspecionar familias.zip            # famílias, tipos, categorias, projetos → stdout JSON
    python3 -m bim_pipeline.cli.familias_revit importar familias.zip --geo-dir DIR --saida catalogo.json \
        [--titulo T] [--fabricante F] [--comprimento-mm 1000] [--deflexao 0.2] [--trabalho DIR] [--sair-com-stdin] \
        [--aps | --aps-credenciais cred.json] [--aps-cache DIR]      # projetos .rvt → IFC pela APS (cobrado por projeto)
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
import zipfile

from bim_pipeline.catalogo.catalogo import diag_vazio, montar_catalogo, montar_resultado, slugify
from bim_pipeline.conversores import rfa_partatom, type_catalog
from bim_pipeline.geometria import perfis
from bim_pipeline.geometria.eixos import CM_TO_M, zup_para_viewer

EXT_RFA = ('.rfa',)
EXT_GEO = ('.ifc', '.ifczip', '.stp', '.step', '.igs', '.iges')
EXT_PROJETO = ('.rvt', '.rte', '.rft')

# Tudo o que a família NÃO cota e este módulo inventa — uma regra por linha, explícita (formas-representativas.md).
PROPORCOES = {
    'comprimento_perfil_mm': 1000.0,   # trecho representativo de viga, pilar, tubo estrutural, cantoneira
    'deck_altura_nervura_mm': 60.0,    # chapa perfilada sem altura de nervura nos parâmetros
    'deck_passo_mm': 280.0,            # passo entre nervuras de uma chapa perfilada
    'deck_comprimento_mm': 1000.0,     # trecho representativo de telha/deck
    'caixa_profundidade': lambda largura, altura: min(largura, altura),   # caixa com só largura e altura
}

RESSALVA = ('Forma representativa gerada a partir dos parâmetros da família Revit: as cotas da seção são as do '
            'tipo; comprimento do trecho e detalhes não cotados (raios, soldas, furos) são aproximados. '
            'Não serve para conferir encaixe.')
SUFIXO_SERIE = ' (forma representativa)'

# Sinônimos (EN/PT) dos parâmetros dimensionais, já normalizados por `_norm`. Letra solta só casa exata.
SINONIMOS = {
    'espessura_chapa':   ('espessura da chapa', 'espessura chapa', 'sheet thickness', 'deck thickness', 'espessura da telha'),
    'largura_modulo':    ('largura do modulo', 'largura modulo', 'module width', 'cover width', 'largura util', 'largura de cobertura'),
    'altura_nervura':    ('altura da nervura', 'altura nervura', 'rib height', 'deck height', 'altura do perfil', 'altura da telha', 'profile height'),
    'espessura_capa':    ('espessura capa de concreto', 'espessura da capa de concreto', 'espessura da capa', 'topping thickness', 'concrete thickness', 'espessura do concreto'),
    'capa':              ('capa de concreto', 'concrete topping', 'com capa de concreto', 'with concrete'),
    'espessura_flange':  ('flange thickness', 'espessura do flange', 'espessura da mesa', 'espessura mesa', 'tf'),
    'espessura_alma':    ('web thickness', 'espessura da alma', 'espessura da teia', 'espessura alma', 'tw'),
    'espessura_parede':  ('wall nominal thickness', 'wall thickness', 'wall design thickness', 'espessura nominal da parede',
                          'espessura da parede', 'espessura de projeto da parede', 'espessura parede', 'thickness', 'espessura', 't'),
    'diametro':          ('diameter', 'diametro', 'outside diameter', 'outer diameter', 'diametro externo', 'nominal diameter',
                          'diametro nominal', 'dn', 'd ext', 'de'),
    'largura':           ('width', 'largura', 'flange width', 'largura da mesa', 'largura do flange', 'b', 'bf', 'w'),
    'altura':            ('height', 'altura', 'h', 'd', 'section height', 'altura da secao'),
    'profundidade':      ('depth', 'profundidade', 'comprimento total'),
    'comprimento':       ('length', 'comprimento', 'l', 'comprimento do trecho'),
}
_TIPOS_COMPRIMENTO_PARTATOM = ('length', 'section property', 'section dimension', 'pipe size', 'duct size', 'reinforcement length')
_RE_VERTICAL = re.compile(r'(?i)\b(pilar(?:es)?|coluna|column|post|poste|montante)\b')
_RE_ESTRUTURAL = re.compile(r'(?i)\b(viga|beam|pilar|coluna|column|perfil|section|framing|tubo|tube|hollow|terca|purlin|'
                            r'cantoneira|angle|trelica|truss|barra|bar|brace|contraventamento)\b')
_RE_U = re.compile(r'(?i)(\bu\b|\bue\b|\bchannel\b|perfil u|\bcanal\b|\bc\s?\d)')
_RE_L = re.compile(r'(?i)(\bl\b|cantoneira|\bangle\b)')
_RE_OMNICLASS = re.compile(r'^\d{2}(?:[.\-]\d{2}){1,}$')


class FamiliasRevitError(SystemExit):
    def __init__(self, msg):
        super().__init__(f'familias_revit: {msg}')


def avisar(msg):
    print(msg, file=sys.stderr, flush=True)


# ─── Texto ────────────────────────────────────────────────────────────────────

_SUBSTITUICOES_CP1252 = {'→': '->', '←': '<-', '≥': '>=', '≤': '<=', '−': '-', '′': "'", '″': '"', '•': '-', ' ': ' ',
                         '≈': '~', '≠': '<>', '∅': 'diam.', 'Ø': 'diam.', ' ': ' ', '​': ''}


def cp1252_seguro(texto):
    """
    O texto codificável em cp1252 (o `.aq` exige — `aq-escrita.md`): troca o que tem equivalente
    ("→" → "->", "≥" → ">=") e substitui o resto por "?". Devolve `(texto, mudou)`.
    """
    s = str(texto if texto is not None else '')
    try:
        s.encode('cp1252')
        return s, False
    except UnicodeEncodeError:
        pass
    for de, para in _SUBSTITUICOES_CP1252.items():
        s = s.replace(de, para)
    saida = s.encode('cp1252', errors='replace').decode('cp1252')
    return saida, True


def _norm(nome):
    s = unicodedata.normalize('NFD', str(nome or ''))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', s).split())


def humanizar(titulo):
    """"Viga_PerfilSoldado-VS_Empresa" → "Viga PerfilSoldado-VS Empresa": só o que o Revit trocou por `_`."""
    return ' '.join(str(titulo or '').replace('_', ' ').split())


# ─── Valores com unidade ──────────────────────────────────────────────────────

_RE_NUM = re.compile(r'^\s*(-?\d+(?:[.,]\d+)?)\s*(mm|cm|dm|m|in|"|″|ft|\'|′)?\s*$')
_RE_FRAC_POL = re.compile(r'^\s*(?:(\d+)\s+)?(\d+)/(\d+)\s*(?:"|″|in)\s*$')
_MM = {'mm': 1.0, 'cm': 10.0, 'dm': 100.0, 'm': 1000.0, 'in': 25.4, '"': 25.4, '″': 25.4, 'ft': 304.8, "'": 304.8, '′': 304.8}


def valor_em_mm(texto, tipo=None):
    """
    "350.00 mm" → 350.0; "0.84 m" → 840.0; "29 7/8\"" → 758.8; "15" → 15.0 (sem unidade assume mm — a
    unidade de projeto mais comum no Brasil; `tipo` é o typeOfParameter do PartAtom e restringe a
    conversão a comprimentos). None quando não é número ou o tipo não é de comprimento.
    """
    if tipo is not None and _norm(tipo) not in _TIPOS_COMPRIMENTO_PARTATOM:
        return None
    t = str(texto or '').strip()
    m = _RE_FRAC_POL.match(t)
    if m:
        inteiro = float(m.group(1) or 0)
        return (inteiro + float(m.group(2)) / float(m.group(3))) * 25.4
    m = _RE_NUM.match(t.replace(' ', ''))
    if not m:
        return None
    n = float(m.group(1).replace(',', '.'))
    return n * _MM.get(m.group(2) or 'mm', 1.0)


# ─── Descoberta dos arquivos ──────────────────────────────────────────────────

def _seguro(nome):
    p = nome.replace('\\', '/')
    return not (p.startswith('/') or '..' in p.split('/') or ':' in p.split('/')[0])


def extrair_zip(caminho, destino, progresso=avisar):
    """
    Extrai do `.zip` só o que interessa (`.rfa`, `.txt`, geometria irmã), preservando as pastas;
    ignora o resto (planilhas, PDFs) e qualquer caminho suspeito. Devolve `(extraidos, ignorados)`.
    """
    extraidos, ignorados = [], []
    with zipfile.ZipFile(caminho) as z:
        for info in z.infolist():
            nome = info.filename
            if info.is_dir():
                continue
            if not _seguro(nome):
                ignorados.append(nome)
                continue
            ext = os.path.splitext(nome)[1].lower()
            if ext not in EXT_RFA + EXT_GEO + EXT_PROJETO + ('.txt',):
                ignorados.append(nome)
                continue
            alvo = os.path.join(destino, *nome.replace('\\', '/').split('/'))
            os.makedirs(os.path.dirname(alvo), exist_ok=True)
            with z.open(info) as f, open(alvo, 'wb') as g:
                shutil.copyfileobj(f, g)
            extraidos.append(nome)
    progresso(f'{os.path.basename(caminho)}: {len(extraidos)} arquivo(s) extraído(s), {len(ignorados)} ignorado(s)')
    return extraidos, ignorados


def descobrir(raiz):
    """
    Numa pasta (ou no caminho de um `.rfa` solto): as famílias e, para cada uma, o type catalog e a
    geometria irmã (mesmo nome, `EXT_GEO`) — primeiro na mesma pasta, depois em qualquer pasta.
    `{'raiz', 'familias': [{rfa, rel, pasta, txt, geometria}], 'projetos': [rel], 'outros': [rel]}`.
    """
    if os.path.isfile(raiz):
        arquivos = [os.path.abspath(raiz)]
        pasta_raiz = os.path.dirname(arquivos[0])
        arquivos += [os.path.join(pasta_raiz, n) for n in os.listdir(pasta_raiz)
                     if os.path.splitext(n)[1].lower() in EXT_GEO + ('.txt',)]
    else:
        pasta_raiz = os.path.abspath(raiz)
        arquivos = [os.path.join(dp, n) for dp, _ds, ns in os.walk(pasta_raiz) for n in sorted(ns)]
    por_ext = {}
    for a in arquivos:
        por_ext.setdefault(os.path.splitext(a)[1].lower(), []).append(a)
    geos = {}
    for ext in EXT_GEO:
        for g in por_ext.get(ext, []):
            geos.setdefault(_norm(os.path.splitext(os.path.basename(g))[0]), []).append(g)
    txts = {}
    for t in por_ext.get('.txt', []):
        txts.setdefault((os.path.dirname(t), _norm(os.path.splitext(os.path.basename(t))[0])), t)

    def irma(caminho):
        candidatos = geos.get(_norm(os.path.splitext(os.path.basename(caminho))[0]), [])
        return next((g for g in candidatos if os.path.dirname(g) == os.path.dirname(caminho)), candidatos[0] if candidatos else None)

    familias = []
    for rfa in sorted(por_ext.get('.rfa', [])):
        base = os.path.splitext(os.path.basename(rfa))[0]
        chave = _norm(base)
        txt = txts.get((os.path.dirname(rfa), chave))
        if txt and not type_catalog.eh_type_catalog(type_catalog.decodificar(open(txt, 'rb').read(4096))):
            txt = None
        familias.append({
            'rfa': rfa, 'rel': os.path.relpath(rfa, pasta_raiz), 'pasta': os.path.relpath(os.path.dirname(rfa), pasta_raiz),
            'txt': txt, 'geometria': irma(rfa),
        })
    projetos = []
    for ext in EXT_PROJETO:
        for p in sorted(por_ext.get(ext, [])):
            g = irma(p)
            projetos.append({'rvt': p, 'rel': os.path.relpath(p, pasta_raiz), 'ifc': g if g and g.lower().endswith(('.ifc', '.ifczip')) else None})
    return {'raiz': pasta_raiz, 'familias': familias, 'projetos': projetos}


# ─── Leitura de uma família ───────────────────────────────────────────────────

def _categoria(pa):
    """`{'termo', 'omniclass', 'nome'}` da primeira categoria do PartAtom: código OmniClass ou nome de categoria Revit."""
    cats = pa.get('categorias') or []
    termo = next((c.get('termo') for c in cats if c.get('termo')), None)
    if not termo:
        return {'termo': None, 'omniclass': None, 'nome': None}
    if _RE_OMNICLASS.match(termo.strip()):
        return {'termo': termo, 'omniclass': termo.strip(), 'nome': None}
    return {'termo': termo, 'omniclass': None, 'nome': termo.strip()}


def _tipos_partatom(pa):
    """Os tipos do PartAtom no mesmo formato do type catalog: `{titulo: {nome: {valor, tipo, unidade, mm}}}`, em ordem."""
    out = {}
    for t in pa.get('tipos_detalhados') or []:
        params = {}
        for nome, d in (t.get('parametros') or {}).items():
            params[nome] = {'valor': d.get('valor') or '', 'tipo': d.get('tipo'), 'unidade': None,
                            'mm': valor_em_mm(d.get('valor'), d.get('tipo'))}
        out[t['titulo']] = params
    return out


def fundir_tipos(tipos_partatom, catalogo_txt):
    """
    Type catalog primeiro (é o que o Revit oferece ao carregar), PartAtom depois: tipos que só o
    PartAtom tem entram; parâmetros que só o PartAtom tem completam os do `.txt`; parâmetros
    CONSTANTES em todos os tipos do PartAtom (fabricante, URL, norma, material) vão para todos.
    Devolve `[(titulo, parametros)]` na ordem.
    """
    ordem, tipos = [], {}
    for t in (catalogo_txt or {}).get('tipos') or []:
        if t['titulo'] not in tipos:
            ordem.append(t['titulo'])
        tipos[t['titulo']] = dict(t['parametros'])
    constantes = {}
    if tipos_partatom:
        nomes = set.intersection(*(set(p) for p in tipos_partatom.values()))
        for nome in nomes:
            vals = {json.dumps(p[nome], sort_keys=True) for p in tipos_partatom.values()}
            if len(vals) == 1:
                constantes[nome] = next(iter(tipos_partatom.values()))[nome]
    for titulo, params in tipos_partatom.items():
        if titulo not in tipos:
            if ordem and len(tipos_partatom) == 1 and titulo not in tipos:
                # um só tipo-molde no .rfa e um type catalog com os tipos reais: o molde não é produto
                continue
            ordem.append(titulo)
            tipos[titulo] = {}
        for nome, d in params.items():
            tipos[titulo].setdefault(nome, d)
    for titulo in ordem:
        for nome, d in constantes.items():
            tipos[titulo].setdefault(nome, d)
    return [(t, tipos[t]) for t in ordem]


def ler_familia(fam, progresso=avisar):
    """`fam` de `descobrir` → a família lida: título, categoria, revit, tipos fundidos, avisos."""
    info, png = rfa_partatom.ler(fam['rfa'])
    pa = info.get('partatom') or {}
    avisos = []
    catalogo_txt = None
    if fam.get('txt'):
        try:
            catalogo_txt = type_catalog.ler(fam['txt'])
        except Exception as e:   # um .txt estranho não derruba a família
            avisos.append(f"{os.path.basename(fam['txt'])}: type catalog ilegível ({e}) — só os tipos do .rfa")
    tipos = fundir_tipos(_tipos_partatom(pa), catalogo_txt)
    titulo = pa.get('titulo') or os.path.splitext(os.path.basename(fam['rfa']))[0]
    if not pa:
        avisos.append(f"{fam['rel']}: sem PartAtom (família anterior ao Revit 2011?) — sem tipos nem categoria")
    return {
        **fam, 'titulo': titulo, 'categoria': _categoria(pa), 'revit': info.get('revit'), 'formato': info.get('formato'),
        'locale': info.get('locale'), 'preview': png is not None, 'tipos': tipos, 'type_catalog': catalogo_txt is not None,
        'parametros_familia': pa.get('parametros_familia') or {}, 'avisos': avisos,
    }


# ─── Dimensões e forma ───────────────────────────────────────────────────────

def dimensoes(parametros):
    """
    Os parâmetros de um tipo → cotas canônicas em mm (`largura`, `altura`, `profundidade`, `diametro`,
    `espessura_parede`, `espessura_flange`, `espessura_alma`, `comprimento`, `espessura_chapa`,
    `largura_modulo`, `altura_nervura`, `espessura_capa`) e `capa` (bool). Casamento por sinônimo
    normalizado; a primeira chave da tabela que casa fica com o parâmetro (os específicos vêm antes
    dos genéricos: "espessura da chapa" antes de "espessura").
    """
    dims, usados = {}, set()
    normalizados = {_norm(nome): (nome, d) for nome, d in parametros.items()}
    for chave, sins in SINONIMOS.items():
        for s in sins:
            hit = normalizados.get(s)
            if not hit or hit[0] in usados:
                continue
            nome, d = hit
            if chave == 'capa':
                v = _norm(d.get('valor'))
                dims['capa'] = v in ('1', 'yes', 'sim', 'true', 'verdadeiro')
                usados.add(nome)
                break
            mm = d.get('mm')
            if mm is None:
                mm = valor_em_mm(d.get('valor'))
            if mm is None or mm <= 0:
                continue
            dims[chave] = mm
            usados.add(nome)
            break
    if 'altura' not in dims and 'profundidade' in dims and ('espessura_flange' in dims or 'espessura_alma' in dims or 'espessura_parede' in dims):
        dims['altura'] = dims.pop('profundidade')     # "Depth" de um perfil é a altura da seção
    return dims


def _cor(material):
    m = _norm(material)
    if 'galv' in m or 'zinc' in m:
        return perfis.COR['aco_galv']
    if 'aco' in m or 'steel' in m or 'metal' in m or 'ferro' in m or 'iron' in m or 'aluminio' in m or 'aluminum' in m:
        return perfis.COR['aco']
    if 'concreto' in m or 'concrete' in m:
        return perfis.COR['concreto']
    return perfis.COR['generico']


def _material(parametros):
    for nome, d in parametros.items():
        if _norm(d.get('tipo')) == 'material' or 'material' in _norm(nome):
            if d.get('valor'):
                return d['valor']
    return ''


def _palavras(*textos):
    """Título de família e categoria como palavras separadas: o Revit troca espaço por `_` e o fabricante usa `-` ("Column_WeldedSection-CS")."""
    return ' '.join(str(t or '').replace('_', ' ').replace('-', ' ') for t in textos)


def eh_vertical(titulo, categoria_nome=None):
    """Pilar/coluna/poste ficam em pé (comprimento em +Z); o resto deita (comprimento em +X)."""
    return bool(_RE_VERTICAL.search(_palavras(titulo, categoria_nome)))


def forma_representativa(dims, titulo, categoria_nome=None, material='', comprimento_mm=None):
    """
    `(nome_da_forma, [(verts, tris, rgba)], regra)` em cm Z-up a partir das cotas, ou None se não há cota
    suficiente. `regra` diz, em texto, o que foi dado e o que foi inventado — vai para a spec.
    """
    texto = _palavras(titulo, categoria_nome)
    titulo = _palavras(titulo)
    vertical = eh_vertical(titulo, categoria_nome)
    L = (dims.get('comprimento') if dims.get('comprimento') and 100 <= dims['comprimento'] <= 20000 else None)
    L_cm = (L or comprimento_mm or PROPORCOES['comprimento_perfil_mm']) / 10.0
    origem_L = 'comprimento do tipo' if L else f'trecho de {L_cm * 10:.0f} mm (aprox.)'
    cor = _cor(material)
    cm = lambda k: dims[k] / 10.0

    def orientar(vt):
        return vt if vertical else perfis.deitar(vt)

    # chapa perfilada (telha-forma / steel deck)
    if 'espessura_chapa' in dims and ('largura_modulo' in dims or 'largura' in dims):
        largura = dims.get('largura_modulo') or dims['largura']
        altura = dims.get('altura_nervura') or dims.get('altura') or PROPORCOES['deck_altura_nervura_mm']
        origem_h = 'altura da nervura do tipo' if (dims.get('altura_nervura') or dims.get('altura')) else f'altura de nervura {altura:.0f} mm (aprox.)'
        comp = (comprimento_mm or PROPORCOES['deck_comprimento_mm']) / 10.0
        placas = perfis.chapa_trapezoidal(largura / 10.0, altura / 10.0, cm('espessura_chapa'), PROPORCOES['deck_passo_mm'] / 10.0, comprimento=comp)
        malhas = [(perfis.assentar(v, comp), t, perfis.COR['aco_galv'] if not material else cor) for v, t in placas]
        regra = f'chapa trapezoidal: largura e espessura do tipo; {origem_h}; passo {PROPORCOES["deck_passo_mm"]:.0f} mm e trecho de {comp * 10:.0f} mm (aprox.)'
        if dims.get('capa') and dims.get('espessura_capa'):
            # a capa é uma laje sobre a mesa superior da nervura: mesma largura e trecho, espessura do tipo
            e_capa = cm('espessura_capa')
            v, t = perfis.extrudar([perfis.retangulo(largura / 10.0, e_capa, cy=altura / 10.0 + e_capa / 2)], comp)
            malhas.append((perfis.assentar(v, comp), t, perfis.COR['concreto']))
            regra += '; capa de concreto com a espessura do tipo'
        return 'chapa_perfilada', malhas, regra

    # tubo redondo / barra redonda
    if 'diametro' in dims:
        d = cm('diametro')
        if dims.get('espessura_parede') and dims['espessura_parede'] * 2 < dims['diametro']:
            v, t = perfis.extrudar([perfis.circulo(d), perfis.circulo(d - 2 * cm('espessura_parede'))], L_cm)
            return 'tubo_redondo', [(orientar(v), t, cor)], f'tubo redondo: diâmetro e parede do tipo; {origem_L}'
        v, t = perfis.extrudar([perfis.circulo(d)], L_cm)
        return 'barra_redonda', [(orientar(v), t, cor)], f'cilindro: diâmetro do tipo; {origem_L}'

    b, h = dims.get('largura'), dims.get('altura')
    if b and h:
        tf, tw, tp = dims.get('espessura_flange'), dims.get('espessura_alma'), dims.get('espessura_parede')
        # perfil I / U / L
        if tf and tw and tf * 2 < h and tw < b:
            if _RE_U.search(titulo):
                v, t = perfis.extrudar([perfis.secao_u(b / 10, h / 10, tf / 10, tw / 10)], L_cm)
                return 'perfil_u', [(orientar(v), t, cor)], f'perfil U: largura, altura, mesa e alma do tipo; {origem_L}; cantos vivos'
            v, t = perfis.extrudar([perfis.secao_i(b / 10, h / 10, tf / 10, tw / 10)], L_cm)
            return 'perfil_i', [(orientar(v), t, cor)], f'perfil I: largura, altura, mesa e alma do tipo; {origem_L}; sem solda nem raio'
        if tp and _RE_L.search(titulo) and tp < min(b, h):
            v, t = perfis.extrudar([perfis.secao_l(b / 10, h / 10, tp / 10)], L_cm)
            return 'cantoneira', [(orientar(v), t, cor)], f'cantoneira: abas e espessura do tipo; {origem_L}'
        # tubo retangular
        if tp and tp * 2 < min(b, h):
            v, t = perfis.extrudar([perfis.retangulo(b / 10, h / 10), perfis.retangulo(b / 10 - 2 * tp / 10, h / 10 - 2 * tp / 10)], L_cm)
            return 'tubo_retangular', [(orientar(v), t, cor)], f'tubo retangular: largura, altura e parede do tipo; {origem_L}; cantos vivos'
        # caixa (equipamento) ou barra retangular (estrutural)
        if dims.get('profundidade'):
            v, t = perfis.caixa(b / 10, cm('profundidade'), h / 10)
            return 'caixa', [(v, t, cor)], 'caixa: largura, profundidade e altura do tipo'
        if _RE_ESTRUTURAL.search(texto):
            v, t = perfis.extrudar([perfis.retangulo(b / 10, h / 10)], L_cm)
            return 'barra_retangular', [(orientar(v), t, cor)], f'barra retangular: largura e altura do tipo; {origem_L}'
        prof = PROPORCOES['caixa_profundidade'](b, h)
        v, t = perfis.caixa(b / 10, prof / 10, h / 10)
        return 'caixa', [(v, t, cor)], f'caixa: largura e altura do tipo; profundidade {prof:.0f} mm (aprox.)'
    return None


# ─── Geometria → JSON do viewer ──────────────────────────────────────────────

def geo_do_viewer(malhas):
    """`[(verts_cm_zup, tris, rgba)]` → `{pos, col, idx}` em metros Y-up (contrato `geometria`)."""
    pos, col, idx = [], [], []
    for verts, tris, rgba in malhas:
        base = len(pos) // 3
        r, g, b = (c / 255.0 for c in rgba[:3])
        for x, y, z in verts:
            vx, vy, vz = zup_para_viewer(x, y, z, CM_TO_M)
            pos += [round(vx, 6), round(vy, 6), round(vz, 6)]
            col += [round(r, 4), round(g, 4), round(b, 4)]
        for a, b_, c in tris:
            idx += [base + a, base + b_, base + c]
    return {'pos': pos, 'col': col, 'idx': idx}


def geo_de_arquivo(caminho, deflexao=0.2, progresso=avisar):
    """A geometria irmã pelos conversores da biblioteca (importados só aqui — OpenCASCADE/ifcopenshell são opcionais)."""
    ext = os.path.splitext(caminho)[1].lower()
    if ext in ('.ifc', '.ifczip'):
        from bim_pipeline.conversores import ifc
        geo = ifc.converter(caminho, log=lambda m: progresso(f'    {m}'))
    else:
        from bim_pipeline.conversores import step_iges
        geo = step_iges.converter(caminho, deflexao)
    return {'pos': geo['pos'], 'col': geo.get('col') or [], 'idx': geo['idx']}, geo


# ─── Famílias → catálogo ─────────────────────────────────────────────────────

def _spec_valor(d):
    v = str(d.get('valor') or '').strip()
    if not v:
        return ''
    rot = type_catalog.rotulo_unidade(d.get('unidade'))
    if rot and not re.search(r'[a-zA-Z°%²³"\']', v):
        return f'{v} {rot}'
    return v


def _codigo(parametros):
    for nome in ('Model', 'Modelo', 'Código', 'Codigo', 'Code', 'Código comercial', 'Referência', 'Part Number'):
        d = parametros.get(nome)
        if d and str(d.get('valor') or '').strip():
            return str(d['valor']).strip()
    return None


_CHAVES_FABRICANTE = ('Manufacturer', 'Fabricante', 'Produtor', 'Manufacturer Name')


def _fabricante(familias, produtos=()):
    votos = {}
    for f in familias:
        for _t, params in f['tipos']:
            for nome in _CHAVES_FABRICANTE:
                v = str((params.get(nome) or {}).get('valor') or '').strip()
                if v:
                    votos[v] = votos.get(v, 0) + 1
    for p in produtos:
        for nome in _CHAVES_FABRICANTE:
            v = str((p.get('specs') or {}).get(nome) or '').strip()
            if v:
                votos[v] = votos.get(v, 0) + 1
    return max(votos, key=votos.get) if votos else None


# ─── Projetos .rvt → produtos (via IFC) ───────────────────────────────────────

def eh_auxiliar(fam, tipo):
    """
    True se o par (família, tipo) é uma peça auxiliar de montagem — não o produto principal.
    Regras: prefixo `x_` ou `x ` no nome da família ou do tipo (convenção Revit: componentes
    que não entram em schedules), ou família de segmento de tubo genérico (Pipe Types).
    """
    fam_l = (fam or '').lower().strip()
    tipo_l = (tipo or '').lower().strip()
    if fam_l.startswith(('x_', 'x ')) or tipo_l.startswith(('x_', 'x ')):
        return True
    if fam_l in ('pipe types', 'pipe segments'):
        return True
    return False


def ifc_do_projeto(proj, aps, trabalho, progresso=avisar):
    """
    O IFC de um projeto: o irmão de mesmo nome (grátis) ou, com `aps = {'cliente', 'cache'}`, a tradução pela
    APS gravada em `trabalho`. Devolve `(caminho_ifc, origem)` com origem ∈ {'irmao', 'aps', 'aps-cache'} ou
    `(None, motivo)`.
    """
    if proj.get('ifc'):
        return proj['ifc'], 'irmao'
    if not aps:
        return None, 'sem IFC irmão e sem a tradução pela Autodesk Platform Services autorizada — marque "usar a APS" ou exporte o IFC do projeto'
    from bim_pipeline.conversores import aps as aps_mod
    destino = os.path.join(trabalho, os.path.splitext(os.path.basename(proj['rvt']))[0] + '.aps.ifc')
    os.makedirs(trabalho, exist_ok=True)
    try:
        r = aps_mod.rvt_para_ifc(proj['rvt'], destino, aps['cliente'], aps.get('cache'), progresso)
    except SystemExit as e:
        return None, str(e)
    return destino, ('aps-cache' if r.get('cache') else 'aps')


def produtos_de_projeto(proj, caminho_ifc, origem, geo_dir, texto, progresso=avisar, filtrar_auxiliares=False):
    """
    Um projeto (via seu IFC) → `(produtos, series, n_geo, avisos, n_filtrados)`: um produto por tipo
    de família, geometria da primeira instância (local, na origem da família), specs dos psets do
    Revit + identidade do projeto. Com `filtrar_auxiliares=True`, peças com prefixo `x_`/`x ` ou
    categorias de segmento genérico (Pipe Types) são excluídas e contadas em `n_filtrados`.
    """
    from bim_pipeline.conversores import ifc_elementos
    nome_proj = os.path.splitext(os.path.basename(proj['rvt']))[0]
    slug_proj = slugify(nome_proj) or 'projeto'
    revit = None
    try:
        info, _png = rfa_partatom.ler(proj['rvt'])
        revit = info.get('revit')
    except Exception:
        pass
    grupos = ifc_elementos.por_tipo(ifc_elementos.elementos(caminho_ifc, progresso))
    progresso(f"  projeto {nome_proj}: {sum(g['instancias'] for g in grupos.values())} elemento(s), {len(grupos)} tipo(s) de família")
    fonte = {'irmao': f'IFC do projeto ({os.path.basename(caminho_ifc)})', 'aps': 'IFC do projeto traduzido pela Autodesk Platform Services',
             'aps-cache': 'IFC do projeto traduzido pela Autodesk Platform Services (cache)'}[origem]
    produtos, series, avisos = [], [], []
    n_geo = 0
    n_filtrados = 0
    for (fam, tipo), g in grupos.items():
        el = g['primeiro']
        if not fam and not tipo:
            avisos.append(f'{nome_proj}: elemento {el["guid"]} sem família/tipo — fora')
            continue
        if filtrar_auxiliares and eh_auxiliar(fam, tipo):
            n_filtrados += 1
            continue
        serie = texto(humanizar(fam or tipo))
        if serie not in series:
            series.append(serie)
        nome_geo = f'{slug_proj}--{slugify(fam) or "familia"}--{slugify(tipo) or "tipo"}.json'
        with open(os.path.join(geo_dir, nome_geo), 'w', encoding='utf-8') as f:
            json.dump(ifc_elementos.geo_do_viewer(el), f, separators=(',', ':'))
        n_geo += 1
        specs = {texto(k): texto(v) for k, v in ifc_elementos.specs_de(el).items()}
        specs['Família Revit'] = texto(humanizar(fam or tipo))
        specs['Tipo Revit'] = texto(tipo or fam)
        if specs.get('Category'):
            specs['Categoria Revit'] = specs.pop('Category')
        specs['Projeto Revit'] = texto(nome_proj)
        if revit:
            specs['Revit'] = revit
        specs['Instâncias no projeto'] = str(g['instancias'])
        specs['Fonte 3D'] = texto(fonte)
        specs['Geometria 3D'] = texto(f'geometria real do elemento no projeto ({len(el["faces"])} triângulos), na origem da família; '
                                      f'compartilhada pelas {g["instancias"]} instância(s) do tipo')
        pid = slugify(f'{nome_proj}-{fam}-{tipo}') or f'{slug_proj}-{len(produtos) + 1}'
        codigo = next((str(specs[k]).strip() for k in ('Model', 'Modelo', 'Código', 'Codigo', 'Code', 'Catalogue Code', 'Product Code',
                                                       'Article Number', 'Type Mark') if specs.get(k)), None)
        produtos.append({
            'id': pid, 'nome': texto(tipo or fam), 'serie': serie, 'geo': nome_geo, 'potencia': None,
            'conexoes': specs.get('Categoria Revit') or el['classe'], 'specs': specs, 'curva': None, 'codigo': codigo,
        })
    if filtrar_auxiliares and n_filtrados:
        avisos.append(f'{nome_proj}: {n_filtrados} tipo(s) auxiliar(es) filtrado(s) (prefixo x_, Pipe Types)')
    return produtos, series, n_geo, avisos, n_filtrados


def catalogo_de_familias(familias, geo_dir, titulo=None, fabricante=None, comprimento_mm=None, deflexao=0.2,
                         progresso=avisar, origem=None, projetos=(), aps=None, trabalho=None,
                         filtrar_auxiliares=False):
    """
    Famílias lidas (`ler_familia`) e projetos (`descobrir()['projetos']`) → o resultado do contrato `catalogo`,
    com um `<geo>.json` por geometria em `geo_dir`. Uma família com geometria irmã compartilha a geometria
    entre os tipos; sem ela, cada tipo recebe uma forma representativa (tipos com as mesmas cotas compartilham
    o mesmo JSON). Um projeto entra pelo IFC irmão ou pela APS (`aps = {'cliente', 'cache'}`), um produto por
    tipo de família do modelo.
    """
    os.makedirs(geo_dir, exist_ok=True)
    diag = diag_vazio()
    avisos = diag['avisos']
    produtos, series, ids = [], [], set()
    n_geo = 0
    n_irma = n_repr = n_sem = 0
    mudou_cp1252 = 0
    versoes = {}
    representativas = {}   # chave de forma → nome do arquivo de geometria
    proj_stats = {'projetos': len(projetos), 'traduzidos_aps': 0, 'do_cache': 0, 'ifc_irmao': 0, 'fora': 0, 'produtos': 0, 'filtrados_auxiliares': 0}

    def texto(s):
        nonlocal mudou_cp1252
        t, mudou = cp1252_seguro(s)
        mudou_cp1252 += int(mudou)
        return t

    trabalho_proprio = None
    if projetos and not trabalho:
        trabalho = trabalho_proprio = tempfile.mkdtemp(prefix='familias-revit-aps-')
    for proj in projetos:
        caminho_ifc, origem_ifc = ifc_do_projeto(proj, aps, trabalho, progresso)
        if not caminho_ifc:
            proj_stats['fora'] += 1
            avisos.append(f"{proj['rel']}: projeto Revit fora — {origem_ifc}")
            continue
        proj_stats[{'irmao': 'ifc_irmao', 'aps': 'traduzidos_aps', 'aps-cache': 'do_cache'}[origem_ifc]] += 1
        try:
            prods, sers, ng, avs, nf = produtos_de_projeto(proj, caminho_ifc, origem_ifc, geo_dir, texto, progresso, filtrar_auxiliares)
            proj_stats['filtrados_auxiliares'] += nf
        except ImportError:
            avisos.append(f"{proj['rel']}: ifcopenshell não instalado — o IFC do projeto não pôde ser lido")
            proj_stats['fora'] += 1
            continue
        except Exception as e:
            avisos.append(f"{proj['rel']}: IFC do projeto ilegível ({e})")
            proj_stats['fora'] += 1
            continue
        avisos.extend(avs)
        for p in prods:
            base_id, k = p['id'], 2
            while p['id'] in ids:
                p['id'], k = f'{base_id}-{k}', k + 1
            ids.add(p['id'])
        produtos.extend(prods)
        series.extend(s for s in sers if s not in series)
        n_geo += ng
        proj_stats['produtos'] += len(prods)
    if trabalho_proprio:
        shutil.rmtree(trabalho_proprio, ignore_errors=True)

    for fi, fam in enumerate(familias, start=1):
        avisos.extend(f"{fam['rel']}: {a}" for a in fam.get('avisos') or [])
        if fam.get('revit'):
            versoes[fam['revit']] = versoes.get(fam['revit'], 0) + 1
        slug_fam = slugify(fam['titulo']) or f'familia-{fi}'
        serie_base = texto(humanizar(fam['titulo']))
        cat = fam.get('categoria') or {}
        progresso(f"  família {fi}/{len(familias)} — {fam['titulo']} ({len(fam['tipos'])} tipo(s))")
        if not fam['tipos']:
            avisos.append(f"{fam['rel']}: sem tipos — nada a importar")
            continue

        geo_irma, info_irma = None, None
        if fam.get('geometria'):
            try:
                geo_irma, info_irma = geo_de_arquivo(fam['geometria'], deflexao, progresso)
                nome_geo = f'{slug_fam}.json'
                with open(os.path.join(geo_dir, nome_geo), 'w', encoding='utf-8') as f:
                    json.dump(geo_irma, f, separators=(',', ':'))
                n_geo += 1
                progresso(f"    geometria irmã {os.path.basename(fam['geometria'])}: {len(geo_irma['idx']) // 3} △")
            except BaseException as e:     # SystemExit dos conversores inclusive: cai na forma representativa
                if isinstance(e, KeyboardInterrupt):
                    raise
                avisos.append(f"{fam['rel']}: geometria irmã {os.path.basename(fam['geometria'])} não convertida ({e}) — forma representativa")
                geo_irma = None

        serie = serie_base if geo_irma else serie_base + SUFIXO_SERIE
        if serie not in series:
            series.append(serie)
        for titulo_tipo, params in fam['tipos']:
            material = _material(params)
            if geo_irma:
                nome_geo = f'{slug_fam}.json'
                fonte_3d = os.path.basename(fam['geometria'])
                geometria_3d = f"geometria do arquivo {fonte_3d} ({len(geo_irma['idx']) // 3} triângulos), compartilhada pelos tipos da família"
                n_irma += 1
            else:
                dims = dimensoes(params)
                forma = forma_representativa(dims, f"{fam['titulo']} {titulo_tipo}", cat.get('nome'), material, comprimento_mm)
                if not forma:
                    n_sem += 1
                    avisos.append(f"{fam['titulo']} / {titulo_tipo}: sem cota reconhecível ({', '.join(sorted(params)) or 'sem parâmetros'}) — fora")
                    continue
                nome_forma, malhas, regra = forma
                chave = (nome_forma, tuple(sorted((k, round(v, 3)) for k, v in dims.items() if isinstance(v, float))), _cor(material),
                         eh_vertical(f"{fam['titulo']} {titulo_tipo}", cat.get('nome')), bool(dims.get('capa')))
                nome_geo = representativas.get(chave)
                if not nome_geo:
                    nome_geo = f'{slug_fam}--{slugify(titulo_tipo) or len(representativas) + 1}.json'
                    with open(os.path.join(geo_dir, nome_geo), 'w', encoding='utf-8') as f:
                        json.dump(geo_do_viewer(malhas), f, separators=(',', ':'))
                    representativas[chave] = nome_geo
                    n_geo += 1
                fonte_3d = f'forma representativa ({nome_forma})'
                geometria_3d = f'{RESSALVA} Regra: {regra}.'
                n_repr += 1

            specs = {}
            for nome, d in params.items():
                v = _spec_valor(d)
                if v:
                    specs[texto(nome)] = texto(v)
            specs['Família Revit'] = texto(humanizar(fam['titulo']))
            specs['Tipo Revit'] = texto(titulo_tipo)
            if cat.get('nome'):
                specs['Categoria Revit'] = texto(cat['nome'])
            if cat.get('omniclass'):
                specs['OmniClass'] = cat['omniclass']
            if fam.get('revit'):
                specs['Revit'] = fam['revit']
            specs['Fonte 3D'] = texto(fonte_3d)
            specs['Geometria 3D'] = texto(geometria_3d)

            pid = slugify(f"{fam['titulo']}-{titulo_tipo}") or f'{slug_fam}-{len(produtos) + 1}'
            base_id, k = pid, 2
            while pid in ids:
                pid, k = f'{base_id}-{k}', k + 1
            ids.add(pid)
            produtos.append({
                'id': pid, 'nome': texto(titulo_tipo), 'serie': serie, 'geo': nome_geo, 'potencia': None,
                'conexoes': texto(cat.get('nome') or cat.get('omniclass') or fam.get('pasta') or ''),
                'specs': specs, 'curva': None, 'codigo': texto(_codigo(params) or '') or None,
            })

    fabricante = fabricante or _fabricante(familias, produtos) or 'Fabricante'
    titulo = titulo or 'Famílias Revit'
    config = {'slug': slugify(titulo) or 'familias-revit', 'titulo': texto(titulo), 'fabricante': texto(fabricante),
              'descricao': '', 'layout': 'catalog-grid'}
    if mudou_cp1252:
        avisos.append(f'{mudou_cp1252} texto(s) com caractere fora do cp1252 ajustado(s) para o .aq')
    hints = {'n_pecas': len(produtos), 'n_simbologias': n_geo, 'schema': 'familias-revit', 'grupos': list(series),
             'linhas': [titulo], 'has_curves': False,
             'origem': {**(origem or {}), 'familias': len(familias), 'tipos': sum(len(f['tipos']) for f in familias),
                        'com_geometria_irma': n_irma, 'representativas': n_repr, 'sem_cota': n_sem, 'revit': versoes,
                        'projetos': proj_stats}}
    return montar_resultado(config, montar_catalogo(config, produtos, series), n_geo, diag, hints)


# ─── Entrada (.rfa, pasta ou .zip) ───────────────────────────────────────────

def preparar(entrada, trabalho=None, progresso=avisar):
    """`(raiz, ignorados, temporario)` — extrai o `.zip` em `trabalho` (ou num tmp que quem chama apaga)."""
    if not os.path.exists(entrada):
        raise FamiliasRevitError(f'{entrada}: não existe')
    ext = os.path.splitext(entrada)[1].lower()
    if ext == '.zip':
        if not zipfile.is_zipfile(entrada):
            raise FamiliasRevitError(f'{os.path.basename(entrada)}: não é um ZIP')
        raiz = trabalho or tempfile.mkdtemp(prefix='familias-revit-')
        _ex, ignorados = extrair_zip(entrada, raiz, progresso)
        return raiz, ignorados, trabalho is None
    if os.path.isdir(entrada) or ext in EXT_RFA + EXT_PROJETO:
        return entrada, [], False
    raise FamiliasRevitError(f'{os.path.basename(entrada)}: envie um .rfa, um projeto .rvt, uma pasta ou um .zip com as famílias')


SEM_APS = ('as famílias embutidas num projeto não são legíveis fora do Revit — coloque o IFC do projeto ao lado '
           '(mesmo nome) ou autorize a tradução pela Autodesk Platform Services')


def inspecionar(entrada, trabalho=None, progresso=avisar):
    """O resumo de `familias_revit inspecionar` (contrato `info-familias-revit`): famílias, tipos, categorias, o que falta."""
    raiz, ignorados, temp = preparar(entrada, trabalho, progresso)
    try:
        d = descobrir(raiz)
        fams = []
        avisos = []
        for f in d['familias']:
            try:
                lf = ler_familia(f, progresso)
            except Exception as e:
                avisos.append(f"{f['rel']}: não li ({e})")
                continue
            avisos.extend(f"{f['rel']}: {a}" for a in lf['avisos'])
            fams.append({
                'arquivo': f['rel'], 'titulo': lf['titulo'], 'revit': lf['revit'], 'formato': lf['formato'],
                'categoria': lf['categoria'].get('nome') or lf['categoria'].get('omniclass'),
                'tipos': len(lf['tipos']), 'type_catalog': lf['type_catalog'],
                'geometria_irma': os.path.relpath(f['geometria'], raiz) if f.get('geometria') else None,
                'preview': lf['preview'],
                'fabricante': next((str((p.get('Manufacturer') or p.get('Fabricante') or {}).get('valor') or '') for _t, p in lf['tipos']
                                    if (p.get('Manufacturer') or p.get('Fabricante'))), None) or None,
            })
        projetos = []
        for p in d['projetos']:
            revit = formato = None
            try:
                info, _png = rfa_partatom.ler(p['rvt'])
                revit, formato = info.get('revit'), info.get('formato')
            except Exception as e:
                avisos.append(f"{p['rel']}: não li o BasicFileInfo ({e})")
            projetos.append({'arquivo': p['rel'], 'revit': revit, 'formato': formato, 'bytes': os.path.getsize(p['rvt']),
                             'ifc_irmao': os.path.relpath(p['ifc'], raiz) if p.get('ifc') else None})
            if not p.get('ifc'):
                avisos.append(f"{p['rel']}: projeto Revit — {SEM_APS}")
        return {
            'entrada': os.path.basename(entrada), 'bytes': _tamanho(entrada), 'familias': fams,
            'n_familias': len(fams), 'n_tipos': sum(f['tipos'] for f in fams),
            'com_geometria_irma': sum(1 for f in fams if f['geometria_irma']),
            'projetos': projetos, 'n_projetos': len(projetos), 'projetos_sem_ifc': sum(1 for p in projetos if not p['ifc_irmao']),
            'ignorados': len(ignorados), 'avisos': avisos,
        }
    finally:
        if temp:
            shutil.rmtree(raiz, ignore_errors=True)


def _tamanho(caminho):
    if os.path.isdir(caminho):
        return sum(os.path.getsize(os.path.join(dp, n)) for dp, _d, ns in os.walk(caminho) for n in ns)
    return os.path.getsize(caminho)


def cliente_aps(credenciais_json=None, usar_env=False):
    """`ClienteAPS` a partir do JSON ou do ambiente, ou None quando a APS não foi autorizada."""
    if not credenciais_json and not usar_env:
        return None
    from bim_pipeline.conversores import aps as aps_mod
    cid, sec = aps_mod.credenciais(credenciais_json)
    return aps_mod.ClienteAPS(cid, sec)


def importar(entrada, geo_dir, titulo=None, fabricante=None, comprimento_mm=None, deflexao=0.2, trabalho=None, progresso=avisar,
             aps=None, filtrar_auxiliares=False):
    """`aps = {'cliente': ClienteAPS, 'cache': dir|None}` autoriza traduzir projetos .rvt pela APS; None = projetos só com IFC irmão."""
    raiz, ignorados, temp = preparar(entrada, trabalho, progresso)
    trabalho_aps = tempfile.mkdtemp(prefix='familias-revit-ifc-')
    try:
        d = descobrir(raiz)
        traduziveis = [p for p in d['projetos'] if p.get('ifc') or aps]
        if not d['familias'] and not traduziveis:
            extra = f' — {len(d["projetos"])} projeto(s) .rvt: {SEM_APS}' if d['projetos'] else ''
            raise FamiliasRevitError(f'{os.path.basename(entrada)}: nenhuma família .rfa encontrada{extra}')
        progresso(f"{len(d['familias'])} família(s) e {len(d['projetos'])} projeto(s) em {os.path.basename(entrada)}")
        familias, avisos_leitura = [], []
        for f in d['familias']:
            try:
                familias.append(ler_familia(f, progresso))
            except Exception as e:
                avisos_leitura.append(f"{f['rel']}: não li ({e})")
        if d['familias'] and not familias and not traduziveis:
            raise FamiliasRevitError(f'{os.path.basename(entrada)}: nenhuma família legível — {"; ".join(avisos_leitura)[:500]}')
        titulo = titulo or (os.path.splitext(os.path.basename(entrada))[0] if not os.path.isdir(entrada) else os.path.basename(entrada.rstrip('/')))
        r = catalogo_de_familias(familias, geo_dir, titulo, fabricante, comprimento_mm, deflexao, progresso,
                                 origem={'entrada': os.path.basename(entrada), 'bytes': _tamanho(entrada), 'ignorados': len(ignorados)},
                                 projetos=d['projetos'], aps=aps, trabalho=trabalho_aps, filtrar_auxiliares=filtrar_auxiliares)
        r['diag']['avisos'] = avisos_leitura + r['diag']['avisos']
        return r
    finally:
        shutil.rmtree(trabalho_aps, ignore_errors=True)
        if temp:
            shutil.rmtree(raiz, ignore_errors=True)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    i = sub.add_parser('inspecionar', help='.rfa, pasta ou .zip → famílias, tipos, categorias (JSON no stdout)')
    i.add_argument('entrada')
    i.add_argument('--trabalho', help='pasta onde extrair o .zip (padrão: temporária, apagada ao fim)')
    m = sub.add_parser('importar', help='.rfa, pasta ou .zip → catálogo (JSON em --saida) + geometrias em --geo-dir')
    m.add_argument('entrada')
    m.add_argument('--geo-dir', required=True)
    m.add_argument('--saida', required=True)
    m.add_argument('--titulo', help='título do catálogo (padrão: nome do arquivo/pasta)')
    m.add_argument('--fabricante', help='fabricante (padrão: o parâmetro Manufacturer mais frequente)')
    m.add_argument('--comprimento-mm', type=float, default=None, help=f'trecho das formas representativas (padrão {PROPORCOES["comprimento_perfil_mm"]:.0f})')
    m.add_argument('--deflexao', type=float, default=0.2, help='deflexão da tesselação da geometria irmã STEP/IGES, em mm')
    m.add_argument('--trabalho', help='pasta onde extrair o .zip (padrão: temporária, apagada ao fim)')
    m.add_argument('--aps', action='store_true', help='traduzir projetos .rvt pela APS com APS_CLIENT_ID/APS_CLIENT_SECRET do ambiente (cobrado)')
    m.add_argument('--aps-credenciais', help='JSON {client_id, client_secret} — o mesmo que --aps, com as credenciais em arquivo')
    m.add_argument('--aps-cache', help='pasta de cache dos IFC traduzidos, por SHA-256 do .rvt (o mesmo projeto não paga duas vezes)')
    m.add_argument('--filtrar-auxiliares', action='store_true',
                   help='excluir peças auxiliares de projetos .rvt: famílias/tipos com prefixo x_ ou x  e segmentos de tubo genérico (Pipe Types)')
    m.add_argument('--sair-com-stdin', action='store_true', help='termina com 2 quando o processo pai fecha o stdin')
    args = ap.parse_args()

    if args.cmd == 'inspecionar':
        print(json.dumps(inspecionar(args.entrada, args.trabalho), ensure_ascii=False))
        return

    if args.sair_com_stdin:
        from bim_pipeline.processo import vigiar_stdin
        vigiar_stdin()
    cli = cliente_aps(args.aps_credenciais, args.aps)
    aps = {'cliente': cli, 'cache': args.aps_cache} if cli else None
    r = importar(args.entrada, os.path.abspath(args.geo_dir), args.titulo, args.fabricante, args.comprimento_mm,
                 args.deflexao, args.trabalho, aps=aps, filtrar_auxiliares=args.filtrar_auxiliares)
    with open(args.saida, 'w', encoding='utf-8') as f:
        json.dump(r, f, ensure_ascii=False)
    o = r['hints']['origem']
    pj = o['projetos']
    avisar(f"pronto — {r['hints']['n_pecas']} peça(s) de {o['familias']} família(s) e {pj['projetos']} projeto(s), {r['n_geometrias']} geometria(s) "
           f"({o['com_geometria_irma']} de arquivo irmão, {o['representativas']} representativas, {o['sem_cota']} sem cota; "
           f"projetos: {pj['produtos']} peça(s), {pj['traduzidos_aps']} traduzido(s) na APS, {pj['do_cache']} do cache, {pj['fora']} fora) → {args.saida}")


if __name__ == '__main__':
    main()
