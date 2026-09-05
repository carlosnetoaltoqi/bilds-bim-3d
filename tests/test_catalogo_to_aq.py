"""Exportar o catálogo salvo para um `.aq` novo (S7.16, 2026-09-05).

`catalogo_to_aq.py` gera do zero — o `.aq` original não fica no servidor — uma biblioteca com
todas as peças do catálogo como estão na tela: um grupo por série, uma simbologia por arquivo de
geometria (compartilhada entre as peças que a compartilham), uma propriedade por chave de spec,
curva Q-H em `MODELO_BOMBA`/`ITEM_CURVA_BOMBA`. O que prova aqui: o `read_aq.py`, o `oq3d.py` e o
`catalogo.py` do projeto leem o arquivo de volta com as mesmas peças, séries, specs e geometria;
texto em cp1252; erro alto para geometria ausente e caractere fora do cp1252; ida e volta com
a Akato inteira (262 peças) sem perder nada.
"""
import json
import sqlite3
import subprocess
import sys

import pytest

import catalogo
import oq3d
import read_aq
from conftest import PIPELINE, ROOT

SCRIPT = PIPELINE / 'catalogo_to_aq.py'


def _geo(dx, cores):
    """Dois triângulos (um por cor) em metros, Y-up, deslocados em x."""
    pos, col, idx = [], [], []
    for k, cor in enumerate(cores):
        base = len(pos) // 3
        z = k * 0.05
        pos += [dx, 0, z, dx + 0.1, 0, z, dx, 0.1, z]
        col += list(cor) * 3
        idx += [base, base + 1, base + 2]
    return {'pos': pos, 'col': col, 'idx': idx}


def _rodar(manifesto, saida, *flags):
    entrada = saida.parent / 'manifesto.json'
    entrada.write_text(json.dumps(manifesto, ensure_ascii=False), encoding='utf8')
    return subprocess.run([sys.executable, str(SCRIPT), str(entrada), str(saida), *flags],
                          capture_output=True, text=True, cwd=ROOT, timeout=600)


def _manifesto(tmp_path):
    geo_dir = tmp_path / 'geo'
    geo_dir.mkdir()
    (geo_dir / '50mm.json').write_text(json.dumps(_geo(0.0, [(1, 0, 0), (0, 0, 1)])), encoding='utf8')
    (geo_dir / 'bomba.json').write_text(json.dumps(_geo(1.0, [(0, 1, 0)])), encoding='utf8')
    return {
        'catalogo': {'fabricante': 'Fábrica Ç', 'titulo': 'Esgoto Série Teste', 'slug': 'esgoto-teste',
                     'origem': 'teste'},
        'geo_dir': str(geo_dir),
        'produtos': [
            # duas peças da mesma série compartilham a geometria (uma simbologia, duas PECA_SIMBOLOGIA_3D)
            {'id': 'cap-50mm', 'nome': 'Cap 50mm', 'serie': 'Cap', 'conexoes': 'Cap',
             'specs': {'Bolsa': 'Bolsa de dupla atuação:\nsoldável', 'Temperatura máxima de operação': '75°C'},
             'curva': None, 'potencia': None, 'geo': '50mm.json'},
            {'id': 'cap-75mm', 'nome': 'Cap 75mm', 'serie': 'Cap', 'conexoes': '',
             'specs': {'Bolsa': 'Soldável', 'Vazio': ''}, 'curva': None, 'potencia': None, 'geo': '50mm.json'},
            # bomba com curva Q-H e código comercial na spec
            {'id': 'bomba-x', 'nome': 'Bomba X 3CV', 'serie': 'Junção Ímpar', 'conexoes': '2" x 2"',
             'specs': {'Código': '10652511', 'Tensão': '220V'},
             'curva': [[31.0, 9.3, 2.46, 36.3], [28.9, 10.9, 2.34, 39.3]], 'potencia': 3.0, 'geo': 'bomba.json'},
        ],
    }


def test_exporta_catalogo_e_o_leitor_do_projeto_le_de_volta(tmp_path):
    saida = tmp_path / 'saida.aq'
    proc = _rodar(_manifesto(tmp_path), saida)
    assert proc.returncode == 0, proc.stderr[-3000:]
    resumo = json.loads(proc.stdout.strip().splitlines()[-1])
    assert resumo['pecas'] == 3 and resumo['grupos'] == 2 and resumo['simbologias'] == 2
    assert resumo['triangulos'] == 3 and resumo['propriedades'] == 4 and resumo['valores'] == 5
    assert resumo['curvas'] == 2 and resumo['bytes'] == saida.stat().st_size

    dados = read_aq.extract(str(saida))
    # o prefixo da série sai do nome ('Cap 50mm' → '50mm', como a Amanco grava); o da bomba não tinha
    assert [p['NOME_PECA'] for p in dados['pecas']] == ['50mm', '75mm', 'Bomba X 3CV']
    assert [g['NOME_GP'] for g in dados['grupos']] == ['Cap', 'Junção Ímpar']
    por_nome = {g['NOME_GP']: g for g in dados['grupos']}
    assert (por_nome['Cap']['ENTIDADE_IFC'], por_nome['Cap']['SUBTIPO_IFC'], por_nome['Cap']['PROJETO_APLICACAO']) == (2071, 3, 8)
    assert por_nome['Junção Ímpar']['ENTIDADE_IFC'] == 2075          # série com curva vira bomba
    tipos = {p['NOME_PECA']: p['TIPO_APLICACAO_PECA'] for p in dados['pecas']}
    assert tipos == {'50mm': 2, '75mm': 2, 'Bomba X 3CV': 6}
    assert {p['DESCRICAO_DADOS'] for p in dados['pecas']} == {'Cap', '2" x 2"'}    # conexões vazias caem na série
    assert all(p['BIBLIOTECA'] == 'Fábrica Ç' for p in dados['pecas'])

    # propriedades: uma por chave, valores só onde não vazio; a spec 'Código' vai para ITEM.CODIGO_ITEM também
    props = {(p['NOME_PECA'], p['propriedade']): p['VALOR'] for p in dados['propriedades']}
    assert props[('50mm', 'Bolsa')] == 'Bolsa de dupla atuação:\nsoldável'
    assert props[('50mm', 'Temperatura máxima de operação')] == '75°C'
    assert ('75mm', 'Vazio') not in props and props[('Bomba X 3CV', 'Código')] == '10652511'
    # o read_aq ordena os pontos por vazão
    assert [(round(c['vazao'], 1), round(c['altura'], 1), round(c['rendimento'], 1)) for c in dados['curvas']] == [(28.9, 10.9, 39.3), (31.0, 9.3, 36.3)]
    assert dados['curvas'][0]['potencia_cv'] == 3.0

    con = sqlite3.connect(f'file:{saida}?mode=ro', uri=True)
    con.text_factory = bytes
    assert con.execute('PRAGMA foreign_key_check').fetchall() == []
    assert con.execute("SELECT COUNT(*) FROM PROPRIEDADE_PERSONALIZADA").fetchone()[0] == 4
    codigos = {r[0].decode('cp1252'): r[1].decode('cp1252') for r in con.execute('SELECT NOME_ITEM, CODIGO_ITEM FROM ITEM')}
    assert codigos == {'50mm': 'cap-50mm', '75mm': 'cap-75mm', 'Bomba X 3CV': '10652511'}
    # cp1252, não UTF-8: o acento é um byte alto isolado, inválido como UTF-8
    (nome_gp,) = con.execute("SELECT NOME_GP FROM GRUPO_PECA WHERE ID_GRUPO_PECA = 2").fetchone()
    assert nome_gp == 'Junção Ímpar'.encode('cp1252')
    with pytest.raises(UnicodeDecodeError):
        nome_gp.decode('utf8')
    (classe,) = con.execute('SELECT NOME_CLASSE FROM CLASSE_SIMBOLOGIA_3D').fetchone()
    assert classe.decode('cp1252') == 'Fábrica Ç - Esgoto Série Teste'
    con.close()

    # geometria: uma simbologia compartilhada pelas duas caps, uma raiz OQ3D por cor, ida e volta em metros
    simbologias, por_peca = read_aq.extract_simbologias(str(saida))
    assert len(simbologias) == 2 and por_peca[1] == por_peca[2] != por_peca[3]
    assert {s['nome'] for s in simbologias.values()} == {'50mm', 'bomba'}
    b = oq3d.to_buffers(simbologias[por_peca[1]]['blob'])
    assert len(b['idx']) == 6 and oq3d.n_raizes_declarado(simbologias[por_peca[1]]['blob']) == 2
    esperado = _geo(0.0, [(1, 0, 0), (0, 0, 1)])
    assert sorted(round(v, 6) for v in b['pos']) == sorted(round(v, 6) for v in esperado['pos'])
    assert {tuple(round(c, 2) for c in b['col'][i:i + 3]) for i in range(0, len(b['col']), 3)} == {(1, 0, 0), (0, 0, 1)}

    # e o pipeline inteiro (catalogo.py) reconstrói o catálogo a partir do arquivo exportado
    cfg = {'slug': 'x', 'titulo': 'x', 'fabricante': 'x'}
    cat, n_geo, diag = catalogo.build_catalog_from_aq(cfg, str(saida), str(tmp_path / 'geo2'))
    assert n_geo == 2 and not catalogo.resumo_diag(diag, out=lambda _l: None)
    assert [(p['nome'], p['serie']) for p in cat['produtos']] == [('50mm', 'Cap'), ('75mm', 'Cap'), ('Bomba X 3CV', 'Junção Ímpar')]
    assert cat['produtos'][2]['curva'] == [[28.9, 10.9, 2.34, 39.3], [31.0, 9.3, 2.46, 36.3]]
    assert cat['produtos'][0]['geo'] == cat['produtos'][1]['geo'] != cat['produtos'][2]['geo']
    assert read_aq.peek_metadata(str(saida))['fabricante'] == 'Fábrica Ç'


def test_manter_prefixo_serie_grava_o_nome_da_tela(tmp_path):
    saida = tmp_path / 'saida.aq'
    proc = _rodar(_manifesto(tmp_path), saida, '--manter-prefixo-serie', '--quiet')
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert proc.stderr == ''
    assert [p['NOME_PECA'] for p in read_aq.extract(str(saida))['pecas']] == ['Cap 50mm', 'Cap 75mm', 'Bomba X 3CV']


def test_geometria_ausente_acusa_erro_e_nao_deixa_aq_parcial(tmp_path):
    m = _manifesto(tmp_path)
    m['produtos'][1]['geo'] = 'nao-existe.json'
    saida = tmp_path / 'saida.aq'
    proc = _rodar(m, saida)
    assert proc.returncode == 1
    assert 'Cap 75mm' in proc.stderr and 'geometria ausente' in proc.stderr
    assert not saida.exists()


def test_caractere_fora_do_cp1252_acusa_erro(tmp_path):
    m = _manifesto(tmp_path)
    m['produtos'][0]['specs']['Bolsa'] = 'seta → fora do cp1252'
    saida = tmp_path / 'saida.aq'
    proc = _rodar(m, saida)
    assert proc.returncode == 1
    assert 'cp1252' in proc.stderr and 'VALOR_PROPRIEDADE_PERSONALIZADA' in proc.stderr
    assert not saida.exists()


def test_catalogo_vazio_acusa_erro(tmp_path):
    m = _manifesto(tmp_path)
    m['produtos'] = []
    proc = _rodar(m, tmp_path / 'saida.aq')
    assert proc.returncode == 1 and 'sem produtos' in proc.stderr


def test_ida_e_volta_com_a_akato_inteira(akato_aq, tmp_path):
    """.aq real → catálogo (catalogo.py) → .aq exportado → catálogo: mesmas peças, séries, specs e bbox."""
    cfg = {'slug': 'akato', 'titulo': 'PVC Construção Civil', 'fabricante': 'Akato'}
    cat1, n1, _ = catalogo.build_catalog_from_aq(cfg, akato_aq, str(tmp_path / 'geo1'))
    manifesto = {
        'catalogo': {'fabricante': cat1['fabricante'], 'titulo': cat1['titulo'], 'slug': cat1['slug']},
        'geo_dir': str(tmp_path / 'geo1'),
        'produtos': [{'id': p['id'], 'nome': p['nome'], 'serie': p['serie'], 'conexoes': p['conexoes'],
                      'specs': p['specs'], 'curva': p['curva'], 'potencia': p['potencia'], 'geo': p['geo']}
                     for p in cat1['produtos']],
    }
    saida = tmp_path / 'akato-exportado.aq'
    # com o prefixo mantido, o nome da tela é estável na ida e volta
    proc = _rodar(manifesto, saida, '--manter-prefixo-serie')
    assert proc.returncode == 0, proc.stderr[-3000:]
    resumo = json.loads(proc.stdout.strip().splitlines()[-1])
    assert resumo['pecas'] == len(cat1['produtos']) == 262 and resumo['simbologias'] == n1 == 262

    cat2, n2, diag2 = catalogo.build_catalog_from_aq(cfg, str(saida), str(tmp_path / 'geo2'))
    assert n2 == n1 and not catalogo.resumo_diag(diag2, out=lambda _l: None)
    chave = lambda p: (p['nome'], p['serie'], p['conexoes'], tuple(sorted(p['specs'].items())))   # noqa: E731
    assert sorted(map(chave, cat2['produtos'])) == sorted(map(chave, cat1['produtos']))

    def bbox(geo_dir, geo):
        d = json.loads((tmp_path / geo_dir / geo).read_text(encoding='utf8'))
        xs, ys, zs = d['pos'][0::3], d['pos'][1::3], d['pos'][2::3]
        return tuple(round(v, 5) for v in (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)))
    por_nome1 = {p['nome']: p for p in cat1['produtos']}
    for p2 in cat2['produtos']:
        p1 = por_nome1[p2['nome']]
        assert bbox('geo1', p1['geo']) == bbox('geo2', p2['geo']), p2['nome']
        assert len(json.loads((tmp_path / 'geo2' / p2['geo']).read_text())['idx']) == len(json.loads((tmp_path / 'geo1' / p1['geo']).read_text())['idx'])
