"""web/tools/testes-editor.sh — round-trips do editor 3D (mesh-model e exportador IFC).

I13 da auditoria (2026-09-04): o round-trip do `mesh-model.ts` comparava strings
`toFixed(5)` de valores com ruído float32 e falhava sempre (28–32% "fora") em
malhas idênticas, então o script saía 1 e não sinalizava nada. Passou a agrupar
vértices por grade a ≤ 2 µm (union-find, original + bake juntos) e compara os
triângulos por grupo, com o sentido.

S7.9 (2026-09-05): a conferência do exportador IFC tinha a mesma armadilha — conjuntos
de coordenadas arredondadas a 10 µm com limite de 2% — e o script imprimia `[FALHA]`
sem sair 1. Passou a parear cada vértice a ≤ 2 µm nos dois sentidos e a sair 1;
`ROUNDTRIP_SABOTAR_IFC` prova que a conferência acusa.

Precisa de Node ≥ 22.6, `web/node_modules` (three) e ao menos uma
geometria em `storage/bim/geo/` (gitignored) — pula com motivo se faltar.
"""
import json
import os
import shutil
import subprocess

import pytest

from conftest import ROOT

SCRIPT = ROOT / 'web' / 'tools' / 'testes-editor.sh'
GEO_DIR = ROOT / 'storage' / 'bim' / 'geo'

pytestmark = pytest.mark.paridade


def _primeira_geometria():
    if not (ROOT / 'web' / 'node_modules' / 'three').is_dir():
        pytest.skip('web/node_modules sem three (pnpm install na raiz)')
    if shutil.which('node') is None:
        pytest.skip('node não está no PATH')
    geos = sorted(p for p in GEO_DIR.glob('*/*.json') if not p.name.endswith('.orig.json')) \
        if GEO_DIR.is_dir() else []
    if not geos:
        pytest.skip('nenhuma geometria em storage/bim/geo (storage é gitignored)')
    return geos[0]


def _roda(geo, **env):
    r = subprocess.run(['bash', str(SCRIPT), str(geo)], capture_output=True, text=True,
                       timeout=300, env={**os.environ, **env})
    return r.returncode, r.stdout + r.stderr


def test_round_trip_da_primeira_geometria_passa():
    codigo, out = _roda(_primeira_geometria())
    assert codigo == 0, out
    assert '[ok  ] todo vértice original tem par no bake' in out
    assert '[ok  ] todo triângulo original existe no bake com o mesmo sentido' in out
    assert '[ok  ] todo vértice esperado tem par no IFC lido a ≤ 2 µm' in out
    assert '[ok  ] todo vértice do IFC lido tem par no esperado a ≤ 2 µm' in out
    assert 'FALHA' not in out


def test_metrica_acusa_bake_sabotado():
    # ROUNDTRIP_SABOTAR inverte um triângulo e move um vértice 1 mm DEPOIS do bake:
    # se a métrica não pegar isso, ela não pega bug nenhum do segment/bake.
    codigo, out = _roda(_primeira_geometria(), ROUNDTRIP_SABOTAR='1')
    assert codigo != 0
    assert '[FALHA] todo triângulo original existe no bake' in out


def test_geometria_do_storage_tem_o_formato_do_viewer():
    g = json.loads(_primeira_geometria().read_text())
    assert set(g) >= {'pos', 'idx'} and len(g['pos']) % 3 == 0 and len(g['idx']) % 3 == 0


def test_metrica_ifc_acusa_esperado_sabotado():
    # ROUNDTRIP_SABOTAR_IFC move um vértice do bake esperado 1 mm DEPOIS de exportar o IFC:
    # a conferência em Python tem de acusar e o script tem de sair 1 (até S7.9 saía 0 com FALHA).
    codigo, out = _roda(_primeira_geometria(), ROUNDTRIP_SABOTAR_IFC='1')
    assert codigo != 0
    assert '[FALHA] todo vértice esperado tem par no IFC lido' in out
    assert '[ok  ] todo triângulo original existe no bake com o mesmo sentido' in out  # o mesh-model continua ok
