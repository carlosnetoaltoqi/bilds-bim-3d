#!/usr/bin/env python3
"""
gerar_aq.py — gera uma biblioteca `.aq` do AltoQi Builder a partir do catálogo
da Akato extraído do PDF.

É o caminho inverso do `scripts/read_aq.py` do projeto: em vez de ler um `.aq`
de fabricante, escreve um.

O QUE ENTRA NO ARQUIVO
----------------------
Só o que o PDF de fato diz. Nada é preenchido por estimativa:

  VERSAO_BANCO_CADASTRO            versão do schema, idioma
  CLASSE_PECA                      uma por linha de produto da Akato
  GRUPO_PECA                       uma por família (87)
  PECA                             uma por produto (269)
  DADOS_HIDRAULICOS                uma por peça
  PROPRIEDADE_PERSONALIZADA        código Akato, embalagem, caixa master,
  VALOR_PROPRIEDADE_PERSONALIZADA  norma, pressão de serviço, cor, temperatura
  CLASSE_ITEM / GRUPO_ITEM /       o insumo de orçamento, com o código
  ITEM / ITEM_ASSOCIADO            comercial em `ITEM.CODIGO_ITEM`

O QUE FICA DE FORA, E POR QUÊ
-----------------------------
**Geometria 3D.** O PDF é um catálogo comercial: traz código, descrição
dimensional e embalagem, e nenhuma cota de forma. Sem as cotas não há malha, e
inventá-las produziria um sólido que não é o produto da Akato. Ficar sem
geometria não é um defeito do arquivo: 312 das 1.168 peças da Amanco (27%)
também não têm linha em `PECA_SIMBOLOGIA_3D` — são as peças sem forma fixa, que
o AltoQi gera parametricamente. Com `--geometria-demo` saem malhas
paramétricas para as famílias de tubo, e só para elas; é uma demonstração do
caminho da geometria, rotulada como tal, com espessura de parede vinda da norma
e não do catálogo.

**`ENTRADA_PECA` e comprimentos equivalentes.** A Amanco preenche
`COMPRIMENTO_EP` peça por peça com o comprimento equivalente de perda de carga,
que vem da tabela técnica do fabricante. O catálogo da Akato não traz esses
valores. Uma `ENTRADA_PECA` sem comprimento equivalente serviria de nada e uma
com valor estimado corromperia o dimensionamento hidráulico de quem usasse a
biblioteca.

**`DIAMETRO_PECA` na maioria das peças.** Ver `CODIGO_DIAMETRO` abaixo.

Uso:
    python3 gerar_aq.py <catalogo.json> <saida.aq> [--modelo <ref.aq>]
                        [--schema <schema.sql>] [--geometria-demo]
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import oq3d_writer  # noqa: E402  o escritor OQ3D deste estudo

# --- Constantes do AltoQi, todas observadas em bibliotecas reais ----------

VERSAO_SCHEMA = 607          # a mais nova entre as 12 bibliotecas disponíveis
MODO_GRAVACAO = 2
TAG_IDIOMA = 'pt-BR'

# Sentinelas de "não definido". O AltoQi não usa NULL para isso.
SENT_INT = -2147483647
SENT_REAL = -1.7976931348623157e+308     # -DBL_MAX

# PROJETO_APLICACAO — tipo de instalação do grupo. Valores observados:
#   8  esgoto        (Amanco, PVC esgoto)
#   12 água fria     (Komeco, bombas e pressurizadores)
#   22 incêndio      (Dancor, bombas de combate a incêndio)
#   36 gás           (Komeco, aquecedor de passagem a gás)
#   64, 76 elétrico  (Maxbar, barramento blindado)
APLICACAO_ESGOTO = 8
APLICACAO_AGUA_FRIA = 12

# Hazen-Williams C e Manning do PVC, como a Amanco grava para PVC.
RUGOSIDADE_PVC = 135.0
RUGOSIDADE_EQUIV_PVC = 6e-05
MANNING_PVC = 0.01
TIPO_FWH_PVC = 1

# ENTIDADE_IFC / SUBTIPO_IFC / TIPO_ENTIDADE_IFC / ENTIDADE_IFC_2X3.
# Os quatro andam juntos; estas combinações vêm todas da Amanco (schema 595) e
# da Dancor (607), correlacionando `GRUPO_PECA.NOME_GP` com os códigos.
IFC_CONEXAO = (2071, 4099, 2088)      # IfcPipeFitting
IFC_TUBO = (2072, 4096, 2086)         # IfcPipeSegment
IFC_APARELHO = (2076, 4122, 2092)     # aparelho sanitário
IFC_VALVULA = (2084, 4103, 2091)      # válvula
IFC_TERMINAL = (2085, 4123, 2092)     # ralo, caixa sifonada

# SUBTIPO_IFC dentro de IfcPipeFitting, pelos grupos da Amanco:
#   0 curva/joelho   1 luva      3 cap      4 tê/junção     6 redução
SUB_CURVA, SUB_LUVA, SUB_CAP, SUB_TE, SUB_REDUCAO = 0, 1, 3, 4, 6
SUB_TUBO = 3                          # único observado em IfcPipeSegment

# TIPO_APLICACAO_PECA, da Amanco:
#   1 tubo   2 conexão   8 aparelho sanitário   9 caixa sifonada/ralo com
#   grelha   10 ralo   55 ramal de ventilação        (6 = bomba, na Dancor)
APL_TUBO, APL_CONEXAO, APL_APARELHO, APL_CAIXA, APL_RALO = 1, 2, 8, 9, 10

# DADOS_HIDRAULICOS.TIPO_CURVA — 2 em todas as conexões da Amanco.
TIPO_CURVA_CONEXAO = 2

# GRUPO_ITEM.UNIDADE_GI — 1 nos três grupos de tubo da Amanco, 0 no resto.
# ITEM_ASSOCIADO.MEDICAO_PECA — 1 nas peças de tubo, 2 nas conexões.
UNIDADE_METRO, UNIDADE_PECA = 1, 0
MEDICAO_TUBO, MEDICAO_CONEXAO = 1, 2

# CODIGO_DIAMETRO — o código que o AltoQi usa em `PECA.DIAMETRO_PECA` e
# `ENTRADA_PECA.DIAMETRO_EP`. NÃO é o diâmetro em centímetro, como a versão
# 2.2.0 da skill `leitor-biblioteca-aq` diz: na Amanco a peça `50 mm - 2"` tem
# `DIAMETRO_PECA = 9`, e a `100 mm - 4"` tem 12.
#
# Só estes seis pares foram observados. Na Amanco, 112 das 1.168 peças trazem código
# (48 de tubo, 52 de caixa sifonada e afins, 12 de ralo), 963 trazem a sentinela
# -DBL_MAX e 93 trazem zero; nenhuma das 700 conexões traz código. A Dancor usa os códigos
# 7 a 11 nos bocais das bombas, cujas sucções e recalques vão de 1.1/4" a 3" —
# consistente com a mesma escala, e é de onde vem o 10.
#
# Os códigos das bitolas de água fria abaixo de 40 mm (20, 25, 32) NÃO
# aparecem em nenhuma das 12 bibliotecas. Ficam fora: uma peça sem código de
# diâmetro usa a sentinela, exatamente como as conexões da Amanco.
CODIGO_DIAMETRO = {40: 8, 50: 9, 60: 10, 75: 11, 100: 12, 150: 14, 200: 15}

FABRICANTE = 'Akato'
TABELA_REFERENCIA = 'Akato — Catálogo Construção Civil, versão 01.2026'


# --- Classificação das famílias ------------------------------------------

def _sem_acento(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn').upper()


# (palavras-chave no título, entidade IFC, subtipo, tipo de aplicação, forma).
# A ordem importa: a primeira regra que casar vence, então as mais específicas
# vêm antes.
#
# As chaves casam por PALAVRA INTEIRA, via `\b`. Uma versão anterior usava
# substring e a chave `TE` do tê casava com INTERNO, EXTERNA, EXTENSÍVEL e
# ENGATE — nove famílias saíam com o subtipo IFC de tê: ADAPTADOR INTERNO,
# UNIÃO INTERNA, SIFÃO EXTENSÍVEL, ENGATE FLEXÍVEL e as suas variantes. Como
# `TE` é a forma sem acento de `TÊ`, a chave é curta por necessidade, e sem
# fronteira de palavra ela pega meio catálogo.
REGRAS_TIPO = [
    (('TUBO',),                       IFC_TUBO,     SUB_TUBO,    APL_TUBO,     'tubo'),
    (('CAIXA SIFONADA',),             IFC_TERMINAL, 1,           APL_CAIXA,    'caixa_sifonada'),
    (('RALO',),                       IFC_TERMINAL, 0,           APL_RALO,     'ralo'),
    (('GRELHA',),                     IFC_TERMINAL, 0,           APL_RALO,     'grelha'),
    (('VALVULA DE RETENCAO',),        IFC_VALVULA,  22,          APL_CONEXAO,  'valvula_retencao'),
    (('REGISTRO',),                   IFC_VALVULA,  22,          APL_CONEXAO,  'registro'),
    (('TORNEIRA', 'BOIA'),            IFC_VALVULA,  22,          APL_CONEXAO,  'torneira_boia'),
    (('SIFAO',),                      IFC_APARELHO, 3,           APL_APARELHO, 'sifao'),
    (('ENGATE',),                     IFC_CONEXAO,  SUB_LUVA,    APL_CONEXAO,  'engate'),
    (('KIT',),                        IFC_APARELHO, 3,           APL_APARELHO, 'chuveiro'),
    (('TRANSPOSICAO',),               IFC_CONEXAO,  SUB_CURVA,   APL_CONEXAO,  'transposicao'),
    (('CURVA', 'JOELHO'),             IFC_CONEXAO,  SUB_CURVA,   APL_CONEXAO,  'joelho'),
    (('JUNCAO',),                     IFC_CONEXAO,  SUB_TE,      APL_CONEXAO,  'juncao'),
    (('TE',),                         IFC_CONEXAO,  SUB_TE,      APL_CONEXAO,  'te'),
    (('CAP',),                        IFC_CONEXAO,  SUB_CAP,     APL_CONEXAO,  'cap'),
    (('PLUG', 'ESPUDE'),              IFC_CONEXAO,  SUB_CAP,     APL_CONEXAO,  'plug'),
    (('ANEL',),                       IFC_CONEXAO,  SUB_LUVA,    APL_CONEXAO,  'anel'),
    (('BUCHA DE REDUCAO', 'REDUCAO',
      'ADAPTADOR'),                   IFC_CONEXAO,  SUB_REDUCAO, APL_CONEXAO,  'reducao'),
    (('NIPEL',),                      IFC_CONEXAO,  SUB_LUVA,    APL_CONEXAO,  'nipel'),
    (('LUVA', 'UNIAO'),               IFC_CONEXAO,  SUB_LUVA,    APL_CONEXAO,  'luva'),
    (('VALVULA', 'UNHO', 'TAMPA'),    IFC_APARELHO, 3,           APL_APARELHO, 'valvula_pia'),
]

# Famílias que não são peça de instalação nenhuma — material de consumo. Vão
# para o arquivo como insumo de orçamento, sem grupo de peça: um adesivo não é
# uma conexão e lançá-lo como tal poluiria a paleta do projetista.
SO_INSUMO = ('ADESIVO', 'FITA VEDA')


def classificar(titulo):
    """
    (entidade_ifc, subtipo, tipo_aplicacao, forma) ou None se é só insumo.

    `forma` é a chave do gerador paramétrico em `formas.py`.
    """
    alvo = _sem_acento(titulo)
    if any(k in alvo for k in SO_INSUMO):
        return None
    for chaves, ifc, sub, apl, forma in REGRAS_TIPO:
        if any(re.search(rf'\b{re.escape(k)}\b', alvo) for k in chaves):
            return ifc, sub, apl, forma
    # Sem regra: entra como conexão genérica, o caso mais comum e o mais
    # inofensivo — a peça aparece na paleta de conexões hidráulicas.
    return IFC_CONEXAO, SUB_LUVA, APL_CONEXAO, 'luva'


# --- Dimensões a partir da descrição -------------------------------------

RE_MM = re.compile(r'(\d+)\s*mm\b')
RE_DN = re.compile(r'\bDN\s*(\d+)')
RE_POL = re.compile(r'(\d+(?:\.\d+)?(?:/\d+)?)\s*["”]')
RE_CM = re.compile(r'(\d+(?:,\d+)?)\s*cm\b')
RE_METRO = re.compile(r'(\d+(?:,\d+)?)\s*m\b')
RE_GRAMA = re.compile(r'(\d+)\s*g\b')


# Diâmetro externo suposto quando a descrição não traz nenhum — acontece nos
# sifões, descritos só pelo comprimento ("62cm", "1,12m", "80cm"). 40 mm é a
# bitola de saída de lavatório da NBR 5688, que é onde o sifão liga.
PADRAO_SEM_DIAMETRO = {'sifao': 40}

RE_METROS_TITULO = re.compile(r'\b(\d+)\s*M\b')


def comprimento_do_titulo(titulo):
    """
    Comprimento em centímetros anunciado no TÍTULO da família, ou None.

    As duas famílias de tubo se chamam `TUBO DE PVC SOLDÁVEL 6M` e `TUBO DE
    PVC ESGOTO SÉRIE NORMAL 6M`: o comprimento da barra está no título, não na
    descrição da peça — que traz só a bitola. É dado do catálogo, e sem lê-lo
    daqui o gerador teria de assumir 6 m por omissão.
    """
    m = RE_METROS_TITULO.search(_sem_acento(titulo))
    return float(m.group(1)) * 100 if m else None


def diametros_mm(descricao, secao, conversao, forma=None):
    """
    (de1, de2) em milímetro, a partir da descrição do catálogo.

    `de1` é o diâmetro principal e `de2` o secundário, ou None. As descrições
    aparecem em quatro formatos, e todos precisam virar milímetro:

      '25 x 20mm'          → (25, 20)     dois em milímetro
      'DN 100 x 50'        → (100, 50)    dois, o DN vale para os dois
      'DN 100 x 100 x 50'  → (100, 50)    corpo e saída da caixa sifonada
      '20mm x 1/2"'        → (20, 20)     milímetro e polegada
      '3/4" x 1/2"'        → (25, 20)     dois em polegada
      '62cm'               → (40, None)   nenhum: cai no padrão da forma

    A polegada é convertida pela **tabela do próprio catálogo** (página 23),
    coluna PVC soldável. O 3/8" e o 7/8" não estão nela e vêm de
    `POLEGADA_EXTRA`.
    """
    import formas as _f

    d = dimensoes(descricao)
    mm = d['mm']
    if mm:
        # O último número é o secundário: em `DN 100 x 100 x 50` o 50 é a
        # saída, não o segundo 100.
        de1 = mm[0]
        de2 = mm[-1] if len(mm) > 1 else None
        if d['pol'] and de2 is None:
            de2 = _polegada_mm(d['pol'][-1], conversao)
        return de1, de2

    if d['pol']:
        de1 = _polegada_mm(d['pol'][0], conversao)
        de2 = (_polegada_mm(d['pol'][-1], conversao)
               if len(d['pol']) > 1 else None)
        return de1, de2

    padrao = PADRAO_SEM_DIAMETRO.get(forma)
    return padrao, None


def _polegada_mm(pol, conversao):
    """Polegada → milímetro pela tabela do catálogo, com as duas extensões."""
    import formas as _f
    chave = f'{pol}"'
    linha = conversao.get(chave)
    if linha and linha.get('pvc_soldavel_mm'):
        return linha['pvc_soldavel_mm']
    return _f.POLEGADA_EXTRA.get(pol)


def dimensoes(descricao):
    """
    O que a descrição do catálogo diz, em campos separados.

    `'50 x 25mm'` → mm [50, 25];  `'20mm x 1/2"'` → mm [20], pol ['1/2'];
    `'DN 100 x 50'` → mm [100, 50];  `'1/2" | 30cm'` → pol ['1/2'],
    comprimento 30 cm.

    O `x` de `50 x 25mm` distribui a unidade: os dois números são milímetros,
    mesmo o primeiro, que não vem seguido de `mm`.
    """
    d = {'mm': [], 'pol': [], 'comprimento_cm': None, 'massa_g': None}

    dns = [int(x) for x in RE_DN.findall(descricao)]
    if dns:
        # `DN 100 x 50`: o DN vale para todos os números da expressão.
        d['mm'] = [int(x) for x in re.findall(r'\d+', descricao)]
    else:
        mm = [int(x) for x in RE_MM.findall(descricao)]
        if mm:
            # `50 x 25mm`: pega os números antes do primeiro `mm` também.
            antes = descricao[:descricao.lower().index('mm')]
            d['mm'] = [int(x) for x in re.findall(r'\d+', antes)]

    d['pol'] = RE_POL.findall(descricao)

    cm = RE_CM.search(descricao)
    if cm:
        d['comprimento_cm'] = float(cm.group(1).replace(',', '.'))
    else:
        m = RE_METRO.search(descricao)
        if m:
            d['comprimento_cm'] = float(m.group(1).replace(',', '.')) * 100
    g = RE_GRAMA.search(descricao)
    if g:
        d['massa_g'] = int(g.group(1))
    return d


# --- Propriedades por linha de produto -----------------------------------
#
# Todas vêm do texto das páginas de abertura de linha do próprio PDF: a NBR e a
# pressão de serviço na página 5 (água fria), a NBR e a temperatura na página 12
# (esgoto). A cor sai da frase "utiliza a cor marrom nos produtos tradicionais e
# a cor azul nas conexões com bucha de latão".

def propriedades_da_familia(familia):
    """{nome: valor} — o que o PDF afirma sobre a linha desta família."""
    secao = familia['secao']
    titulo = _sem_acento(familia['titulo'])
    props = {}
    if secao == 'ÁGUA FRIA':
        props['Norma'] = 'NBR 5648'
        props['Pressão de serviço'] = 'até 7,5 kgf/cm²'
        if 'BUCHA DE LATAO' in titulo or 'SBL' in titulo:
            props['Cor'] = 'azul'
        elif 'ROSCAVEL' in titulo:
            props['Cor'] = 'branca'
        else:
            props['Cor'] = 'marrom'
        props['Tipo de junta'] = ('roscável' if 'ROSCAVEL' in titulo
                                  else 'soldável')
    elif secao == 'ESGOTO':
        props['Norma'] = 'NBR 5688'
        props['Cor'] = 'branca'
        props['Temperatura máxima de operação'] = (
            '45 °C em regime não contínuo')
    return props


def linha_de_produto(familia):
    """A linha comercial da família, para virar uma CLASSE_PECA."""
    titulo = _sem_acento(familia['titulo'])
    if familia['secao'] == 'ÁGUA FRIA':
        return ('PVC Água Fria Roscável' if 'ROSCAVEL' in titulo
                else 'PVC Água Fria Soldável')
    if familia['secao'] == 'ESGOTO':
        return 'PVC Esgoto Série Normal'
    if familia['secao'] == 'ACESSÓRIOS':
        return 'Acessórios'
    return 'Polietileno'


# --- Escrita do banco -----------------------------------------------------

def criar_schema(destino, schema_sql=None, modelo=None):
    """
    Cria o `.aq` vazio com o schema completo do AltoQi.

    O DDL vem de `schema_sql` (o arquivo versionado em
    `eng-reversa/dados/schema-aq-607.sql`) ou, se não houver, é lido do
    `sqlite_master` de um `.aq` real. Nunca é escrito à mão: são 77 tabelas e
    84 índices, e uma coluna faltando faz o AltoQi recusar o arquivo.
    """
    if os.path.exists(destino):
        os.remove(destino)
    con = sqlite3.connect(destino)
    if schema_sql and os.path.exists(schema_sql):
        with open(schema_sql, encoding='utf-8') as f:
            con.executescript(f.read())
        origem = schema_sql
    elif modelo:
        ref = sqlite3.connect(f'file:{modelo}?mode=ro', uri=True)
        for (sql,) in ref.execute(
                'SELECT sql FROM sqlite_master '
                "WHERE sql IS NOT NULL AND type IN ('table','index')"):
            con.execute(sql)
        ref.close()
        origem = modelo
    else:
        raise SystemExit('preciso de --schema ou --modelo para o DDL')
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM sqlite_master "
                    "WHERE type='table'").fetchone()[0]
    print(f'  schema: {n} tabelas, de {os.path.basename(origem)}')
    return con


class Gerador:
    def __init__(self, con, catalogo):
        self.con = con
        self.cat = catalogo
        self.ids = {}          # tabela -> último id usado

    def novo(self, tabela):
        self.ids[tabela] = self.ids.get(tabela, 0) + 1
        return self.ids[tabela]

    def ins(self, tabela, **campos):
        """
        INSERT com o texto gravado em cp1252, como o AltoQi faz.

        ISTO É O CONTRÁRIO DO ÓBVIO E ERRAR AQUI CORROMPE TODO O ARQUIVO EM
        SILÊNCIO. O `.aq` declara `PRAGMA encoding = UTF-8`, mas o AltoQi
        Builder — aplicação Windows — grava **bytes cp1252** nas colunas de
        texto. Numa biblioteca real:

            SELECT NOME_CP FROM CLASSE_PECA
            → b'Bomba de Combate a Inc\\xeancio - Dancor'

        `\\xea` é `ê` em cp1252 e não é UTF-8 válido. O `typeof()` continua
        `'text'`: o SQLite não valida a codificação do que se manda gravar.

        O `scripts/read_aq.py` do projeto lê com `text_factory` cp1252. Então
        gravar em UTF-8, que é o padrão do módulo `sqlite3`, produz mojibake na
        leitura — `'Tubo De Pvc Soldável 6M'` virou `'Tubo De Pvc SoldÃ¡vel
        6M'`, e o erro não levanta exceção em lugar nenhum: aparece no nome do
        produto na página publicada, que é exatamente o bug de produção de
        2026-08-28, agora do lado de quem escreve.

        `CAST(? AS TEXT)` sobre um parâmetro `bytes` grava os bytes crus e
        mantém o valor tipado como texto — o mesmo resultado do AltoQi.
        """
        cols, marks, valores = [], [], []
        for chave, valor in campos.items():
            cols.append(f'"{chave}"')
            if isinstance(valor, str):
                marks.append('CAST(? AS TEXT)')
                valores.append(self.cp1252(valor, f'{tabela}.{chave}'))
            else:
                marks.append('?')
                valores.append(valor)
        self.con.execute(
            f'INSERT INTO "{tabela}" ({", ".join(cols)}) '
            f'VALUES ({", ".join(marks)})', valores)

    @staticmethod
    def cp1252(texto, onde):
        """
        Texto → bytes cp1252, falando alto se algum caractere não couber.

        O cp1252 tem 256 posições e o catálogo usa `°`, `º`, `²`, `´` e `’`,
        todos representáveis. Um caractere fora da tabela — um `–` de outra
        fonte, um `→` — não pode virar `?` em silêncio: entraria no nome do
        produto e ninguém veria.
        """
        try:
            return texto.encode('cp1252')
        except UnicodeEncodeError as e:
            raise SystemExit(
                f'{onde}: {texto!r} tem caractere fora do cp1252 '
                f'na posição {e.start} ({texto[e.start]!r}). '
                f'O .aq não representa esse caractere — troque-o na origem.')

    # -- cabeçalho --------------------------------------------------------

    def versao(self):
        self.ins('VERSAO_BANCO_CADASTRO',
                 VERSAO=VERSAO_SCHEMA, VERSAO_CONTEUDO_CADASTRO_ELLO=0,
                 MODO_GRAVACAO=MODO_GRAVACAO, TRADUCAO_HABILITADA=0,
                 TAG_IDIOMA=TAG_IDIOMA)

    # -- peças ------------------------------------------------------------

    def gerar(self, com_geometria=False):
        self.versao()

        classes_peca = {}      # linha de produto -> ID_CLASSE_PECA
        classes_item = {}
        props = {}             # nome da propriedade -> ID
        id_grupo_prop = self.novo('GRUPO_PROPRIEDADE_PERSONALIZADA')
        self.ins('GRUPO_PROPRIEDADE_PERSONALIZADA',
                 ID_GRUPO_PROPRIEDADE_PERSONALIZADA=id_grupo_prop,
                 NOME=f'{FABRICANTE}: Construção Civil')

        def id_propriedade(nome):
            if nome not in props:
                props[nome] = self.novo('PROPRIEDADE_PERSONALIZADA')
                self.ins('PROPRIEDADE_PERSONALIZADA',
                         ID_PROPRIEDADE_PERSONALIZADA=props[nome],
                         ID_GRUPO_PROPRIEDADE_PERSONALIZADA=id_grupo_prop,
                         NOME=nome, TIPO_VALOR=0)
            return props[nome]

        pecas_de_tubo = []     # (id_peca, nome, mm) para a geometria demo
        todas_as_pecas = []    # (id_peca, desc, familia, forma) para a paramétrica
        n_pecas = n_insumos = 0

        for fam in self.cat['familias']:
            linha = linha_de_produto(fam)
            tipo = classificar(fam['titulo'])

            # CLASSE_ITEM e CLASSE_PECA, uma por linha de produto.
            if linha not in classes_item:
                classes_item[linha] = self.novo('CLASSE_ITEM')
                self.ins('CLASSE_ITEM', ID_CLASSE_ITEM=classes_item[linha],
                         NOME_CI=f'{FABRICANTE} - {linha}',
                         CODIGO_ELLO=0, ATIVO=1)
            id_grupo_item = self.novo('GRUPO_ITEM')
            self.ins('GRUPO_ITEM', ID_GRUPO_ITEM=id_grupo_item,
                     ID_CLASSE_ITEM=classes_item[linha],
                     NOME_GI=fam['titulo'].title(),
                     UNIDADE_GI=(UNIDADE_METRO
                                 if tipo and tipo[2] == APL_TUBO
                                 else UNIDADE_PECA),
                     CODIGO_ELLO=0, ATIVO=1)

            id_grupo_peca = None
            if tipo is not None:
                (ifc, tipo_ent, ifc2x3), sub, apl, _forma = tipo
                if linha not in classes_peca:
                    classes_peca[linha] = self.novo('CLASSE_PECA')
                    self.ins('CLASSE_PECA',
                             ID_CLASSE_PECA=classes_peca[linha],
                             NOME_CP=f'{FABRICANTE} - {linha}',
                             INDICACAO_CP='', CODIGO_ELLO=0, ATIVO=1)
                aplicacao = (APLICACAO_ESGOTO if fam['secao'] == 'ESGOTO'
                             else APLICACAO_AGUA_FRIA)
                id_grupo_peca = self.novo('GRUPO_PECA')
                self.ins(
                    'GRUPO_PECA',
                    ID_GRUPO_PECA=id_grupo_peca,
                    NOME_GP=fam['titulo'].title(),
                    TIPO_SECAO_GP=0,
                    RUGOSIDADE_GP=RUGOSIDADE_PVC,
                    RUGOSIDADE_EQUIVALENTE=RUGOSIDADE_EQUIV_PVC,
                    TIPO_FWH=TIPO_FWH_PVC,
                    COEFICIENTE_MANNING=MANNING_PVC,
                    TIPO_MATERIAL=0,
                    PROJETO_APLICACAO=aplicacao,
                    ELEMENTO_APLICACAO=1 if apl == APL_TUBO else 0,
                    TIPO_CONFIGURACAO_GP=SENT_INT,
                    REPRESENTACAO_GP=2 if apl == APL_TUBO else 0,
                    ID_CLASSE_PECA=classes_peca[linha],
                    CODIGO_ELLO=0, ATIVO=1,
                    ENTIDADE_IFC=ifc, SUBTIPO_IFC=sub,
                    TIPO_ENTIDADE_IFC=tipo_ent,
                    ENTIDADE_IFC_2X3=ifc2x3, SUBTIPO_IFC_2X3=sub,
                    TIPO_ENTIDADE_IFC_2X3=tipo_ent)

            props_familia = propriedades_da_familia(fam)

            for linha_prod in fam['linhas']:
                desc = linha_prod['descricao']
                dim = dimensoes(desc)

                # ITEM: o insumo de orçamento. `CODIGO_ITEM` é onde o AltoQi
                # guarda o código comercial do fabricante — é lá que o 21011
                # da Akato pertence, do mesmo jeito que o 14808 da Amanco.
                id_item = self.novo('ITEM')
                self.ins('ITEM', ID_ITEM=id_item,
                         ID_GRUPO_ITEM=id_grupo_item,
                         NOME_ITEM=desc, CODIGO_ELLO=0, ATIVO=1,
                         FABRICANTE=FABRICANTE,
                         TABELA_REFERENCIA=TABELA_REFERENCIA,
                         CATEGORIA='Insumo',
                         CODIGO_ITEM=linha_prod['codigo'],
                         OBSERVACAO='')

                if id_grupo_peca is None:
                    n_insumos += 1
                    continue

                id_peca = self.novo('PECA')
                mm_principal = dim['mm'][0] if dim['mm'] else None
                # Código de diâmetro SÓ NO TUBO. Na Amanco as 48 peças de tubo
                # têm código e nenhuma das 700 conexões tem — o diâmetro de
                # uma conexão mora em `ENTRADA_PECA.DIAMETRO_EP`, que a Amanco
                # preenche nas 2.627 entradas dela e que este gerador não
                # escreve (ver o cabeçalho do módulo). Pôr o código na conexão
                # divergiria da única biblioteca real de conexões disponível.
                codigo_diam = (CODIGO_DIAMETRO.get(mm_principal)
                               if apl == APL_TUBO else None)
                self.ins(
                    'PECA',
                    ID_PECA=id_peca,
                    NOME_PECA=desc,
                    BIBLIOTECA=FABRICANTE,
                    SIMBOLO_SELECIONADO=1,
                    DESCRICAO_DADOS=desc,
                    POSICIONAR_SIMBOLOGIA=0,
                    POSICAO_DADOS=0,
                    POSICIONA_CAMPOS=1,
                    DESENHA_SIMBOLOGIA=2,
                    # Sem código de diâmetro observado, vai a sentinela — é o
                    # que a Amanco faz nas suas 700 conexões.
                    DIAMETRO_PECA=(codigo_diam if codigo_diam is not None
                                   else SENT_REAL),
                    INDICACAO_PLANTA=(f'ø{mm_principal}' if mm_principal
                                      else desc),
                    INDICACAO_DETALHE=(f'ø{mm_principal}' if mm_principal
                                       else desc),
                    COMPRIMENTO_PECA=(dim['comprimento_cm'] or 0),
                    ID_GRUPO_PECA=id_grupo_peca,
                    TIPO_APLICACAO_PECA=apl,
                    CODIGO_ELLO=0, ATIVO=1,
                    POSICIONAR_SIMBOLOGIA_3D=0,
                    FORMATO_PECA=-1,
                    OPCAO_RENDERIZACAO_PLANIFICADA=0,
                    INCLUIR_REPRESENTACAO3D_PARAMETRICA=0,
                    CONEXAO_VOLUMETRICA=0,
                    INDICE_SIMBOLO3D_SELECIONADO=-1)
                n_pecas += 1

                self.ins('DADOS_HIDRAULICOS',
                         ID_DADOS_HIDRAULICOS=self.novo('DADOS_HIDRAULICOS'),
                         TIPO_CURVA=TIPO_CURVA_CONEXAO, ID_PECA=id_peca)

                self.ins('ITEM_ASSOCIADO',
                         ID_ITEM_ASSOCIADO=self.novo('ITEM_ASSOCIADO'),
                         QUANTIDADE_IA=1.0,
                         MEDICAO_PECA=(MEDICAO_TUBO if apl == APL_TUBO
                                       else MEDICAO_CONEXAO),
                         ID_PECA=id_peca, ID_ITEM=id_item)

                valores = dict(props_familia)
                valores['Código Akato'] = linha_prod['codigo']
                if linha_prod['embalagem'] is not None:
                    valores['Embalagem'] = f"{linha_prod['embalagem']} un"
                if linha_prod['master'] is not None:
                    valores['Caixa master'] = f"{linha_prod['master']} un"
                for nome, valor in valores.items():
                    self.ins(
                        'VALOR_PROPRIEDADE_PERSONALIZADA',
                        ID_VALOR_PROPRIEDADE_PERSONALIZADA=self.novo(
                            'VALOR_PROPRIEDADE_PERSONALIZADA'),
                        ID_PROPRIEDADE_PERSONALIZADA=id_propriedade(nome),
                        ID_PECA=id_peca, VALOR=valor)

                if apl == APL_TUBO and mm_principal:
                    pecas_de_tubo.append((id_peca, desc, mm_principal,
                                          fam['secao'], linha))
                todas_as_pecas.append((id_peca, desc, fam, tipo[3],
                                       linha_prod))

        n_geo = 0
        if com_geometria == 'demo':
            self.geometria_demo(pecas_de_tubo)
            n_geo = len(pecas_de_tubo)
        elif com_geometria == 'parametrica':
            n_geo = self.geometria_parametrica(todas_as_pecas)

        self.con.commit()
        return {'pecas': n_pecas, 'insumos_sem_peca': n_insumos,
                'com_geometria': n_geo}

    # -- geometria paramétrica de todas as peças ---------------------------

    def geometria_parametrica(self, pecas):
        """
        Uma malha para CADA peça, gerada pelo `formas.py`.

        As formas são **representativas, não as cotas da Akato** — o catálogo
        não traz cota de forma nenhuma. O que é real: o diâmetro nominal (do
        catálogo) e a espessura de parede (da NBR 5648 / NBR 5688). Todo o
        resto — profundidade de bolsa, raio de curva, comprimento de braço,
        corpo de registro — é proporção inventada, na tabela `PROPORCOES` do
        `formas.py`.

        A ressalva fica gravada em três lugares dentro do arquivo, para não
        depender de quem leu este docstring:

        - no nome da `CLASSE_SIMBOLOGIA_3D`, com o sufixo "(forma
          representativa)" — é o que a cascata do `build.py` publica como
          linha do catálogo;
        - no nome do `GRUPO_SIMBOLOGIA_3D`, que é o que aparece na árvore do
          AltoQi;
        - numa propriedade personalizada em cada peça, que é o que aparece na
          ficha do produto.
        """
        import formas

        conv = {c['polegada']: c
                for c in self.cat.get('conversao_polegada_mm', [])}

        classes, grupos = {}, {}
        id_prop = self._id_propriedade_ressalva()
        n = 0

        for id_peca, desc, fam, forma, linha_prod in pecas:
            de1, de2 = diametros_mm(desc, fam['secao'], conv, forma)
            if de1 is None:
                continue
            comp = (dimensoes(desc)['comprimento_cm']
                    or comprimento_do_titulo(fam['titulo']))
            peca = formas.Peca(de1, de2, fam['secao'], fam['titulo'], comp)
            malhas = formas.gerar(forma, peca)
            if not malhas:
                continue

            lp = linha_de_produto(fam)
            if lp not in classes:
                classes[lp] = self.novo('CLASSE_SIMBOLOGIA_3D')
                self.ins('CLASSE_SIMBOLOGIA_3D',
                         ID_CLASSE_SIMBOLOGIA_3D=classes[lp],
                         NOME_CLASSE=f'{FABRICANTE.upper()} - {lp}',
                         CODIGO_ELLO=0, ATIVO=1)
            chave = (lp, fam['titulo'])
            if chave not in grupos:
                grupos[chave] = self.novo('GRUPO_SIMBOLOGIA_3D')
                self.ins('GRUPO_SIMBOLOGIA_3D',
                         ID_GRUPO_SIMBOLOGIA_3D=grupos[chave],
                         NOME_GRUPO=f"{fam['titulo'].title()} "
                                    f'(forma representativa)',
                         CODIGO_ELLO=0, ATIVO=1, ID_CLASSE=classes[lp])

            blob = oq3d_writer.escrever(
                [(v, t, c, None) for v, t, c in malhas])
            id_simb = self.novo('SIMBOLOGIA_3D')
            self.ins('SIMBOLOGIA_3D',
                     ID_SIMBOLOGIA_3D=id_simb,
                     ID_GRUPO_SIMBOLOGIA_3D=grupos[chave],
                     NOME=f"{linha_prod['codigo']} {desc}",
                     CODIGO_ELLO=0, ATIVO=1,
                     SIMBOLOGIA_3D=sqlite3.Binary(blob),
                     REFERENCIA_CORTE=0, EMBUTIMENTO=1.0, USA_CORES_PECA=1,
                     DESLOCAMENTO_X=0.0, DESLOCAMENTO_Y=0.0,
                     DESLOCAMENTO_Z=0.0, ANGULO_PLANO_XY=0.0,
                     ANGULO_PLANO_XZ=0.0, ANGULO_PLANO_YZ=0.0)
            self.ins('PECA_SIMBOLOGIA_3D',
                     ID_PECA_SIMBOLOGIA_3D=self.novo('PECA_SIMBOLOGIA_3D'),
                     ID_PECA=id_peca, ID_SIMBOLOGIA_3D=id_simb)
            self.ins('VALOR_PROPRIEDADE_PERSONALIZADA',
                     ID_VALOR_PROPRIEDADE_PERSONALIZADA=self.novo(
                         'VALOR_PROPRIEDADE_PERSONALIZADA'),
                     ID_PROPRIEDADE_PERSONALIZADA=id_prop,
                     ID_PECA=id_peca,
                     VALOR='forma representativa gerada por parâmetro; '
                           'cotas de encaixe não são as do fabricante')
            n += 1
        return n

    def _id_propriedade_ressalva(self):
        """A propriedade que carrega a ressalva da forma, por peça."""
        pid = self.novo('PROPRIEDADE_PERSONALIZADA')
        self.ins('PROPRIEDADE_PERSONALIZADA',
                 ID_PROPRIEDADE_PERSONALIZADA=pid,
                 ID_GRUPO_PROPRIEDADE_PERSONALIZADA=1,
                 NOME='Geometria 3D', TIPO_VALOR=0)
        return pid

    # -- geometria de demonstração ----------------------------------------

    # Espessura de parede em milímetros. NÃO vem do catálogo da Akato — vem das
    # normas NBR 5648 (soldável) e NBR 5688 (esgoto série normal). Está aqui
    # só para a demonstração do caminho da geometria; um arquivo de produção
    # deve usar a cota do fabricante.
    PAREDE_MM = {
        'ÁGUA FRIA': {20: 1.5, 25: 1.7, 32: 2.1, 40: 2.4, 50: 3.0, 60: 3.3},
        'ESGOTO': {40: 1.5, 50: 1.7, 75: 1.7, 100: 2.1, 150: 3.2, 200: 4.6},
    }
    COMPRIMENTO_TUBO_CM = 600.0          # os dois tubos do catálogo são de 6 m
    COR_PVC = {'ÁGUA FRIA': (150, 88, 55, 255),    # marrom
               'ESGOTO': (235, 235, 230, 255)}     # branca

    def geometria_demo(self, tubos):
        """
        Malha paramétrica para as famílias de tubo, e só para elas.

        Um tubo é o único produto deste catálogo cuja forma está inteiramente
        determinada pelo que o PDF diz mais a norma: um cilindro vazado de
        diâmetro externo nominal e 6 m de comprimento. Todo o resto — joelhos,
        tês, luvas, caixas sifonadas — depende de cotas que o catálogo não
        traz.

        Vale notar que nem isto seria necessário numa biblioteca de produção:
        as 48 peças de tubo da Amanco não têm linha em `PECA_SIMBOLOGIA_3D`,
        porque o AltoQi gera o cilindro do tubo parametricamente a partir de
        `DIAMETRO_PECA` e `COMPRIMENTO_PECA`. Isto existe para exercitar o
        `oq3d_writer.py` dentro de um `.aq` de verdade.
        """
        import oq3d_writer as w

        # `CLASSE_SIMBOLOGIA_3D.NOME_CLASSE` tem de seguir o padrão
        # "FABRICANTE - Linha de Produto": é o primeiro passo da cascata de
        # inferência de fabricante do `build.py`, e o `PECA.BIBLIOTECA` está
        # vazio nas 12 bibliotecas reais, então na prática é a única fonte.
        # Uma classe chamada "AKATO - Tubos PVC (demonstração)" faz o
        # pipeline publicar "Tubos PVC (demonstração)" como a linha do
        # catálogo. A ressalva da demonstração vai no nome do GRUPO, que é o
        # que aparece na árvore do AltoQi, e não na linha do produto.
        classes, grupos = {}, {}

        def containers(secao, linha):
            if linha not in classes:
                classes[linha] = self.novo('CLASSE_SIMBOLOGIA_3D')
                self.ins('CLASSE_SIMBOLOGIA_3D',
                         ID_CLASSE_SIMBOLOGIA_3D=classes[linha],
                         NOME_CLASSE=f'{FABRICANTE.upper()} - {linha}',
                         CODIGO_ELLO=0, ATIVO=1)
                grupos[linha] = self.novo('GRUPO_SIMBOLOGIA_3D')
                self.ins('GRUPO_SIMBOLOGIA_3D',
                         ID_GRUPO_SIMBOLOGIA_3D=grupos[linha],
                         NOME_GRUPO='TUBO (demonstração)',
                         CODIGO_ELLO=0, ATIVO=1, ID_CLASSE=classes[linha])
            return grupos[linha]

        for id_peca, nome, mm, secao, linha in tubos:
            id_grupo = containers(secao, linha)
            parede = self.PAREDE_MM.get(secao, {}).get(mm)
            if parede is None:
                continue
            r_ext = mm / 20.0                     # mm de diâmetro → cm de raio
            r_int = r_ext - parede / 10.0
            verts, tris = w.tubo(r_ext, r_int, self.COMPRIMENTO_TUBO_CM,
                                 lados=32)
            blob = w.escrever([(verts, tris,
                                self.COR_PVC.get(secao, (200, 200, 200, 255)),
                                None)])
            id_simb = self.novo('SIMBOLOGIA_3D')
            self.ins('SIMBOLOGIA_3D',
                     ID_SIMBOLOGIA_3D=id_simb,
                     ID_GRUPO_SIMBOLOGIA_3D=id_grupo,
                     NOME=f'{mm}MM', CODIGO_ELLO=0, ATIVO=1,
                     SIMBOLOGIA_3D=sqlite3.Binary(blob),
                     REFERENCIA_CORTE=0, EMBUTIMENTO=1.0,
                     USA_CORES_PECA=1,
                     DESLOCAMENTO_X=0.0, DESLOCAMENTO_Y=0.0,
                     DESLOCAMENTO_Z=0.0, ANGULO_PLANO_XY=0.0,
                     ANGULO_PLANO_XZ=0.0, ANGULO_PLANO_YZ=0.0)
            self.ins('PECA_SIMBOLOGIA_3D',
                     ID_PECA_SIMBOLOGIA_3D=self.novo('PECA_SIMBOLOGIA_3D'),
                     ID_PECA=id_peca, ID_SIMBOLOGIA_3D=id_simb)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('catalogo')
    ap.add_argument('saida')
    ap.add_argument('--schema', default=os.path.join(
        os.path.dirname(AQUI), 'dados', 'schema-aq-607.sql'))
    ap.add_argument('--modelo', default=None,
                    help='.aq de referência, se não houver --schema')
    ap.add_argument('--geometria-demo', action='store_true',
                    help='malha só para as famílias de tubo')
    ap.add_argument('--geometria-parametrica', action='store_true',
                    help='malha representativa para TODAS as peças')
    args = ap.parse_args()

    with open(args.catalogo, encoding='utf-8') as f:
        catalogo = json.load(f)

    print(f'gerando {args.saida}')
    con = criar_schema(args.saida, args.schema, args.modelo)
    g = Gerador(con, catalogo)
    modo = ('parametrica' if args.geometria_parametrica
            else 'demo' if args.geometria_demo else None)
    resumo = g.gerar(com_geometria=modo)
    con.close()

    tam = os.path.getsize(args.saida)
    print(f"  {resumo['pecas']} peças, "
          f"{resumo['insumos_sem_peca']} insumos sem peça, "
          f"{resumo['com_geometria']} com geometria ({modo or 'nenhuma'})")
    print(f'  {tam:,} bytes'.replace(',', '.'))


if __name__ == '__main__':
    main()
