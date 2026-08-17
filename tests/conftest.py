"""Configuração global de testes — path e fixtures compartilhados."""

import sys
import os
import sqlite3

import pytest

# Adiciona scripts/ ao sys.path para que os módulos do projeto sejam importáveis
# diretamente (ex: `from parse_ifc import ...`).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))


@pytest.fixture
def minimal_aq_db(tmp_path):
    """
    Cria um arquivo SQLite mínimo com o schema AltoQi (.aq direto).

    Contém:
      - 2 grupos: CAM-W10 (ativo) e TJM (inativo)
      - 2 peças: ambas ATIVO=1, mas peca 2 está no grupo inativo

    Útil para testar open_aq(), extract() e build_product_map().
    """
    db_path = tmp_path / 'library.db'
    con = sqlite3.connect(str(db_path))
    con.executescript("""
        CREATE TABLE GRUPO_PECA (
            ID_GRUPO_PECA INTEGER PRIMARY KEY,
            NOME_GP TEXT,
            ATIVO INTEGER
        );
        CREATE TABLE PECA (
            ID_PECA INTEGER PRIMARY KEY,
            ID_GRUPO_PECA INTEGER,
            NOME_PECA TEXT,
            DESCRICAO_DADOS TEXT,
            DIAMETRO_PECA REAL,
            COMPRIMENTO_PECA REAL,
            ALTURA_PECA REAL,
            LARGURA_PECA REAL,
            BIBLIOTECA TEXT,
            ATIVO INTEGER
        );
        INSERT INTO GRUPO_PECA VALUES (1, 'CAM-W10', 1);
        INSERT INTO GRUPO_PECA VALUES (2, 'TJM', 0);
        INSERT INTO PECA VALUES (1, 1, '1CV T 220V', '1.5" x 1.5"',
                                 3.8, 30.0, 20.0, 20.0, 'TestLib', 1);
        INSERT INTO PECA VALUES (2, 2, '2CV T 220V', '2" x 2"',
                                 5.0, 35.0, 25.0, 25.0, 'TestLib', 1);
    """)
    con.commit()
    con.close()
    return str(db_path)
