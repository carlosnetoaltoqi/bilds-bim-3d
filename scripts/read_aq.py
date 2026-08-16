#!/usr/bin/env python3
"""
read_aq.py — Extrai dados de uma biblioteca BIM AltoQi (.aq) para JSON.

Um .aq pode ser de dois tipos:
  1. ZIP contendo SQLite — caso mais comum ao baixar do AltoQi
  2. SQLite direto — ocorre quando o .aq foi extraído de outro ZIP

Sempre tenta SQLite direto primeiro (método robusto).
Encoding: latin-1 (Windows-1252) — sempre configurar antes de qualquer query.

Uso:
  python3 scripts/read_aq.py <arquivo.aq> <saida.json>
"""
import sys
import json
import sqlite3
import zipfile
import os
import shutil
import tempfile
import argparse


def open_aq(aq_path):
    """
    Abre um .aq como SQLite. Tenta direto primeiro, cai para ZIP se falhar.
    Retorna (connection, tmp_dir_or_None).
    Caller deve fechar a connection e remover tmp_dir se não for None.
    """
    # Tentativa 1: SQLite direto
    try:
        con = sqlite3.connect(aq_path)
        con.text_factory = lambda b: b.decode('latin-1')
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
    con.text_factory = lambda b: b.decode('latin-1')
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


def build_product_map(aq_data):
    """
    Organiza os dados do .aq em um mapa por grupo:
      { nome_gp → { 'serie': str, 'pecas': [ { id, nome, specs, curva_pts } ] } }

    Útil para build_catalog.py cruzar com os slugs dos IFCs.
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
            'diametro_cm': p.get('DIAMETRO_PECA'),
            'comprimento_cm': p.get('COMPRIMENTO_PECA'),
            'altura_cm': p.get('ALTURA_PECA'),
            'largura_cm': p.get('LARGURA_PECA'),
            'specs': props_by_peca.get(pid, {}),
            'curva_pts': curves_by_peca.get(pid),
        })

    return product_map


def main():
    parser = argparse.ArgumentParser(description='Lê biblioteca AltoQi .aq → JSON')
    parser.add_argument('aq_file', help='Arquivo .aq de entrada')
    parser.add_argument('output', help='Arquivo JSON de saída')
    args = parser.parse_args()

    data = extract(args.aq_file)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    print(f'Extraídos: {len(data["grupos"])} grupos, {len(data["pecas"])} peças, '
          f'{len(data["curvas"])} pontos de curva, {len(data["propriedades"])} propriedades')
    print(f'Saída: {args.output}')


if __name__ == '__main__':
    main()
