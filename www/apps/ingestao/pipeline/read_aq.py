#!/usr/bin/env python3
"""
read_aq.py — Extrai dados de uma biblioteca BIM AltoQi (.aq) para JSON.

Um .aq pode ser de dois tipos:
  1. ZIP contendo SQLite — caso mais comum ao baixar do AltoQi
  2. SQLite direto — ocorre quando o .aq foi extraído de outro ZIP

Sempre tenta SQLite direto primeiro (método robusto).

Encoding: **cp1252**, não latin-1. Os dois são idênticos exceto na faixa
0x80–0x9F, que é justamente onde moram travessão (0x96), aspas curvas
(0x93/0x94) e reticências (0x85) — os caracteres que aparecem em nome de peça.
Lidos como latin-1 eles viram caracteres de controle e chegam quebrados na
página do catálogo. Ver `_decode_texto`.

Uso:
  python3 www/apps/ingestao/pipeline/read_aq.py <arquivo.aq> <saida.json>
"""
import sys
import json
import sqlite3
import zipfile
import os
import shutil
import tempfile
import argparse
from urllib.request import pathname2url


def _decode_texto(b):
    """
    Decodifica texto do .aq. O AltoQi Builder é aplicação Windows, então grava
    cp1252 — usar latin-1 corrompe travessão, aspas curvas e reticências.

    cp1252 deixa cinco bytes indefinidos (0x81, 0x8D, 0x8F, 0x90, 0x9D) e falha
    neles; latin-1 nunca falha. O fallback existe para que uma biblioteca com
    esses bytes continue abrindo, em vez de derrubar o build inteiro por causa
    de um caractere.
    """
    try:
        return b.decode('cp1252')
    except UnicodeDecodeError:
        return b.decode('latin-1')


def open_aq(aq_path):
    """
    Abre um .aq como SQLite. Tenta direto primeiro, cai para ZIP se falhar.
    Retorna (connection, tmp_dir_or_None).
    Caller deve fechar a connection e remover tmp_dir se não for None.
    """
    # `sqlite3.connect(caminho)` CRIA um arquivo vazio se ele não existir e depois
    # falha no SELECT — o erro virava "não é SQLite nem ZIP" e ficava um .aq de 0 bytes
    # no disco. Checar antes e abrir somente-leitura.
    if not os.path.isfile(aq_path):
        raise FileNotFoundError(f'biblioteca .aq não encontrada: {aq_path}')

    # Tentativa 1: SQLite direto
    try:
        uri = 'file:' + pathname2url(os.path.abspath(aq_path)) + '?mode=ro'
        con = sqlite3.connect(uri, uri=True)
        con.text_factory = _decode_texto
        con.row_factory = sqlite3.Row
        con.execute('SELECT 1 FROM GRUPO_PECA LIMIT 1')
        return con, None
    except Exception:
        pass

    # Tentativa 2: ZIP contendo SQLite
    tmp_dir = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(aq_path, 'r') as z:
            z.extractall(tmp_dir)
    except zipfile.BadZipFile:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ValueError(f'{aq_path} não é um SQLite válido nem um ZIP válido')

    db_files = [f for f in os.listdir(tmp_dir)
                if os.path.isfile(os.path.join(tmp_dir, f)) and not f.endswith('.xml')]
    if not db_files:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise FileNotFoundError('Nenhum SQLite encontrado dentro do .aq')

    dest = os.path.join(tmp_dir, '_extracted.db')
    shutil.copy(os.path.join(tmp_dir, db_files[0]), dest)
    con = sqlite3.connect(dest)
    con.text_factory = _decode_texto
    con.row_factory = sqlite3.Row
    return con, tmp_dir


def extract(aq_path):
    """
    Extrai todos os dados relevantes do .aq e retorna dict estruturado.

    Estrutura de retorno:
      grupos:       list de dicts GRUPO_PECA (séries/famílias)
      pecas:        list de dicts PECA (variantes)
      curvas:       list de pontos Q-H (VAZAO_ICB, ALTURA_ICB, POTENCIA_ICB, RENDIMENTO_ICB)
      propriedades: list de propriedades personalizadas por peça
    """
    con, tmp_dir = open_aq(aq_path)
    cur = con.cursor()
    result = {'grupos': [], 'pecas': [], 'curvas': [], 'propriedades': []}

    try:
        # Grupos (séries/famílias de produtos)
        cur.execute('SELECT * FROM GRUPO_PECA WHERE ATIVO = 1 ORDER BY ID_GRUPO_PECA')
        result['grupos'] = [dict(r) for r in cur.fetchall()]

        # Peças (variantes individuais)
        cur.execute('SELECT * FROM PECA WHERE ATIVO = 1 ORDER BY ID_GRUPO_PECA, ID_PECA')
        result['pecas'] = [dict(r) for r in cur.fetchall()]

        # Curvas Q-H (apenas para grupos com MODELO_BOMBA)
        try:
            cur.execute("""
                SELECT
                    p.ID_PECA,
                    p.NOME_PECA,
                    gp.NOME_GP        AS serie,
                    mb.NOME_MB        AS modelo_bomba,
                    mb.POTENCIA_MB    AS potencia_cv,
                    icb.VAZAO_ICB     AS vazao,
                    icb.ALTURA_ICB    AS altura,
                    icb.POTENCIA_ICB  AS potencia_ponto,
                    icb.RENDIMENTO_ICB AS rendimento,
                    icb.NPSH
                FROM PECA p
                JOIN GRUPO_PECA gp        ON gp.ID_GRUPO_PECA = p.ID_GRUPO_PECA
                JOIN DADOS_HIDRAULICOS dh ON dh.ID_PECA = p.ID_PECA
                JOIN MODELO_BOMBA mb      ON mb.ID_MODELO_BOMBA = dh.ID_MODELO_BOMBA
                JOIN ITEM_CURVA_BOMBA icb ON icb.ID_MODELO_BOMBA = mb.ID_MODELO_BOMBA
                WHERE p.ATIVO = 1
                ORDER BY p.ID_PECA, icb.VAZAO_ICB
            """)
            result['curvas'] = [dict(r) for r in cur.fetchall()]
        except sqlite3.OperationalError:
            pass  # Tabelas de bomba ausentes (não é biblioteca de bombas)

        # Propriedades personalizadas
        try:
            cur.execute("""
                SELECT
                    p.ID_PECA,
                    p.NOME_PECA,
                    gprop.NOME  AS grupo,
                    prop.NOME   AS propriedade,
                    vprop.VALOR
                FROM VALOR_PROPRIEDADE_PERSONALIZADA vprop
                JOIN PROPRIEDADE_PERSONALIZADA prop
                    ON prop.ID_PROPRIEDADE_PERSONALIZADA = vprop.ID_PROPRIEDADE_PERSONALIZADA
                JOIN GRUPO_PROPRIEDADE_PERSONALIZADA gprop
                    ON gprop.ID_GRUPO_PROPRIEDADE_PERSONALIZADA = prop.ID_GRUPO_PROPRIEDADE_PERSONALIZADA
                JOIN PECA p ON p.ID_PECA = vprop.ID_PECA
                ORDER BY p.ID_PECA, prop.NOME
            """)
            result['propriedades'] = [dict(r) for r in cur.fetchall()]
        except sqlite3.OperationalError:
            pass

    finally:
        con.close()
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return result


SENTINELAS = (-2147483647, -1.7976931348623157e+308)


def _sem_sentinela(v):
    """
    Sentinela do AltoQi → None.

    O AltoQi não usa `NULL` para "não definido": grava `-2147483647` em coluna
    inteira e `-1.7976931348623157e+308` (`-DBL_MAX`) em coluna real. Na Amanco
    são 963 das 1.168 peças em `DIAMETRO_PECA` e 963 em `COMPRIMENTO_PECA`.

    Sem esta conversão o mapa entrega `-1.8e308` como se fosse medida, e
    qualquer aritmética a jusante produz lixo — `IS NULL` não encontra esses
    valores e um `if peca['comprimento_cm']:` os considera verdadeiros.
    """
    return None if v in SENTINELAS else v


def build_product_map(aq_data):
    """
    Organiza os dados do .aq em um mapa por grupo:
      { nome_gp → { 'serie': str, 'pecas': [ { id, nome, specs, curva_pts } ] } }

    Útil para build_catalog.py cruzar com os slugs dos IFCs.

    ⚠️ `diametro_codigo` **não é medida** — é o código de diâmetro do AltoQi
    (8 = 40 mm, 9 = 50 mm, 12 = 100 mm…). A chave se chamava `diametro_cm` até
    2026-09-02, o que afirmava centímetro e estava errado. As outras três
    (`comprimento_cm`, `altura_cm`, `largura_cm`) são centímetro de verdade.
    Todas as quatro passam por `_sem_sentinela`.
    """
    # Mapa de propriedades por peça
    props_by_peca = {}
    for p in aq_data['propriedades']:
        pid = p['ID_PECA']
        if pid not in props_by_peca:
            props_by_peca[pid] = {}
        props_by_peca[pid][p['propriedade']] = p['VALOR']

    # Mapa de curvas por peça
    curves_by_peca = {}
    for pt in aq_data['curvas']:
        pid = pt['ID_PECA']
        if pid not in curves_by_peca:
            curves_by_peca[pid] = []
        curves_by_peca[pid].append([
            round(pt['vazao'], 3),
            round(pt['altura'], 3),
            round(pt['potencia_ponto'] or 0, 3),
            round(pt['rendimento'] or 0, 1),
        ])

    # Mapa de grupos
    grupos_by_id = {g['ID_GRUPO_PECA']: g for g in aq_data['grupos']}

    product_map = {}
    for p in aq_data['pecas']:
        gid = p['ID_GRUPO_PECA']
        if gid not in grupos_by_id:
            continue
        nome_gp = grupos_by_id[gid]['NOME_GP']
        if nome_gp not in product_map:
            product_map[nome_gp] = {'serie': nome_gp, 'pecas': []}

        pid = p['ID_PECA']
        product_map[nome_gp]['pecas'].append({
            'id': pid,
            'nome': p['NOME_PECA'],
            'conexoes': p.get('DESCRICAO_DADOS', ''),
            'diametro_codigo': _sem_sentinela(p.get('DIAMETRO_PECA')),
            'comprimento_cm': _sem_sentinela(p.get('COMPRIMENTO_PECA')),
            'altura_cm': _sem_sentinela(p.get('ALTURA_PECA')),
            'largura_cm': _sem_sentinela(p.get('LARGURA_PECA')),
            'specs': props_by_peca.get(pid, {}),
            'curva_pts': curves_by_peca.get(pid),
        })

    return product_map


# ─── Metadados do catálogo ────────────────────────────────────────────────────

def read_classes(con):
    """
    NOME_CLASSE de CLASSE_SIMBOLOGIA_3D — o padrão observado é
    "FABRICANTE - Linha de Produto" (ex: 'AMANCO - PVC Esgoto SN').

    É a fonte mais confiável de fabricante: presente nas três bibliotecas
    testadas, enquanto PECA.BIBLIOTECA estava vazia em todas elas.
    """
    try:
        return [r[0] for r in con.execute(
            "SELECT DISTINCT NOME_CLASSE FROM CLASSE_SIMBOLOGIA_3D "
            "WHERE NOME_CLASSE IS NOT NULL AND NOME_CLASSE != ''")]
    except sqlite3.OperationalError:
        return []


def _titlecase(s):
    """DANCOR → Dancor; preserva palavras que já têm capitalização mista."""
    out = []
    for w in s.split():
        out.append(w.capitalize() if (w.isupper() or w.islower()) else w)
    return ' '.join(out)


def peek_metadata(aq_path):
    """
    Lê apenas os metadados do catálogo, sem tocar na geometria.

    Retorna: fabricante, linhas (sufixos das classes), grupos, has_curves,
             n_pecas, n_simbologias, schema.
    """
    meta = {'fabricante': '', 'linhas': [], 'grupos': [], 'has_curves': False,
            'n_pecas': 0, 'n_simbologias': 0, 'schema': None}
    try:
        con, tmp = open_aq(aq_path)
    except FileNotFoundError:
        raise                       # caminho errado é erro do operador, não "sem metadados"
    except Exception:
        return meta                 # arquivo existe mas não é .aq legível: o caller decide

    try:
        classes = read_classes(con)
        prefixos, sufixos = [], []
        for c in classes:
            if ' - ' in c:
                pre, suf = c.split(' - ', 1)
                prefixos.append(pre.strip())
                sufixos.append(suf.strip())
            else:
                sufixos.append(c.strip())
        # Fabricante: prefixo comum a todas as classes
        if prefixos and len(set(prefixos)) == 1:
            meta['fabricante'] = _titlecase(prefixos[0])
        meta['linhas'] = sufixos

        # PECA.BIBLIOTECA como reforço (raramente preenchida)
        if not meta['fabricante']:
            try:
                r = con.execute("SELECT BIBLIOTECA FROM PECA WHERE BIBLIOTECA IS NOT NULL "
                                "AND BIBLIOTECA != '' LIMIT 1").fetchone()
                if r:
                    meta['fabricante'] = r[0].strip()
            except sqlite3.OperationalError:
                pass

        for sql, key in (
            ('SELECT NOME_GP FROM GRUPO_PECA WHERE ATIVO=1 ORDER BY ID_GRUPO_PECA', 'grupos'),
        ):
            try:
                meta[key] = [r[0] for r in con.execute(sql)]
            except sqlite3.OperationalError:
                pass

        for sql, key in (('SELECT COUNT(*) FROM PECA', 'n_pecas'),
                         ('SELECT COUNT(*) FROM SIMBOLOGIA_3D', 'n_simbologias')):
            try:
                meta[key] = con.execute(sql).fetchone()[0]
            except sqlite3.OperationalError:
                pass

        try:
            meta['has_curves'] = con.execute(
                'SELECT 1 FROM ITEM_CURVA_BOMBA LIMIT 1').fetchone() is not None
        except sqlite3.OperationalError:
            pass
        try:
            meta['schema'] = con.execute(
                'SELECT VERSAO FROM VERSAO_BANCO_CADASTRO LIMIT 1').fetchone()[0]
        except sqlite3.OperationalError:
            pass
    finally:
        con.close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    return meta


# ─── Geometria 3D embutida (OQ3D) ────────────────────────────────────────────

def extract_simbologias(aq_path):
    """
    Lê SIMBOLOGIA_3D e o vínculo determinístico com as peças.

    Este vínculo (PECA → PECA_SIMBOLOGIA_3D → SIMBOLOGIA_3D) é uma chave
    estrangeira: dispensa o file_map e o matching por nome que o caminho IFC
    exige. Várias peças podem compartilhar a mesma simbologia.

    Retorna:
      simbologias: { id → { nome, grupo, classe, blob, imagem } }
      por_peca:    { id_peca → id_simbologia_3d }
    """
    con, tmp_dir = open_aq(aq_path)
    simbologias, por_peca = {}, {}
    try:
        try:
            rows = con.execute("""
                SELECT s.ID_SIMBOLOGIA_3D, s.NOME,
                       CAST(s.SIMBOLOGIA_3D AS BLOB), CAST(s.IMAGEM AS BLOB),
                       g.NOME_GRUPO, c.NOME_CLASSE
                FROM SIMBOLOGIA_3D s
                LEFT JOIN GRUPO_SIMBOLOGIA_3D g
                       ON g.ID_GRUPO_SIMBOLOGIA_3D = s.ID_GRUPO_SIMBOLOGIA_3D
                LEFT JOIN CLASSE_SIMBOLOGIA_3D c
                       ON c.ID_CLASSE_SIMBOLOGIA_3D = g.ID_CLASSE
            """).fetchall()
        except sqlite3.OperationalError:
            rows = con.execute(
                'SELECT ID_SIMBOLOGIA_3D, NOME, '
                'CAST(SIMBOLOGIA_3D AS BLOB), CAST(IMAGEM AS BLOB), '
                'NULL, NULL FROM SIMBOLOGIA_3D').fetchall()

        for r in rows:
            blob = r[2]
            img = r[3]
            simbologias[r[0]] = {
                'nome': r[1] or '',
                # CAST AS BLOB na query garante bytes — sem re-encode, que
                # com cp1252 não seria reversível
                'blob': blob,
                'imagem': img,
                'grupo': r[4] or '',
                'classe': r[5] or '',
            }

        try:
            for pid, sid in con.execute(
                    'SELECT ID_PECA, ID_SIMBOLOGIA_3D FROM PECA_SIMBOLOGIA_3D'):
                por_peca[pid] = sid
        except sqlite3.OperationalError:
            pass
    finally:
        con.close()
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    return simbologias, por_peca


def main():
    parser = argparse.ArgumentParser(description='Lê biblioteca AltoQi .aq → JSON')
    parser.add_argument('aq_file', help='Arquivo .aq de entrada')
    parser.add_argument('output', nargs='?', help='Arquivo JSON de saída')
    parser.add_argument('--meta', action='store_true',
                        help='Mostra só os metadados (fabricante, linhas, contagens)')
    args = parser.parse_args()

    if args.meta or not args.output:
        meta = peek_metadata(args.aq_file)
        print(f'fabricante   : {meta["fabricante"] or "(não identificado)"}')
        print(f'linhas       : {", ".join(meta["linhas"]) or "(nenhuma)"}')
        print(f'peças        : {meta["n_pecas"]}')
        print(f'simbologias  : {meta["n_simbologias"]}')
        print(f'grupos       : {len(meta["grupos"])}')
        print(f'curvas Q-H   : {"sim" if meta["has_curves"] else "não"}')
        print(f'schema       : {meta["schema"]}')
        return

    data = extract(args.aq_file)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    print(f'Extraídos: {len(data["grupos"])} grupos, {len(data["pecas"])} peças, '
          f'{len(data["curvas"])} pontos de curva, {len(data["propriedades"])} propriedades')
    print(f'Saída: {args.output}')


if __name__ == '__main__':
    main()
