#!/usr/bin/env python3
"""
aq_referencia.py — extrai de um `.aq` real os valores que um GERADOR precisa.

`docs/conhecimento/aq-formato.md` documenta o schema para **ler**. Para **escrever** falta outra coisa: os valores concretos que o AltoQi
Builder põe nas colunas de enum e de configuração — `PROJETO_APLICACAO`,
`TIPO_APLICACAO_PECA`, `ENTIDADE_IFC`, `TIPO_SECAO_GP` — e quais tabelas ficam
de fato preenchidas numa biblioteca de fabricante.

Somente leitura: abre o `.aq` e imprime. Nunca escreve no arquivo.

Uso:
    python3 -m bim_pipeline.cli.ferramentas.aq_referencia <arquivo.aq> [--tabela NOME] [--limite N]
"""
import argparse
import sqlite3
import sys

# Colunas BLOB que nunca devem ser lidas por inteiro: o WIREFRAME é 69-71% do
# arquivo (285 MB dos 412 MB da Amanco) e não serve para nada aqui.
BLOBS = {'SIMBOLOGIA_3D', 'IMAGEM', 'SIMBOLOGIA_3D_SIMPLIFICADA',
         'IMAGEM_SIMPLIFICADA', 'WIREFRAME', 'SIMBOLOGIA', 'METAINFOS',
         'SIMBOLO_ESQUEMA_LIGACAO'}

# As tabelas que compõem uma biblioteca de fabricante, na ordem em que têm de
# ser inseridas para as chaves estrangeiras fecharem.
ORDEM_INSERCAO = [
    'VERSAO_BANCO_CADASTRO',
    'CLASSE_PECA', 'GRUPO_PECA', 'PECA',
    'CLASSE_SIMBOLOGIA_3D', 'GRUPO_SIMBOLOGIA_3D', 'SIMBOLOGIA_3D',
    'PECA_SIMBOLOGIA_3D', 'ENTRADA_3D', 'ENTRADA_PECA',
    'MODELO_BOMBA', 'ITEM_CURVA_BOMBA', 'DADOS_HIDRAULICOS',
    'GRUPO_PROPRIEDADE_PERSONALIZADA', 'PROPRIEDADE_PERSONALIZADA',
    'VALOR_PROPRIEDADE_PERSONALIZADA',
    'CLASSE_ITEM', 'GRUPO_ITEM', 'ITEM', 'ITEM_ASSOCIADO',
    'CLASSE_SIMBOLOGIA', 'GRUPO_SIMBOLOGIA', 'CONTEUDO_SIMBOLOGIA',
    'SIMBOLOGIA', 'PECA_SIMBOLOGIA',
]


def _decode_texto(b):
    """cp1252, não latin-1 — ver a skill `leitor-biblioteca-aq`."""
    try:
        return b.decode('cp1252')
    except UnicodeDecodeError:
        return b.decode('latin-1')


def abrir(caminho):
    con = sqlite3.connect(f'file:{caminho}?mode=ro', uri=True)
    con.text_factory = _decode_texto
    con.row_factory = sqlite3.Row
    return con


def colunas(con, tabela):
    return [r[1] for r in con.execute(f'PRAGMA table_info("{tabela}")')]


def colunas_seguras(con, tabela):
    """Colunas da tabela menos os BLOBs grandes, que viram LENGTH()."""
    saida = []
    for c in colunas(con, tabela):
        if c in BLOBS:
            saida.append(f'LENGTH("{c}") AS "len_{c}"')
        else:
            saida.append(f'"{c}"')
    return saida


def contagens(con):
    tabelas = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    saida = {}
    for t in tabelas:
        saida[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    return saida


def amostra(con, tabela, limite):
    sel = ', '.join(colunas_seguras(con, tabela))
    return list(con.execute(f'SELECT {sel} FROM "{tabela}" LIMIT {limite}'))


def distintos(con, tabela, coluna):
    """Valores distintos de uma coluna, com contagem — para achar os enums."""
    return list(con.execute(
        f'SELECT "{coluna}" AS v, COUNT(*) AS n FROM "{tabela}" '
        f'GROUP BY 1 ORDER BY n DESC LIMIT 12'))


# Colunas de enum/configuração cujos valores concretos o gerador precisa.
ENUNS = {
    'GRUPO_PECA': ['PROJETO_APLICACAO', 'ELEMENTO_APLICACAO', 'TIPO_SECAO_GP',
                   'TIPO_MATERIAL', 'TIPO_FWH', 'RUGOSIDADE_GP',
                   'TIPO_CONFIGURACAO_GP', 'REPRESENTACAO_GP',
                   'ENTIDADE_IFC', 'SUBTIPO_IFC', 'TIPO_ENTIDADE_IFC',
                   'ENTIDADE_IFC_2X3', 'SUBTIPO_IFC_2X3',
                   'TIPO_ENTIDADE_IFC_2X3', 'ATIVO', 'CODIGO_ELLO'],
    'PECA': ['TIPO_APLICACAO_PECA', 'SECAO', 'FORMATO_PECA', 'ATIVO',
             'BIBLIOTECA', 'SIMBOLO_SELECIONADO', 'POSICIONAR_SIMBOLOGIA',
             'POSICAO_DADOS', 'POSICIONA_CAMPOS', 'DESENHA_SIMBOLOGIA',
             'POSICIONAR_SIMBOLOGIA_3D', 'OPCAO_RENDERIZACAO_PLANIFICADA',
             'INCLUIR_REPRESENTACAO3D_PARAMETRICA', 'CONEXAO_VOLUMETRICA',
             'INDICE_SIMBOLO3D_SELECIONADO', 'CODIGO_ELLO', 'DIAMETRO_INTERNO'],
    'SIMBOLOGIA_3D': ['USA_CORES_PECA', 'REFERENCIA_CORTE', 'EMBUTIMENTO',
                      'ATIVO', 'CODIGO_ELLO'],
    'ENTRADA_3D': ['TIPO_SECAO', 'DIAMETRO'],
    'ENTRADA_PECA': ['LIGACAO_EP', 'SECAO_EP', 'DIAMETRO_EP'],
    'DADOS_HIDRAULICOS': ['TIPO_CURVA', 'DIAMETRO_MINIMO', 'TIPO_POSICAO',
                          'COEFICIENTE_RUGOSIDADE', 'FATOR_K'],
    'PROPRIEDADE_PERSONALIZADA': ['TIPO_VALOR'],
    'CLASSE_PECA': ['NOME_CP', 'INDICACAO_CP', 'ATIVO'],
    'CLASSE_SIMBOLOGIA_3D': ['NOME_CLASSE', 'ATIVO'],
    'GRUPO_ITEM': ['UNIDADE_GI', 'ATIVO'],
    'ITEM': ['FABRICANTE', 'CATEGORIA', 'TABELA_REFERENCIA'],
    'ITEM_ASSOCIADO': ['QUANTIDADE_IA', 'MEDICAO_PECA'],
}


def linha_legivel(row, largura=118):
    itens = []
    for k in row.keys():
        v = row[k]
        if v is None or v == '' or v == 0:
            continue          # o silêncio já diz "default"
        itens.append(f'{k}={v!r}')
    texto = ' '.join(itens)
    return texto if len(texto) <= largura else texto[:largura] + ' …'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('aq')
    ap.add_argument('--tabela', action='append', default=None)
    ap.add_argument('--limite', type=int, default=3)
    args = ap.parse_args()

    con = abrir(args.aq)
    cont = contagens(con)

    print(f'### {args.aq}')
    ver = con.execute('SELECT * FROM VERSAO_BANCO_CADASTRO').fetchone()
    print('VERSAO_BANCO_CADASTRO:', dict(ver))

    print('\n### TABELAS PREENCHIDAS')
    for t, n in sorted(cont.items(), key=lambda kv: -kv[1]):
        if n:
            marca = '*' if t in ORDEM_INSERCAO else ' '
            print(f'  {marca} {t:40} {n:7}')
    vazias = [t for t, n in cont.items() if not n]
    print(f'  ({len(vazias)} tabelas vazias)')

    alvos = args.tabela or [t for t in ORDEM_INSERCAO if cont.get(t)]
    for t in alvos:
        if not cont.get(t):
            print(f'\n### {t} — VAZIA')
            continue
        print(f'\n### {t}  ({cont[t]} linhas)')
        for row in amostra(con, t, args.limite):
            print('   ', linha_legivel(row))
        for col in ENUNS.get(t, []):
            if col not in colunas(con, t):
                continue
            vals = distintos(con, t, col)
            resumo = ', '.join(f'{r["v"]!r}×{r["n"]}' for r in vals)
            print(f'    · {col}: {resumo}')
    con.close()


if __name__ == '__main__':
    main()
