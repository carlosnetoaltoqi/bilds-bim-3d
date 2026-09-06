"""
aq_writer.py — ESCREVE uma biblioteca `.aq` do AltoQi Builder: o schema completo, as
constantes do AltoQi (sentinelas, códigos IFC, aplicações, unidades) e um escritor que
grava texto em cp1252 como o Builder faz. É o inverso do `read_aq.py`.

Era a parte genérica do gerador do estudo de escrita de `.aq` a partir de PDF (2026-09-02, `docs/historico/estudos/escrita-aq-de-pdf/`);
promovida para o pipeline do serviço de ingestão em 2026-09-05 (I4) para que o `geo_to_aq.py`
— o "Exportar .aq" do editor — não dependa de uma pasta de estudo. O que era do catálogo estudado
(classificação de famílias, dimensões do PDF, formas representativas) continua lá, como
`Gerador(EscritorAq)`.

Tudo aqui foi observado em bibliotecas reais de fabricante (schemas 595 e 607);
o conhecimento está em `docs/conhecimento/aq-escrita.md` e na skill `leitor-biblioteca-aq`.
"""
import os
import sqlite3

AQUI = os.path.dirname(os.path.abspath(__file__))
# DDL das 77 tabelas e 84 índices do schema 607, extraído de uma biblioteca real. Nunca é
# escrito à mão: uma coluna faltando faz o AltoQi recusar o arquivo.
SCHEMA_SQL = os.path.join(AQUI, 'schema-aq-607.sql')

# --- Constantes do AltoQi, todas observadas em bibliotecas reais ----------

VERSAO_SCHEMA = 607          # a mais nova entre as 12 bibliotecas disponíveis
MODO_GRAVACAO = 2
TAG_IDIOMA = 'pt-BR'

# Sentinelas de "não definido". O AltoQi não usa NULL para isso.
SENT_INT = -2147483647
SENT_REAL = -1.7976931348623157e+308     # -DBL_MAX

# PROJETO_APLICACAO — tipo de instalação do grupo. Valores observados:
#   8  esgoto        (biblioteca de PVC esgoto)
#   12 água fria     (bombas e pressurizadores)
#   22 incêndio      (bombas de combate a incêndio)
#   36 gás           (aquecedor de passagem a gás)
#   64, 76 elétrico  (barramento blindado)
APLICACAO_ESGOTO = 8
APLICACAO_AGUA_FRIA = 12
APLICACAO_INCENDIO = 22
APLICACAO_GAS = 36

# Hazen-Williams C e Manning do PVC, como as bibliotecas de PVC gravam.
RUGOSIDADE_PVC = 135.0
RUGOSIDADE_EQUIV_PVC = 6e-05
MANNING_PVC = 0.01
TIPO_FWH_PVC = 1

# ENTIDADE_IFC / SUBTIPO_IFC / TIPO_ENTIDADE_IFC / ENTIDADE_IFC_2X3.
# Os quatro andam juntos; estas combinações vêm de uma biblioteca de conexões (schema 595) e
# de uma de bombas (607), correlacionando `GRUPO_PECA.NOME_GP` com os códigos.
IFC_CONEXAO = (2071, 4099, 2088)      # IfcPipeFitting
IFC_TUBO = (2072, 4096, 2086)         # IfcPipeSegment
IFC_BOMBA = (2075, 4118, 2093)        # bomba (SUBTIPO_IFC = 5)
IFC_APARELHO = (2076, 4122, 2092)     # aparelho sanitário
IFC_VALVULA = (2084, 4103, 2091)      # válvula
IFC_TERMINAL = (2085, 4123, 2092)     # ralo, caixa sifonada

# SUBTIPO_IFC dentro de IfcPipeFitting, pelos grupos de uma biblioteca de conexões:
#   0 curva/joelho   1 luva      3 cap      4 tê/junção     6 redução
SUB_CURVA, SUB_LUVA, SUB_CAP, SUB_TE, SUB_REDUCAO = 0, 1, 3, 4, 6
SUB_TUBO = 3                          # único observado em IfcPipeSegment
SUB_BOMBA = 5                         # único observado em 2075

# TIPO_APLICACAO_PECA, observado numa biblioteca de conexões:
#   1 tubo   2 conexão   8 aparelho sanitário   9 caixa sifonada/ralo com
#   grelha   10 ralo   55 ramal de ventilação        (6 = bomba, numa biblioteca de bombas)
APL_TUBO, APL_CONEXAO, APL_APARELHO, APL_CAIXA, APL_RALO = 1, 2, 8, 9, 10
APL_BOMBA = 6

# DADOS_HIDRAULICOS.TIPO_CURVA — 2 em todas as conexões observadas.
TIPO_CURVA_CONEXAO = 2

# GRUPO_ITEM.UNIDADE_GI — 1 nos grupos de tubo, 0 no resto.
# ITEM_ASSOCIADO.MEDICAO_PECA — 1 nas peças de tubo, 2 nas conexões.
UNIDADE_METRO, UNIDADE_PECA = 1, 0
MEDICAO_TUBO, MEDICAO_CONEXAO = 1, 2

# CODIGO_DIAMETRO — o código que o AltoQi usa em `PECA.DIAMETRO_PECA` e
# `ENTRADA_PECA.DIAMETRO_EP`. NÃO é o diâmetro em centímetro (erro antigo, corrigido em
# `docs/conhecimento/aq-formato.md`): numa biblioteca real a peça `50 mm - 2"` tem
# `DIAMETRO_PECA = 9`, e a `100 mm - 4"` tem 12.
#
# Só estes seis pares foram observados. Numa biblioteca de conexões real, ~10 % das peças trazem código
# (48 de tubo, 52 de caixa sifonada e afins, 12 de ralo), 963 trazem a sentinela
# -DBL_MAX e algumas trazem zero; nenhuma conexão traz código. Uma biblioteca de bombas usa os códigos
# 7 a 11 nos bocais das bombas, cujas sucções e recalques vão de 1.1/4" a 3" —
# consistente com a mesma escala, e é de onde vem o 10.
#
# Os códigos das bitolas de água fria abaixo de 40 mm (20, 25, 32) NÃO
# aparecem em nenhuma das 12 bibliotecas. Ficam fora: uma peça sem código de
# diâmetro usa a sentinela, exatamente como as conexões das bibliotecas reais.
CODIGO_DIAMETRO = {40: 8, 50: 9, 60: 10, 75: 11, 100: 12, 150: 14, 200: 15}


def _sem_acento(texto):
    import unicodedata
    nfd = unicodedata.normalize('NFD', texto or '')
    return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn').upper()


# Classificação de um grupo de peças pelo nome — (ENTIDADE_IFC…, SUBTIPO_IFC, TIPO_APLICACAO_PECA).
# É o vocabulário de um catálogo hidráulico em PVC; a primeira regra que casa (palavra
# inteira) vence, e sem regra a peça entra como conexão genérica (luva), que é o caso mais
# comum e o mais inofensivo. Nasceu da tabela `REGRAS_TIPO` do gerador daquele estudo
# e foi AJUSTADA contra os 192 grupos com 3D de uma biblioteca de conexões real (2026-09-05): reproduz 189 deles
# ("Junção … com Joelho" é tê, não curva; caixa sifonada é 2085/1/9; terminal de ventilação é
# 2079; ralo pluvial é 2085/0/10; adaptador é luva; sifão é cap). Os 3 restantes são
# inconsistências da própria biblioteca ('Caixa Sifonada' e 'Chuveiro Residencial' com códigos
# diferentes dos irmãos). Serve a quem escreve um
# `.aq` a partir de um catálogo que não guardou esses códigos (o `catalogo_to_aq.py`).
IFC_TERMINAL_VENT = (2079, 4121, 2092)   # terminal de ventilação
REGRAS_GRUPO = (
    (('TUBO',),                              IFC_TUBO,          SUB_TUBO,    APL_TUBO),
    (('BOMBA', 'PRESSURIZADOR', 'MOTOBOMBA'), IFC_BOMBA,         SUB_BOMBA,   APL_BOMBA),
    (('CAIXA SIFONADA',),                    IFC_TERMINAL,      SUB_LUVA,    APL_CAIXA),
    (('GRELHA',),                            IFC_APARELHO,      SUB_CAP,     APL_APARELHO),
    (('RALO', 'RALOS'),                      IFC_TERMINAL,      SUB_CURVA,   APL_RALO),
    (('MAQUINA',),                           IFC_APARELHO,      10,          APL_APARELHO),
    (('CHUVEIRO',),                          IFC_APARELHO,      SUB_CAP,     APL_APARELHO),
    (('PIA', 'LAVATORIO', 'TANQUE', 'VASO', 'KIT'), IFC_APARELHO, SUB_TE,   APL_APARELHO),
    (('SIFAO',),                             IFC_CONEXAO,       SUB_CAP,     APL_CONEXAO),
    (('TERMINAL DE VENTILACAO',),            IFC_TERMINAL_VENT, SUB_LUVA,    APL_CONEXAO),
    (('VALVULA', 'REGISTRO', 'TORNEIRA', 'BOIA'), IFC_VALVULA,  22,          APL_CONEXAO),
    (('JUNCAO', 'TE'),                       IFC_CONEXAO,       SUB_TE,      APL_CONEXAO),
    (('CURVA', 'JOELHO', 'TRANSPOSICAO'),    IFC_CONEXAO,       SUB_CURVA,   APL_CONEXAO),
    (('CAP', 'PLUG', 'ESPUDE', 'TAMPAO'),    IFC_CONEXAO,       SUB_CAP,     APL_CONEXAO),
    (('REDUCAO', 'BUCHA'),                   IFC_CONEXAO,       SUB_REDUCAO, APL_CONEXAO),
    (('LUVA', 'UNIAO', 'NIPEL', 'ANEL', 'ENGATE', 'ADAPTADOR'), IFC_CONEXAO, SUB_LUVA, APL_CONEXAO),
)


def classificar_grupo(nome):
    """(entidade_ifc, subtipo_ifc, tipo_aplicacao_peca) para o nome de um grupo/série."""
    import re
    alvo = _sem_acento(nome)
    for chaves, ifc, sub, apl in REGRAS_GRUPO:
        if any(re.search(rf'\b{re.escape(k)}\b', alvo) for k in chaves):
            return ifc, sub, apl
    return IFC_CONEXAO, SUB_LUVA, APL_CONEXAO


def aplicacao_de(*textos):
    """`PROJETO_APLICACAO` inferido do título/linha: esgoto 8, incêndio 22, gás 36, senão água fria 12."""
    alvo = ' '.join(_sem_acento(t) for t in textos if t)
    if 'ESGOTO' in alvo or 'PLUVIAL' in alvo:
        return APLICACAO_ESGOTO
    if 'INCENDIO' in alvo or 'SPRINKLER' in alvo or 'HIDRANTE' in alvo:
        return APLICACAO_INCENDIO
    if 'GAS' in alvo.split() or 'GLP' in alvo:
        return APLICACAO_GAS
    return APLICACAO_AGUA_FRIA


def criar_schema(destino, schema_sql=SCHEMA_SQL, modelo=None):
    """
    Cria o `.aq` vazio com o schema completo do AltoQi.

    O DDL vem de `schema_sql` (padrão: o `schema-aq-607.sql` deste diretório) ou, se não
    houver, é lido do `sqlite_master` de um `.aq` real (`modelo`). Nunca é escrito à mão: são 77 tabelas e
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


class EscritorAq:
    """INSERTs num `.aq` com ids sequenciais por tabela e texto em cp1252."""

    def __init__(self, con):
        self.con = con
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
            → b'Bomba de Combate a Inc\\xeancio - Fabricante'

        `\\xea` é `ê` em cp1252 e não é UTF-8 válido. O `typeof()` continua
        `'text'`: o SQLite não valida a codificação do que se manda gravar.

        O `read_aq.py` lê com `text_factory` cp1252. Então
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

    def versao(self):
        """Cabeçalho `VERSAO_BANCO_CADASTRO` — sem ele o Builder não abre o arquivo."""
        self.ins('VERSAO_BANCO_CADASTRO',
                 VERSAO=VERSAO_SCHEMA, VERSAO_CONTEUDO_CADASTRO_ELLO=0,
                 MODO_GRAVACAO=MODO_GRAVACAO, TRADUCAO_HABILITADA=0,
                 TAG_IDIOMA=TAG_IDIOMA)

    # -- peças ------------------------------------------------------------
