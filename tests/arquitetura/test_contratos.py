"""Contratos biblioteca ↔ serviços (ADR-015): o que a biblioteca emite segue os JSON Schema de
`bim_pipeline/contratos/`. É o lado Python da prova; o lado TypeScript (`@bim/base` validarContrato)
lê os mesmos arquivos."""
import json
import os
import subprocess
import sys

import pytest

jsonschema = pytest.importorskip('jsonschema')

from bim_pipeline import contratos
from bim_pipeline.catalogo.catalogo import diag_vazio, montar_catalogo, montar_resultado


def test_todos_os_schemas_sao_validos():
    for nome in contratos.NOMES:
        jsonschema.Draft202012Validator.check_schema(contratos.carregar(nome))


def test_montar_resultado_segue_o_contrato_inclusive_com_diag_interno():
    config = {'slug': 's', 'titulo': 'T', 'fabricante': 'F', 'descricao': '', 'layout': 'catalog-grid'}
    produtos = [{'id': 'a', 'nome': 'A', 'serie': 'S', 'geo': 'a.json', 'potencia': None, 'conexoes': '', 'specs': {'k': 'v'}, 'curva': None}]
    diag = diag_vazio()
    diag['sim_ilegivel'].append((7, 'sete', 'truncado'))          # a forma interna: tuplas
    diag['avisos'].append((8, 'oito', 'declara 7 objetos-raiz'))
    r = montar_resultado(config, montar_catalogo(config, produtos, {'S'}), 1, diag, {'n_pecas': 1, 'schema': 607})
    contratos.validar('catalogo', r)
    assert r['diag']['sim_ilegivel'] == [{'id': 7, 'nome': 'sete', 'erro': 'truncado'}]
    # já em objeto: passa igual (idempotente); aviso em texto (plugin web) também
    r2 = montar_resultado(config, r['catalog'], 1, {**r['diag'], 'avisos': ['grupo sem IGES']}, {})
    contratos.validar('catalogo', r2)
    assert r2['diag']['sim_ilegivel'] == r['diag']['sim_ilegivel']


def test_catalogo_de_aq_emite_o_contrato(aq_pequena, tmp_path):
    saida = tmp_path / 'c.json'
    r = subprocess.run([sys.executable, '-m', 'bim_pipeline.cli.catalogo_de_aq', aq_pequena, '--geo-dir', str(tmp_path / 'geo'), '--saida', str(saida)],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    resultado = json.loads(saida.read_text(encoding='utf8'))
    contratos.validar('catalogo', resultado)
    for p in resultado['catalog']['produtos'][:5]:
        contratos.validar('geometria', json.loads((tmp_path / 'geo' / p['geo']).read_text(encoding='utf8')))


def test_conversor_step_emite_o_contrato(tmp_path):
    step_iges = pytest.importorskip('bim_pipeline.conversores.step_iges')
    if not step_iges.HAS_OCP:
        pytest.skip('OCP não instalado')
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    caixa = tmp_path / 'caixa.stp'
    w = STEPControl_Writer(); w.Transfer(BRepPrimAPI_MakeBox(10.0, 20.0, 30.0).Shape(), STEPControl_AsIs); w.Write(str(caixa))
    geo = step_iges.converter(str(caixa))
    contratos.validar('geometria', geo)


def test_manifesto_e_info_plugin_exemplos_validam():
    contratos.validar('manifesto-catalogo-aq', {
        'catalogo': {'fabricante': 'F', 'titulo': 'T', 'slug': 't'}, 'geo_dir': '/tmp/x',
        'produtos': [{'id': 'a', 'nome': 'A', 'serie': 'S', 'conexoes': '', 'specs': {}, 'curva': None, 'potencia': None, 'geo': 'geo/i/a.json'}]})
    contratos.validar('info-plugin', {'arquivo': 'p.dll', 'bytes': 100, 'host': 'https://x', 'hosts': ['https://x'], 'dotnet': True,
                                      'plugin': None, 'empresa': None, 'versao': None})
    contratos.validar('info-familias-revit', {'entrada': 'f.zip', 'bytes': 10, 'n_familias': 1, 'n_tipos': 2, 'com_geometria_irma': 0, 'ignorados': 0,
                                              'avisos': [], 'familias': [{'arquivo': 'a/F.rfa', 'titulo': 'F', 'revit': None, 'formato': 2021, 'categoria': None,
                                                                          'fabricante': None, 'tipos': 2, 'type_catalog': True, 'geometria_irma': None, 'preview': False}]})
    contratos.validar('resumo-miniaturas', {'geo': 'a', 'bytes': 10})
    contratos.validar('resumo-miniaturas', {'geo': 'a', 'error': 'x'})
    with pytest.raises(jsonschema.ValidationError):
        contratos.validar('resumo-miniaturas', {'geo': 'a'})
