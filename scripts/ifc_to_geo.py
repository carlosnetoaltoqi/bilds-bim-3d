#!/usr/bin/env python3
"""
ifc_to_geo.py — um IFC vira o JSON de geometria do viewer, no mesmo contrato do
`step_to_geo.py`: `{ pos, col, idx, partes, unidade, bbox_mm, fonte }`, metros,
Y-up, indexado e deduplicado. É a porta de entrada de IFC no editor 3D da POC
(`POST /cad/importar`), ao lado do STEP.

Não reimplementa nada: a geometria vem do `parse_ifc.py` do projeto — o parser
STEP/IFC4 validado nas bibliotecas da Dancor (tessellated) e da Amanco (B-rep via
`ifcopenshell`), com LocalPlacement, MappedItem, cores por face
(`IFCINDEXEDCOLOURMAP`) e a troca de eixos Z-up → Y-up. Aqui só se acrescenta:

- **dedup** com a quantização float32 do pipeline (`dedup.py`) — o `parse_ifc`
  devolve vértices expandidos quando há cor por face;
- **unidade**: o `parse_ifc` não converte unidade (a skill `leitor-ifc` manda
  verificar a magnitude, porque o CATIA declara MILLIMETRE e escreve metros).
  Regra aqui: se o arquivo declara `.MILLI.` E a bbox bruta passa de 50 (ou
  seja, uma peça de "50 m"), os valores estão de fato em milímetros e são
  divididos por 1000; caso contrário ficam como estão. O que foi feito vai em
  `escala_aplicada`;
- **partes**: nome dos `IfcProduct` com representação (via `ifcopenshell` quando
  instalado; senão, por regex nas entidades de elemento), só para o editor
  mostrar de onde veio — a divisão em partes é feita por componentes conexos,
  como sempre.

Uso:
    python3 scripts/ifc_to_geo.py peca.ifc saida.json
    python3 scripts/ifc_to_geo.py peca.ifc --info
"""
import argparse
import json
import os
import re
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import parse_ifc            # noqa: E402  o parser do projeto, intocado
from dedup import dedup     # noqa: E402

ELEMENTOS = ('IFCBUILDINGELEMENTPROXY', 'IFCELEMENTASSEMBLY', 'IFCFLOWFITTING', 'IFCFLOWTERMINAL',
             'IFCFLOWSEGMENT', 'IFCMECHANICALFASTENER', 'IFCPLATE', 'IFCBEAM', 'IFCCOLUMN',
             'IFCMEMBER', 'IFCDISCRETEACCESSORY')


def unidade_declarada(conteudo):
    m = re.search(r'IFCSIUNIT\s*\(\s*\*\s*,\s*\.LENGTHUNIT\.\s*,\s*(\$|\.[A-Z]+\.)\s*,\s*\.([A-Z_]+)\.', conteudo)
    if not m:
        return 'desconhecida'
    prefixo = '' if m.group(1) == '$' else m.group(1).strip('.')
    return f'{prefixo}{m.group(2)}'.replace('MILLIMETRE', 'MILLIMETRE').replace('METRE', 'METRE')


def nomes_das_partes(caminho, conteudo):
    try:
        import ifcopenshell
        f = ifcopenshell.open(caminho)
        nomes = []
        for p in f.by_type('IfcProduct'):
            if getattr(p, 'Representation', None):
                nomes.append({'nome': p.Name or p.is_a(), 'tipo': p.is_a()})
        if nomes:
            return nomes
    except Exception:
        pass
    nomes = []
    for m in re.finditer(r"=\s*(" + '|'.join(ELEMENTOS) + r")\s*\(\s*'[^']*'\s*,\s*(?:#\d+|\$)\s*,\s*('([^']*)'|\$)", conteudo):
        nomes.append({'nome': m.group(3) or m.group(1), 'tipo': m.group(1)})
    return nomes


def converter(caminho):
    t0 = time.time()
    with open(caminho, encoding='utf-8', errors='replace') as f:
        conteudo = f.read()
    unidade = unidade_declarada(conteudo)

    bruto = parse_ifc.parse_ifc_file(caminho)
    if not bruto.get('pos'):
        raise SystemExit(f'{caminho}: o parse_ifc.py não extraiu geometria (sem IFCTRIANGULATEDFACESET e sem ifcopenshell para B-rep?)')

    geo, _n, _nd, _pct = dedup({'pos': bruto['pos'], 'col': bruto.get('col', []), **({'idx': bruto['idx']} if 'idx' in bruto else {})})

    # unidade: o parser não escala; decide pela declaração E pela magnitude
    pos = geo['pos']
    xs, ys, zs = pos[0::3], pos[1::3], pos[2::3]
    bruto_bbox = [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)]
    escala = 1.0
    if unidade.startswith('MILLI') and max(bruto_bbox) > 50:
        escala = 0.001
    elif unidade.startswith('CENTI') and max(bruto_bbox) > 50:
        escala = 0.01
    if escala != 1.0:
        geo['pos'] = [round(v * escala, 7) for v in pos]
    else:
        geo['pos'] = [round(v, 7) for v in pos]

    bb = [round(d * escala * 1000, 3) for d in bruto_bbox]
    partes = nomes_das_partes(caminho, conteudo)
    geo.update({
        'partes': partes,
        'unidade': unidade,
        'escala_aplicada': escala,
        'bbox_mm': bb,
        'fonte': os.path.basename(caminho),
        'cor_por_face': 'idx' not in bruto,
        'segundos': round(time.time() - t0, 2),
    })
    return geo


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('entrada')
    ap.add_argument('saida', nargs='?')
    ap.add_argument('--info', action='store_true')
    args = ap.parse_args()

    geo = converter(args.entrada)
    fmt = lambda n: f'{n:,}'.replace(',', '.')
    nv, nt = len(geo['pos']) // 3, len(geo['idx']) // 3
    bb = geo['bbox_mm']
    print(f"{geo['fonte']}: unidade {geo['unidade']} (escala {geo['escala_aplicada']}), {len(geo['partes'])} produto(s), "
          f"{fmt(nv)} vértices, {fmt(nt)} triângulos, bbox {bb[0]:.1f}×{bb[1]:.1f}×{bb[2]:.1f} mm, "
          f"{'cor por face' if geo['cor_por_face'] else 'cor uniforme'}, {geo['segundos']} s")
    for p in geo['partes'][:12]:
        print(f"  {p['tipo']}: {p['nome']}")
    if len(geo['partes']) > 12:
        print(f'  … +{len(geo["partes"]) - 12}')
    if args.info or not args.saida:
        return
    with open(args.saida, 'w', encoding='utf-8') as f:
        json.dump(geo, f, separators=(',', ':'))
    print(f'  → {args.saida} ({os.path.getsize(args.saida) / 1024:.0f} KB)')


if __name__ == '__main__':
    main()
