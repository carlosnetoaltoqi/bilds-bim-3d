"""bim_pipeline.saida.zip_bilds + a CLI — o único escritor do ZIP da bilds.com (S8/F1, ADR-012).

I1: miniaturas indisponíveis derrubam a geração, salvo --allow-no-thumbs/--skip-thumbs; thumbCount no manifest.
Nada fica persistido além do ZIP pedido. Testes com a fixture real usam `aq_pequena`.
"""
import json
import os
import zipfile

import pytest

from bim_pipeline.aq import oq3d, read_aq
from bim_pipeline.cli import zip_bilds as cli
from bim_pipeline.miniaturas import render
from bim_pipeline.saida import zip_bilds
from fixtures import FIXTURAS


def _catalog_minimo(geo_dir, serie='Serie-A', layout='catalog-grid'):
    os.makedirs(geo_dir, exist_ok=True)
    with open(os.path.join(geo_dir, 'peca-a.json'), 'w') as f:
        json.dump({'pos': [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.5, 1.0, 0.0], 'col': [], 'idx': []}, f)
    return {'slug': 'teste', 'titulo': 'Título <mini>', 'fabricante': 'Fab "X"', 'descricao': '',
            'layout': layout, 'filtros': [serie],
            'produtos': [{'id': 'peca-a', 'nome': 'Peça 1" <b>', 'serie': serie, 'geo': 'peca-a.json',
                          'potencia': None, 'conexoes': '', 'specs': {}, 'curva': None}]}


# ── build_zip_bilds ──────────────────────────────────────────────────────────

def test_zip_estrutura_e_manifest(tmp_path):
    geo_dir = str(tmp_path / 'geo')
    catalog = _catalog_minimo(geo_dir)
    zip_path = str(tmp_path / 'saida.zip')
    r = zip_bilds.build_zip_bilds(catalog, zip_path, geo_dir)
    assert r == {'geometrias': 1, 'ausentes': [], 'thumbs': 0}
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert {'manifest.json', 'catalog.json', 'geo/peca-a.json'} <= set(names)
        assert not any(n.startswith('thumbs/') for n in names)
        manifest = json.loads(zf.read('manifest.json'))
        assert manifest == {'slug': 'teste', 'title': 'Título <mini>', 'manufacturer': 'Fab "X"', 'description': '',
                            'layout': 'catalog-grid', 'filters': ['Serie-A'], 'productCount': 1, 'thumbCount': 0}
        assert json.loads(zf.read('catalog.json'))['produtos'][0]['geo'] == 'peca-a.json'


def test_zip_geo_compartilhada_entra_uma_vez_e_thumbs_contam(tmp_path):
    geo_dir = str(tmp_path / 'geo'); thumbs_dir = tmp_path / 'thumbs'
    catalog = _catalog_minimo(geo_dir)
    catalog['produtos'].append(dict(catalog['produtos'][0], id='p2', thumb='peca-a.webp'))
    catalog['produtos'][0]['thumb'] = 'peca-a.webp'
    thumbs_dir.mkdir()
    (thumbs_dir / 'peca-a.webp').write_bytes(b'RIFF....WEBP')
    zip_path = str(tmp_path / 'saida.zip')
    r = zip_bilds.build_zip_bilds(catalog, zip_path, geo_dir, thumbs_dir=str(thumbs_dir))
    with zipfile.ZipFile(zip_path) as zf:
        nomes = zf.namelist()
        manifest = json.loads(zf.read('manifest.json'))
    assert nomes.count('geo/peca-a.json') == 1 and nomes.count('thumbs/peca-a.webp') == 1
    assert manifest['productCount'] == 2 and manifest['thumbCount'] == 1 == r['thumbs']


def test_zip_geo_ausente_fica_fora_e_avisa(tmp_path):
    geo_dir = str(tmp_path / 'geo')
    catalog = _catalog_minimo(geo_dir)
    catalog['produtos'][0]['geo'] = 'nao-existe.json'
    avisos = []
    r = zip_bilds.build_zip_bilds(catalog, str(tmp_path / 's.zip'), geo_dir, avisar=avisos.append)
    assert r['ausentes'] == ['nao-existe.json'] and r['geometrias'] == 0
    assert avisos == ['AVISO: geo/nao-existe.json não encontrado — fora do ZIP']
    with zipfile.ZipFile(tmp_path / 's.zip') as zf:
        assert 'geo/nao-existe.json' not in zf.namelist()


def test_nome_zip_tem_slug_e_carimbo():
    import datetime
    assert zip_bilds.nome_zip('abc', datetime.datetime(2026, 9, 6, 8, 5)) == 'abc-202609060805.zip'


# ── gerar_zip / CLI (I1) ──────────────────────────────────────────────────────

@pytest.fixture
def sem_node(monkeypatch):
    monkeypatch.setattr(render, 'find_node', lambda: None)


def test_gerar_zip_sem_node_falha_por_padrao(saida, aq_pequena, sem_node):
    with pytest.raises(render.ThumbsError, match='Node >= 20'):
        zip_bilds.gerar_zip(aq_pequena, str(saida / 'a.zip'))
    assert not (saida / 'a.zip').exists()


def test_gerar_zip_allow_no_thumbs_segue_com_aviso(saida, aq_pequena, sem_node):
    n = FIXTURAS['aq_pequena']['pecas']
    msgs = []
    r = zip_bilds.gerar_zip(aq_pequena, str(saida / 'a.zip'), miniaturas='opcionais', progresso=msgs.append)
    assert r['thumbs'] == 0 and len(r['catalog']['produtos']) == n and (saida / 'a.zip').stat().st_size == r['bytes']
    assert any(m.startswith('AVISO: miniaturas não geradas') for m in msgs)
    with zipfile.ZipFile(saida / 'a.zip') as z:
        m = json.loads(z.read('manifest.json'))
    assert m['thumbCount'] == 0 and m['productCount'] == n
    # nada além do ZIP ficou: o diretório de trabalho é temporário
    assert sorted(p.name for p in saida.iterdir()) == ['a.zip']


def test_gerar_zip_skip_thumbs_nem_tenta(saida, aq_pequena, monkeypatch):
    def explode(*a, **k):
        raise AssertionError('build_thumbs não devia ser chamado com miniaturas="nao"')
    monkeypatch.setattr(zip_bilds, 'build_thumbs', explode)
    r = zip_bilds.gerar_zip(aq_pequena, str(saida / 'a.zip'), miniaturas='nao')
    assert (saida / 'a.zip').exists() and r['thumbs'] == 0


def test_gerar_zip_catalogo_vazio_acusa(saida, tmp_path, monkeypatch):
    monkeypatch.setattr(zip_bilds, 'auto_config', lambda *a, **k: ({'slug': 's', 'titulo': 'T', 'fabricante': 'F', 'layout': 'catalog-grid'}, {}))
    monkeypatch.setattr(zip_bilds, 'build_catalog_from_aq', lambda *a, **k: ({'slug': 's', 'titulo': 'T', 'fabricante': 'F', 'layout': 'catalog-grid', 'filtros': [], 'produtos': []}, 0, None))
    monkeypatch.setattr(zip_bilds, 'resumo_diag', lambda *a, **k: False)
    with pytest.raises(zip_bilds.CatalogoVazio):
        zip_bilds.gerar_zip(str(tmp_path / 'x.aq'), str(saida / 'a.zip'))


def test_cli_um_arquivo_e_flags(saida, aq_pequena, sem_node, capsys):
    assert cli.main([aq_pequena, '--saida', str(saida / 'a.zip')]) == 1
    assert 'ERRO: miniaturas' in capsys.readouterr().err and not (saida / 'a.zip').exists()
    assert cli.main([aq_pequena, '--saida', str(saida / 'b.zip'), '--allow-no-thumbs']) == 0
    assert (saida / 'b.zip').exists()
    with pytest.raises(SystemExit):
        cli.main(['--skip-thumbs', '--allow-no-thumbs', 'x', '--saida', 'y'])   # excludentes
    with pytest.raises(SystemExit):
        cli.main([aq_pequena])                                                   # falta --saida


def test_cli_lote_espelha_pastas_pula_feitos_e_sai_com_1_em_falha(saida, aq_pequena, sem_node, tmp_path, capsys):
    entrada = tmp_path / 'input' / 'fabricante-exemplo' / 'linha-exemplo'
    entrada.mkdir(parents=True)
    os.symlink(aq_pequena, entrada / os.path.basename(aq_pequena))
    out = tmp_path / 'output'
    # sem Node e sem --allow-no-thumbs: falha, exit 1, nenhum ZIP
    assert cli.main(['--all', '--input-dir', str(tmp_path / 'input'), '--output-dir', str(out)]) == 1
    err = capsys.readouterr().err
    assert 'falhas  : 1' in err and 'Node >= 20' in err and not list(out.rglob('*.zip'))
    # com --allow-no-thumbs: ZIP espelhando a subpasta + catalog.json solto
    assert cli.main(['--all', '--input-dir', str(tmp_path / 'input'), '--output-dir', str(out), '--allow-no-thumbs']) == 0
    zips = list(out.rglob('*.zip'))
    assert len(zips) == 1 and zips[0].parent == out / 'fabricante-exemplo' / 'linha-exemplo'
    assert len(list(zips[0].parent.glob('*-catalog.json'))) == 1   # o slug vem da pasta (inferência), não da fixture
    # segunda rodada pula; --force refaz
    assert cli.main(['--all', '--input-dir', str(tmp_path / 'input'), '--output-dir', str(out), '--allow-no-thumbs']) == 0
    assert 'pulados : 1' in capsys.readouterr().err and len(list(out.rglob('*.zip'))) == 1


def test_cli_lote_sem_aq_sai_com_1(tmp_path, capsys):
    assert cli.main(['--all', '--input-dir', str(tmp_path), '--output-dir', str(tmp_path / 'o')]) == 1
    assert 'Nenhuma biblioteca .aq' in capsys.readouterr().err


# ── miniatura de verdade (Chromium) ───────────────────────────────────────────

@pytest.mark.thumbs
def test_build_thumbs_renderiza_uma_geometria(saida, aq_pequena):
    if not render.find_node():
        pytest.skip('sem Node >= 20 (nvm) — o passo de miniaturas não roda aqui')
    mini = os.path.join(os.path.dirname(render.__file__), 'node_modules', 'playwright')
    if not os.path.isdir(mini):
        pytest.skip('playwright não instalado em biblioteca/bim_pipeline/miniaturas (pnpm install)')
    sims, _ = read_aq.extract_simbologias(aq_pequena)
    # uma peça compacta, não um tubo: bounding box com proporção < 5
    sid = next(s for s in sorted(sims)
               if max(oq3d.bbox(sims[s]['blob'])) / max(min(oq3d.bbox(sims[s]['blob'])), 1e-9) < 5)
    geo_dir = saida / 'geo' / 'um'
    geo_dir.mkdir(parents=True)
    (geo_dir / 'a.json').write_text(json.dumps(oq3d.to_buffers(sims[sid]['blob'])))
    catalog = {'produtos': [{'id': 'a', 'geo': 'a.json'}, {'id': 'b', 'geo': 'a.json'}]}
    n = render.build_thumbs(catalog, str(geo_dir), str(saida / 'thumbs' / 'um'))
    assert n == 1
    webp = saida / 'thumbs' / 'um' / f'a.{render.THUMB_EXT}'
    assert webp.is_file() and webp.read_bytes()[:4] == b'RIFF' and webp.stat().st_size > 1000
    assert all(p['thumb'] == f'a.{render.THUMB_EXT}' for p in catalog['produtos'])
