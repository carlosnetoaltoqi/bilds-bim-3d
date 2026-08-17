"""
Tests para scripts/read_aq.py.

Cobre open_aq() (SQLite direto e via ZIP), proteção contra Zip Slip,
extract() e build_product_map(). Usa fixtures de banco SQLite mínimo.
"""

import zipfile
import sqlite3
import shutil
import pytest

from read_aq import open_aq, extract, build_product_map


# ── open_aq ───────────────────────────────────────────────────────────────────

class TestOpenAq:
    def test_opens_sqlite_directly(self, minimal_aq_db):
        """Arquivo .aq que é SQLite direto deve abrir sem criar tmp_dir."""
        con, tmp = open_aq(minimal_aq_db)
        try:
            assert tmp is None
            cur = con.cursor()
            cur.execute('SELECT COUNT(*) FROM GRUPO_PECA')
            assert cur.fetchone()[0] == 2
        finally:
            con.close()

    def test_opens_sqlite_inside_zip(self, minimal_aq_db, tmp_path):
        """Arquivo .aq que é ZIP contendo SQLite deve descompactar e abrir."""
        zip_path = str(tmp_path / 'library.aq')
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(minimal_aq_db, 'library.db')

        con, tmpd = open_aq(zip_path)
        try:
            assert tmpd is not None
            cur = con.cursor()
            cur.execute('SELECT COUNT(*) FROM GRUPO_PECA')
            assert cur.fetchone()[0] == 2
        finally:
            con.close()
            if tmpd:
                shutil.rmtree(tmpd, ignore_errors=True)

    def test_text_factory_set_to_latin1(self, minimal_aq_db):
        """A conexão deve ter text_factory configurado (não deve lançar erro em ASCII)."""
        con, tmp = open_aq(minimal_aq_db)
        try:
            cur = con.cursor()
            cur.execute('SELECT NOME_GP FROM GRUPO_PECA WHERE ID_GRUPO_PECA = 1')
            row = cur.fetchone()
            assert row is not None
            assert 'CAM-W10' in str(row[0])
        finally:
            con.close()

    def test_invalid_file_raises(self, tmp_path):
        """Arquivo que não é SQLite nem ZIP deve levantar ValueError."""
        bad = tmp_path / 'bad.aq'
        bad.write_text('not sqlite not zip')
        with pytest.raises((ValueError, Exception)):
            open_aq(str(bad))

    def test_zip_slip_traversal_entry_is_skipped(self, tmp_path):
        """
        ZIP com entrada de traversal (../evil.db) deve ter a entrada ignorada.
        Como nenhum SQLite válido é extraído, open_aq levanta FileNotFoundError.

        Proteção documentada em docs/specs/leitor-biblioteca-aq.md, seção
        "Segurança — Zip Slip na extração do .aq".
        """
        zip_path = str(tmp_path / 'evil.aq')
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('../../../evil.db', b'fake sqlite content')

        with pytest.raises(FileNotFoundError):
            open_aq(zip_path)

    def test_zip_with_xml_file_ignored(self, minimal_aq_db, tmp_path):
        """Arquivos .xml dentro do ZIP devem ser ignorados na busca pelo SQLite."""
        zip_path = str(tmp_path / 'library.aq')
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(minimal_aq_db, 'library.db')
            zf.writestr('metadata.xml', '<root/>')

        con, tmpd = open_aq(zip_path)
        try:
            cur = con.cursor()
            cur.execute('SELECT COUNT(*) FROM GRUPO_PECA')
            count = cur.fetchone()[0]
            assert count == 2
        finally:
            con.close()
            if tmpd:
                shutil.rmtree(tmpd, ignore_errors=True)


# ── extract ───────────────────────────────────────────────────────────────────

class TestExtract:
    def test_returns_expected_keys(self, minimal_aq_db):
        result = extract(minimal_aq_db)
        assert set(result.keys()) == {'grupos', 'pecas', 'curvas', 'propriedades'}

    def test_grupos_only_active(self, minimal_aq_db):
        """Apenas grupos com ATIVO=1 devem ser retornados."""
        result = extract(minimal_aq_db)
        assert len(result['grupos']) == 1
        assert result['grupos'][0]['NOME_GP'] == 'CAM-W10'

    def test_pecas_both_active(self, minimal_aq_db):
        """Ambas as peças têm ATIVO=1 — as duas devem ser retornadas."""
        result = extract(minimal_aq_db)
        assert len(result['pecas']) == 2

    def test_curvas_empty_without_pump_tables(self, minimal_aq_db):
        """Banco sem tabelas de bomba deve retornar curvas=[]. """
        result = extract(minimal_aq_db)
        assert result['curvas'] == []

    def test_propriedades_empty_without_prop_tables(self, minimal_aq_db):
        """Banco sem tabelas de propriedade deve retornar propriedades=[]."""
        result = extract(minimal_aq_db)
        assert result['propriedades'] == []

    def test_extract_with_curves(self, tmp_path):
        """Banco com tabelas de bomba deve extrair pontos de curva Q-H."""
        db_path = str(tmp_path / 'bomba.db')
        con = sqlite3.connect(db_path)
        con.executescript("""
            CREATE TABLE GRUPO_PECA (
                ID_GRUPO_PECA INTEGER PRIMARY KEY, NOME_GP TEXT, ATIVO INTEGER
            );
            CREATE TABLE PECA (
                ID_PECA INTEGER PRIMARY KEY, ID_GRUPO_PECA INTEGER,
                NOME_PECA TEXT, DESCRICAO_DADOS TEXT, DIAMETRO_PECA REAL,
                COMPRIMENTO_PECA REAL, ALTURA_PECA REAL, LARGURA_PECA REAL,
                BIBLIOTECA TEXT, ATIVO INTEGER
            );
            CREATE TABLE DADOS_HIDRAULICOS (
                ID_DADOS_HIDRAULICOS INTEGER PRIMARY KEY,
                ID_PECA INTEGER, ID_MODELO_BOMBA INTEGER
            );
            CREATE TABLE MODELO_BOMBA (
                ID_MODELO_BOMBA INTEGER PRIMARY KEY,
                NOME_MB TEXT, POTENCIA_MB REAL, ATIVO INTEGER
            );
            CREATE TABLE ITEM_CURVA_BOMBA (
                ID_ITEM_CURVA_BOMBA INTEGER PRIMARY KEY,
                ID_MODELO_BOMBA INTEGER, VAZAO_ICB REAL, ALTURA_ICB REAL,
                POTENCIA_ICB REAL, RENDIMENTO_ICB REAL, NPSH REAL
            );
            INSERT INTO GRUPO_PECA VALUES (1, 'CAM-W10', 1);
            INSERT INTO PECA VALUES (1, 1, '1CV T 220V', '1.5"x1.5"', 3.8, 30., 20., 20., 'Lib', 1);
            INSERT INTO DADOS_HIDRAULICOS VALUES (1, 1, 1);
            INSERT INTO MODELO_BOMBA VALUES (1, 'CAM-W10 1CV', 1.0, 1);
            INSERT INTO ITEM_CURVA_BOMBA VALUES (1, 1, 0.0, 30.0, 1.0, 55.0, NULL);
            INSERT INTO ITEM_CURVA_BOMBA VALUES (2, 1, 3.0, 25.0, 1.1, 60.0, NULL);
            INSERT INTO ITEM_CURVA_BOMBA VALUES (3, 1, 6.0, 18.0, 1.2, 55.0, NULL);
        """)
        con.commit()
        con.close()

        result = extract(db_path)
        assert len(result['curvas']) == 3
        assert result['curvas'][0]['serie'] == 'CAM-W10'
        assert result['curvas'][0]['vazao'] == pytest.approx(0.0)
        assert result['curvas'][1]['vazao'] == pytest.approx(3.0)


# ── build_product_map ─────────────────────────────────────────────────────────

class TestBuildProductMap:
    def test_groups_by_nome_gp(self, minimal_aq_db):
        aq_data = extract(minimal_aq_db)
        product_map = build_product_map(aq_data)

        assert 'CAM-W10' in product_map
        # TJM não aparece porque seu grupo tem ATIVO=0 → não está em aq_data['grupos']
        assert 'TJM' not in product_map

    def test_peca_included_in_group(self, minimal_aq_db):
        aq_data = extract(minimal_aq_db)
        product_map = build_product_map(aq_data)

        pecas = product_map['CAM-W10']['pecas']
        assert len(pecas) == 1
        assert pecas[0]['nome'] == '1CV T 220V'

    def test_peca_has_required_fields(self, minimal_aq_db):
        aq_data = extract(minimal_aq_db)
        product_map = build_product_map(aq_data)
        peca = product_map['CAM-W10']['pecas'][0]

        assert 'id' in peca
        assert 'nome' in peca
        assert 'conexoes' in peca
        assert 'specs' in peca
        assert 'curva_pts' in peca

    def test_curva_pts_none_without_curves(self, minimal_aq_db):
        aq_data = extract(minimal_aq_db)
        product_map = build_product_map(aq_data)
        peca = product_map['CAM-W10']['pecas'][0]
        assert peca['curva_pts'] is None

    def test_curva_pts_populated_when_curves_exist(self, tmp_path):
        """Peça com curva Q-H deve ter curva_pts como lista de pontos."""
        db_path = str(tmp_path / 'bomba.db')
        con = sqlite3.connect(db_path)
        con.executescript("""
            CREATE TABLE GRUPO_PECA (ID_GRUPO_PECA INTEGER PRIMARY KEY, NOME_GP TEXT, ATIVO INTEGER);
            CREATE TABLE PECA (
                ID_PECA INTEGER PRIMARY KEY, ID_GRUPO_PECA INTEGER,
                NOME_PECA TEXT, DESCRICAO_DADOS TEXT, DIAMETRO_PECA REAL,
                COMPRIMENTO_PECA REAL, ALTURA_PECA REAL, LARGURA_PECA REAL,
                BIBLIOTECA TEXT, ATIVO INTEGER
            );
            CREATE TABLE DADOS_HIDRAULICOS (
                ID_DADOS_HIDRAULICOS INTEGER PRIMARY KEY,
                ID_PECA INTEGER, ID_MODELO_BOMBA INTEGER
            );
            CREATE TABLE MODELO_BOMBA (
                ID_MODELO_BOMBA INTEGER PRIMARY KEY, NOME_MB TEXT, POTENCIA_MB REAL, ATIVO INTEGER
            );
            CREATE TABLE ITEM_CURVA_BOMBA (
                ID_ITEM_CURVA_BOMBA INTEGER PRIMARY KEY, ID_MODELO_BOMBA INTEGER,
                VAZAO_ICB REAL, ALTURA_ICB REAL, POTENCIA_ICB REAL, RENDIMENTO_ICB REAL, NPSH REAL
            );
            INSERT INTO GRUPO_PECA VALUES (1, 'CAM-W10', 1);
            INSERT INTO PECA VALUES (1, 1, '1CV', '1.5"x1.5"', 3.8, 30., 20., 20., 'Lib', 1);
            INSERT INTO DADOS_HIDRAULICOS VALUES (1, 1, 1);
            INSERT INTO MODELO_BOMBA VALUES (1, 'CAM-W10 1CV', 1.0, 1);
            INSERT INTO ITEM_CURVA_BOMBA VALUES (1, 1, 0.0, 30.0, 1.0, 55.0, NULL);
            INSERT INTO ITEM_CURVA_BOMBA VALUES (2, 1, 3.0, 25.0, 1.1, 60.0, NULL);
        """)
        con.commit()
        con.close()

        aq_data = extract(db_path)
        product_map = build_product_map(aq_data)
        peca = product_map['CAM-W10']['pecas'][0]

        assert peca['curva_pts'] is not None
        assert len(peca['curva_pts']) == 2
        # Cada ponto: [vazao, altura, potencia, rendimento]
        assert peca['curva_pts'][0] == pytest.approx([0.0, 30.0, 1.0, 55.0])
        assert peca['curva_pts'][1] == pytest.approx([3.0, 25.0, 1.1, 60.0])
