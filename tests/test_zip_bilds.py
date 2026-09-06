"""
zip_bilds.py — `build_zip_bilds` monta um ZIP conforme o contrato bilds.com.

Testa a função diretamente (sem Chromium) e o CLI com um catálogo mínimo.
Os testes marcados `aq` precisam de `input/` e pulam no CI.
"""
import json
import os
import subprocess
import sys
import tempfile
import zipfile

import pytest

from bim_pipeline.saida import zip_bilds


# ─── helpers ─────────────────────────────────────────────────────────────────

def _catalog_minimo(geo_dir: str) -> dict:
    """Catálogo com um produto e um arquivo de geometria criado em geo_dir."""
    geo_nome = 'peca-a.json'
    geo = {'pos': [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.5, 1.0, 0.0], 'col': [], 'idx': []}
    with open(os.path.join(geo_dir, geo_nome), 'w') as f:
        json.dump(geo, f)
    return {
        'slug': 'teste',
        'titulo': 'Teste',
        'fabricante': 'Fabricante',
        'descricao': '',
        'layout': 'catalog-grid',
        'filtros': ['Serie-A'],
        'produtos': [
            {'id': 'peca-a', 'nome': 'Peça A', 'serie': 'Serie-A',
             'geo': geo_nome, 'specs': {}, 'curva': None},
        ],
    }


# ─── build_zip_bilds ──────────────────────────────────────────────────────────

def test_zip_bilds_estrutura():
    """ZIP tem manifest.json, catalog.json e geo/; campos obrigatórios no manifest."""
    with tempfile.TemporaryDirectory() as tmp:
        geo_dir = os.path.join(tmp, 'geo')
        os.makedirs(geo_dir)
        catalog = _catalog_minimo(geo_dir)
        zip_path = os.path.join(tmp, 'saida.zip')
        zip_bilds.build_zip_bilds(catalog, zip_path, geo_dir)

        assert os.path.exists(zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert 'manifest.json' in names
            assert 'catalog.json' in names
            assert 'geo/peca-a.json' in names
            # sem thumbs_dir → thumbs/ não entra
            assert not any(n.startswith('thumbs/') for n in names)

            manifest = json.loads(zf.read('manifest.json'))
            assert manifest['slug'] == 'teste'
            assert manifest['title'] == 'Teste'
            assert manifest['manufacturer'] == 'Fabricante'
            assert manifest['layout'] == 'catalog-grid'
            assert manifest['productCount'] == 1
            assert manifest['thumbCount'] == 0

            cat = json.loads(zf.read('catalog.json'))
            assert cat['produtos'][0]['geo'] == 'peca-a.json'


def test_zip_bilds_geo_compartilhada():
    """Dois produtos com mesma geometria: o arquivo entra no ZIP só uma vez."""
    with tempfile.TemporaryDirectory() as tmp:
        geo_dir = os.path.join(tmp, 'geo')
        os.makedirs(geo_dir)
        geo = {'pos': [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.5, 1.0, 0.0], 'col': [], 'idx': []}
        with open(os.path.join(geo_dir, 'peca.json'), 'w') as f:
            json.dump(geo, f)
        catalog = {
            'slug': 's', 'titulo': 'T', 'fabricante': 'F', 'descricao': '',
            'layout': 'series-rows', 'filtros': [],
            'produtos': [
                {'id': 'a', 'nome': 'A', 'serie': '', 'geo': 'peca.json', 'specs': {}, 'curva': None},
                {'id': 'b', 'nome': 'B', 'serie': '', 'geo': 'peca.json', 'specs': {}, 'curva': None},
            ],
        }
        zip_path = os.path.join(tmp, 'saida.zip')
        zip_bilds.build_zip_bilds(catalog, zip_path, geo_dir)
        with zipfile.ZipFile(zip_path) as zf:
            assert zf.namelist().count('geo/peca.json') == 1


def test_zip_bilds_thumbs():
    """Com thumbs_dir preenchido e thumb anotado no produto, miniatura entra no ZIP."""
    with tempfile.TemporaryDirectory() as tmp:
        geo_dir = os.path.join(tmp, 'geo')
        thumbs_dir = os.path.join(tmp, 'thumbs')
        os.makedirs(geo_dir)
        os.makedirs(thumbs_dir)
        geo = {'pos': [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.5, 1.0, 0.0], 'col': [], 'idx': []}
        with open(os.path.join(geo_dir, 'peca.json'), 'w') as f:
            json.dump(geo, f)
        # simula a anotação que build_thumbs faz no produto
        with open(os.path.join(thumbs_dir, 'peca.webp'), 'wb') as f:
            f.write(b'RIFF\x00\x00\x00\x00WEBP')   # cabeçalho mínimo (não é WebP válido, mas o ZipFile não valida)
        catalog = {
            'slug': 's', 'titulo': 'T', 'fabricante': 'F', 'descricao': '',
            'layout': 'series-rows', 'filtros': [],
            'produtos': [
                {'id': 'a', 'nome': 'A', 'serie': '', 'geo': 'peca.json',
                 'thumb': 'peca.webp', 'specs': {}, 'curva': None},
            ],
        }
        zip_path = os.path.join(tmp, 'saida.zip')
        zip_bilds.build_zip_bilds(catalog, zip_path, geo_dir, thumbs_dir=thumbs_dir)
        with zipfile.ZipFile(zip_path) as zf:
            assert 'thumbs/peca.webp' in zf.namelist()
            manifest = json.loads(zf.read('manifest.json'))
            assert manifest['thumbCount'] == 1


def test_zip_bilds_geo_ausente(tmp_path):
    """Geometria referenciada mas ausente em disco: não entra no ZIP (sem crash)."""
    geo_dir = str(tmp_path / 'geo')
    os.makedirs(geo_dir)
    catalog = {
        'slug': 's', 'titulo': 'T', 'fabricante': 'F', 'descricao': '',
        'layout': 'series-rows', 'filtros': [],
        'produtos': [
            {'id': 'a', 'nome': 'A', 'serie': '', 'geo': 'nao-existe.json', 'specs': {}, 'curva': None},
        ],
    }
    zip_path = str(tmp_path / 'saida.zip')
    zip_bilds.build_zip_bilds(catalog, zip_path, geo_dir)
    with zipfile.ZipFile(zip_path) as zf:
        assert 'geo/nao-existe.json' not in zf.namelist()


# ─── CLI ─────────────────────────────────────────────────────────────────────

AQ_AKATO = os.path.join(os.path.dirname(__file__), '..', 'input', 'Akato', 'Akato.aq')


@pytest.mark.skipif(not os.path.exists(AQ_AKATO), reason='input/Akato/Akato.aq não encontrado')
@pytest.mark.aq
def test_cli_akato(tmp_path):
    """CLI com a Akato real: ZIP tem os arquivos obrigatórios e o manifest é válido."""
    saida = str(tmp_path / 'saida.zip')
    r = subprocess.run(
        [sys.executable, '-m', 'bim_pipeline.cli.zip_bilds', os.path.abspath(AQ_AKATO),
         '--saida', saida, '--skip-thumbs'],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert os.path.exists(saida)
    with zipfile.ZipFile(saida) as zf:
        names = zf.namelist()
        assert 'manifest.json' in names
        assert 'catalog.json' in names
        manifest = json.loads(zf.read('manifest.json'))
        assert manifest['productCount'] > 0
        assert all(f'geo/{p["geo"]}' in names
                   for p in json.loads(zf.read('catalog.json'))['produtos'])
