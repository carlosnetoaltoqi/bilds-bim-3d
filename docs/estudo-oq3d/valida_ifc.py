#!/usr/bin/env python3
"""
valida_ifc.py — Confere a geometria que o oq3d.py tira do .aq contra o IFC da
mesma biblioteca, peça a peça.

Existe para provar duas coisas que já quebraram no passado:

  1. que TODA instância repetida (TQi3DReusedObject) emite geometria — o
     contador de triângulos só bate com o IFC se as referências resolverem;
  2. que as instâncias caem no LUGAR certo — a rotação de
     TCoordinateTransformation3D é column-major, e lê-la como row-major
     transpõe a matriz e desloca as peças rotacionadas.

Em biblioteca tessellated (IFCTRIANGULATEDFACESET, ex.: Dancor) a comparação é
exata: reconstrói-se o IFC a partir do STEP (placement do produto × mapped
item) e compara-se o CONJUNTO DE PONTOS, não só a bounding box — bbox é fraca,
uma rotação e a sua transposta podem gerar a mesma caixa.

Em biblioteca B-rep (IFCADVANCEDBREP, ex.: Amanco) a tesselação é independente,
então compara-se a forma: extensão da bounding box, com tolerância.

Uso:
    python3 docs/estudo-oq3d/valida_ifc.py Dancor
    python3 docs/estudo-oq3d/valida_ifc.py Amanco --limite 40

Requer ifcopenshell para as bibliotecas B-rep.
"""
import os
import re
import sys
import glob
import sqlite3
import argparse
import unicodedata
import collections

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'scripts'))
import oq3d
import read_aq
from build import find_aq_product

try:
    import ifcopenshell
    import ifcopenshell.geom
    import ifcopenshell.util.placement as P
except ImportError:
    sys.exit('precisa de ifcopenshell: pip install ifcopenshell')

CM = 100.0  # IFC vem em metros; o OQ3D em centímetros


def norm(s):
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


# ── lado IFC ────────────────────────────────────────────────────────────────

def ifc_tessellated(path):
    """(pontos_cm, n_triangulos) reconstruídos do STEP — exato, sem tesselador.

    Cada instância é um IfcProduct próprio: o MappingTarget costuma ser
    identidade e quem posiciona é o ObjectPlacement do produto.
    """
    f = ifcopenshell.open(path)
    pts, ntri = [], 0

    def add(fs, M):
        nonlocal ntri
        c = np.array(fs.Coordinates.CoordList, float)
        pts.append((np.c_[c, np.ones(len(c))] @ M.T)[:, :3] * CM)
        ntri += len(fs.CoordIndex)

    for prod in f.by_type('IfcProduct'):
        rep = getattr(prod, 'Representation', None)
        if not rep:
            continue
        M0 = P.get_local_placement(prod.ObjectPlacement)
        for r in rep.Representations:
            for it in r.Items:
                if it.is_a('IfcTriangulatedFaceSet'):
                    add(it, M0)
                elif it.is_a('IfcMappedItem'):
                    M = M0 @ P.get_cartesiantransformationoperator3d(it.MappingTarget) \
                           @ P.get_axis2placement(it.MappingSource.MappingOrigin)
                    for sub in it.MappingSource.MappedRepresentation.Items:
                        if sub.is_a('IfcTriangulatedFaceSet'):
                            add(sub, M)
    if not pts:
        return None, 0
    return np.concatenate(pts), ntri


def ifc_brep(path):
    """(pontos_cm, n_triangulos) via tesselador do ifcopenshell."""
    f = ifcopenshell.open(path)
    s = ifcopenshell.geom.settings()
    try:
        s.set(s.USE_WORLD_COORDS, True)
    except Exception:
        s.set('use-world-coords', True)
    pts, ntri = [], 0
    for prod in f.by_type('IfcProduct'):
        if not getattr(prod, 'Representation', None):
            continue
        try:
            sh = ifcopenshell.geom.create_shape(s, prod)
        except Exception:
            continue
        v = np.array(sh.geometry.verts, float).reshape(-1, 3) * CM
        pts.append(v)
        ntri += len(sh.geometry.faces) // 3
    if not pts:
        return None, 0
    return np.concatenate(pts), ntri


def is_tessellated(path):
    with open(path, 'rb') as fh:
        head = fh.read()
    return b'IFCTRIANGULATEDFACESET' in head.upper()


# ── comparação ──────────────────────────────────────────────────────────────

def _unicos(pts):
    """Pontos únicos, ordenados lexicograficamente."""
    u = np.unique(np.round(pts, 6), axis=0)
    return u[np.lexsort((u[:, 2], u[:, 1], u[:, 0]))]


def compara_exato(aq_pts, ifc_pts, tol=1e-3):
    """(iguais, erro_max) — alinha por translação e compara as nuvens de pontos.

    O alinhamento usa o canto da bounding box, não o centróide: o OQ3D guarda
    várias malhas como sopa de triângulos (vértices repetidos) enquanto o IFC
    solda os vértices, então os centróides têm pesos diferentes e não servem
    de âncora. Os extremos da caixa, esses, são os mesmos nos dois lados.

    A comparação é por tolerância (10 µm), não por igualdade de conjunto:
    arredondar para casas fixas coloca coordenadas em cima da fronteira de
    arredondamento e os dois lados caem para lados diferentes.
    """
    off = aq_pts.min(0) - ifc_pts.min(0)
    A, B = _unicos(aq_pts - off), _unicos(ifc_pts)
    if len(A) != len(B):
        return False, float('inf')
    err = float(np.abs(A - B).max()) if len(A) else 0.0
    return err <= tol, err


def extensao(pts):
    return np.sort(pts.max(0) - pts.min(0))   # ordenada: invariante a eixo


def indexa_aq(aq):
    """(por_ifc, simbologias) — casa caminho de IFC com o BLOB OQ3D do .aq.

    Reaproveita o matcher de produção (build.find_aq_product): o nome da peça
    sozinho é ambíguo em catálogo hierárquico ("50MM" existe em Cap, Joelho,
    Luva...), quem desambigua é o caminho de pastas do IFC.
    """
    dados = read_aq.extract(aq)
    pmap = read_aq.build_product_map(dados)
    simbologias, por_peca = read_aq.extract_simbologias(aq)
    return pmap, por_peca, simbologias


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('lib')
    ap.add_argument('--limite', type=int, default=0, help='máx. de peças (0 = todas)')
    ap.add_argument('--tol', type=float, default=0.5, help='tolerância de bbox em cm (B-rep)')
    a = ap.parse_args()

    raiz = os.path.join('input', a.lib)
    aqs = glob.glob(os.path.join(raiz, '**', '*.aq'), recursive=True)
    ifcs = sorted(p for p in glob.glob(os.path.join(raiz, '**', '*.[iI][fF][cC]'), recursive=True)
                  if ':Zone' not in p)
    if not aqs or not ifcs:
        sys.exit(f'faltam .aq ou IFC em {raiz}')

    base = os.path.commonpath([os.path.dirname(p) for p in ifcs])

    ok = div = semmatch = 0
    linhas = []
    for aq in aqs:
        pmap, por_peca, simbologias = indexa_aq(aq)
        # índice por NOME da simbologia — só os nomes sem ambiguidade
        cont = collections.Counter(norm(v['nome']) for v in simbologias.values())
        por_sim_nome = {norm(v['nome']): k for k, v in simbologias.items()
                        if cont[norm(v['nome'])] == 1}
        for path in ifcs:
            if a.limite and len(linhas) >= a.limite:
                break
            rel = os.path.relpath(path, base)
            slug = os.path.splitext(os.path.basename(path))[0]
            # 1) nome da simbologia igual ao do arquivo (catálogo flat, ex. Dancor)
            sid = por_sim_nome.get(norm(slug))
            if sid is None:
                # 2) matcher de produção: usa a hierarquia de pastas (ex. Amanco)
                m = find_aq_product(slug, pmap, ifc_path_hint=rel)
                if not m:
                    semmatch += 1
                    continue
                sid = por_peca.get(m[1]['id'])
            if sid is None or sid not in simbologias:
                semmatch += 1
                continue
            b = simbologias[sid]['blob']
            if not b or not oq3d.is_oq3d(b):
                continue
            ms = oq3d.extract(b)
            if not ms:
                continue
            aq_pts = np.concatenate([np.asarray(x[0]) for x in ms])
            aq_tri = sum(len(x[1]) for x in ms)

            tess = is_tessellated(path)
            ifc_pts, ifc_tri = (ifc_tessellated if tess else ifc_brep)(path)
            if ifc_pts is None or not len(ifc_pts):
                continue

            if tess:
                igual, err = compara_exato(aq_pts, ifc_pts)
                bom = igual and aq_tri == ifc_tri
                det = (f'pontos idênticos (erro {err:.1e} cm)' if igual
                       else f'PONTOS DIFEREM (erro {err:.3e} cm)')
                det += f' | tri aq={aq_tri} ifc={ifc_tri}'
            else:
                d = float(np.abs(extensao(aq_pts) - extensao(ifc_pts)).max())
                bom = d <= a.tol
                det = f'Δbbox={d:.4f} cm | tri aq={aq_tri} ifc={ifc_tri}'
            ok += bom
            div += (not bom)
            linhas.append((bom, rel, det))

    for bom, rel, det in linhas:
        if not bom:
            print(f"XX  {rel[:60]:60s} {det}")
    print(f"\n{a.lib}: {ok} conferem, {div} divergem, {semmatch} sem match de peça")
    return 1 if div else 0


if __name__ == '__main__':
    sys.exit(main())
