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

# PROJETO_APLICACAO, TIPO_APLICACAO_PECA, ENTIDADE_IFC e o vocabulário que classifica um
# grupo pelo nome **saíram daqui** (2026-09-10, ADR-024) e moram em `bim_pipeline.aq.cadastro`:
# a disciplina é bitmask e vem de quem importa, não de quatro palavras no título, e o
# vocabulário é um por disciplina. As quatro constantes que existiam aqui
# (`APLICACAO_AGUA_FRIA = 12` e `APLICACAO_INCENDIO = 22`) estavam erradas contra o catálogo
# oficial: 12 é hidráulico **mais sanitário** e 22 carrega um bit não identificado.

# Hazen-Williams C e Manning do PVC, como as bibliotecas de PVC gravam.
RUGOSIDADE_PVC = 135.0
RUGOSIDADE_EQUIV_PVC = 6e-05
MANNING_PVC = 0.01
TIPO_FWH_PVC = 1

# DADOS_HIDRAULICOS.TIPO_CURVA — 2 em todas as conexões observadas.
TIPO_CURVA_CONEXAO = 2

# GRUPO_ITEM.UNIDADE_GI — 1 nos grupos de tubo, 0 no resto.
# ITEM_ASSOCIADO.MEDICAO_PECA — 1 nas peças de tubo, 2 nas conexões.
UNIDADE_METRO, UNIDADE_PECA = 1, 0
MEDICAO_TUBO, MEDICAO_CONEXAO = 1, 2

# O código de bitola (`ENTRADA_PECA.DIAMETRO_EP`, `PECA.DIAMETRO_PECA`) também mora em
# `cadastro.py`. A escala é **em polegada** — a tabela em milímetro que existia aqui era a
# equivalência do PVC esgoto e errava toda bitola de PVC soldável.


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
