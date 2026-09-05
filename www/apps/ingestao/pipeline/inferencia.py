"""
inferencia.py — fabricante, título, slug e layout de um catálogo a partir do `.aq`
e do caminho do arquivo, sem perguntar nada. (Era parte de `scripts/build.py`; movido
para o serviço de ingestão em 2026-09-05, etapa E2.)

O pipeline estático usa `auto_config()` no modo `--all` e `peek_aq()` no modo
interativo; o serviço de ingestão usa `auto_config()` para todo upload.
"""
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

from catalogo import slugify, tokenize   # noqa: E402

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


# Pastas cujo nome não descreve o catálogo — não servem de título. As de saída
# entraram em 2026-09-02: um .aq em `eng-reversa/saida/` publicava com o título
# "Saida", e a validação não acusava, porque "Saida" de fato é diferente do
# fabricante. As de upload entraram em 2026-09-05: o serviço recebe o arquivo em
# `/tmp` com nome `bim-<uuid>.aq`, então o caminho não diz nada — use `nome_original`.
_GENERIC_DIRS = {'input', 'biblioteca', 'bibliotecas', 'bim', 'ifc', 'aq',
                 'downloads', 'arquivos', 'temp', 'tmp', '.', '',
                 'saida', 'output', 'out', 'dist', 'build', 'uploads', 'upload'}


def peek_aq(aq_path, nome_original=None):
    """
    Lê o .aq para extrair fabricante, título e pistas de layout.

    Fabricante e título NUNCA podem sair em branco ou em forma de slug: são o
    cabeçalho da página publicada. A cascata abaixo sempre produz algo legível.

    `nome_original` é o nome que o usuário deu ao arquivo quando ele chega por
    upload com nome temporário (`bim-<uuid>.aq`); sem ele, usa-se o do caminho.

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
    fn_tokens = _tokens_from_aq_filename(nome_original or aq_path)

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


def find_aq_paths(input_dir):
    """Caminhos absolutos de todos os .aq em input_dir (busca recursiva, ordem estável).
    Pasta inexistente → lista vazia."""
    aq_paths = []
    for root, dirs, files in os.walk(input_dir):
        dirs.sort()
        for f in sorted(files):
            if f.lower().endswith('.aq'):
                aq_paths.append(os.path.join(root, f))
    return aq_paths


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


def layout_para(hints):
    """Curvas Q-H → linhas por série; muitos itens sem curva → grade com filtros."""
    n = hints.get('n_pecas') or 0
    return ('series-rows' if hints.get('has_curves')
            else ('catalog-grid' if n > 6 else 'series-rows'))


def auto_config(aq_path, nome_original=None):
    """Config inferido do .aq sem perguntar nada — modo --all do build e todo upload do serviço."""
    hints = peek_aq(aq_path, nome_original)
    titulo = hints['titulo']
    fabricante = hints['fabricante']

    return {
        'slug': slugify(titulo or fabricante or 'catalogo'),
        'titulo': titulo,
        'fabricante': fabricante,
        'descricao': '',
        'layout': layout_para(hints),
        'aq_file': aq_path,
    }, hints
