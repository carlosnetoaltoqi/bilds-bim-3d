"""read_aq.py — abrir o .aq e extrair catálogo e geometria."""
import os
import sqlite3

import pytest

import read_aq


def test_open_aq_inexistente_nao_cria_arquivo(tmp_path):
    alvo = tmp_path / 'nao_existe.aq'
    with pytest.raises(FileNotFoundError):
        read_aq.open_aq(str(alvo))
    assert not alvo.exists()   # C2: sqlite3.connect criava um arquivo vazio


def test_open_aq_nem_sqlite_nem_zip(tmp_path):
    lixo = tmp_path / 'lixo.aq'
    lixo.write_bytes(b'nada a ver' * 100)
    with pytest.raises(ValueError, match='nem um ZIP'):
        read_aq.open_aq(str(lixo))


def test_open_aq_abre_somente_leitura(akato_aq):
    con, tmp = read_aq.open_aq(akato_aq)
    try:
        assert tmp is None                   # SQLite direto, sem extração
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            con.execute('CREATE TABLE _teste (a)')
    finally:
        con.close()


def test_extract_akato_contagens_e_cp1252(akato_aq):
    data = read_aq.extract(akato_aq)
    assert len(data['grupos']) == 83
    assert len(data['pecas']) == 262
    assert len(data['propriedades']) == 1756
    assert data['curvas'] == []              # não é biblioteca de bombas
    nomes = [g['NOME_GP'] for g in data['grupos']]
    assert 'Tubo De Pvc Soldável 6M' in nomes
    assert 'Curva 45° Longa Soldável' in nomes
    textos = nomes + [p['NOME_PECA'] or '' for p in data['pecas']] \
        + [p['VALOR'] or '' for p in data['propriedades']]
    for t in textos:
        # latin-1 no lugar de cp1252 deixaria controles C1 (\x80–\x9f); erro
        # de decodificação deixaria U+FFFD.
        assert not any(0x80 <= ord(c) <= 0x9f for c in t), repr(t)
        assert '�' not in t, repr(t)


def test_extract_simbologias_akato(akato_aq):
    sims, por_peca = read_aq.extract_simbologias(akato_aq)
    assert len(sims) == 262 and len(por_peca) == 262
    assert set(por_peca.values()) <= set(sims)
    for s in sims.values():
        assert isinstance(s['blob'], bytes) and s['blob']
        assert isinstance(s['nome'], str)
    assert any(s['classe'].startswith('AKATO - ') for s in sims.values())


def test_build_product_map_akato(akato_aq):
    data = read_aq.extract(akato_aq)
    pm = read_aq.build_product_map(data)
    assert len(pm) == 83
    assert sum(len(g['pecas']) for g in pm.values()) == 262
