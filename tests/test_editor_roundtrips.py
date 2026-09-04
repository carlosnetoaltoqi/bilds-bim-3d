"""www/tools/testes-editor.sh — round-trips do editor 3D (mesh-model e exportador IFC).

I13 da auditoria (2026-09-04): o round-trip do `mesh-model.ts` comparava strings
`toFixed(5)` de valores com ruído float32 e falhava sempre (28–32% "fora") em
malhas idênticas, então o script saía 1 e não sinalizava nada. Passou a agrupar
vértices por grade a ≤ 2 µm (union-find, original + bake juntos) e compara os
triângulos por grupo, com o sentido.

Precisa de Node ≥ 22.6, `www/apps/web/node_modules` (three) e ao menos uma
geometria em `www/storage/bim/geo/` (gitignored) — pula com motivo se faltar.
"""
import json
import os
import shutil
import subprocess

import pytest

from conftest import ROOT

SCRIPT = ROOT / 'www' / 'tools' / 'testes-editor.sh'
GEO_DIR = ROOT / 'www' / 'storage' / 'bim' / 'geo'

pytestmark = pytest.mark.paridade


def _primeira_geometria():
    if not (ROOT / 'www' / 'apps' / 'web' / 'node_modules' / 'three').is_dir():
        pytest.skip('www/apps/web/node_modules sem three (pnpm install em www/)')
    if shutil.which('node') is None:
        pytest.skip('node não está no PATH')
    geos = sorted(p for p in GEO_DIR.glob('*/*.json') if not p.name.endswith('.orig.json')) \
        if GEO_DIR.is_dir() else []
    if not geos:
        pytest.skip('nenhuma geometria em www/storage/bim/geo (storage é gitignored)')
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
