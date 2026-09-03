#!/usr/bin/env python3
"""
step_to_geo.py — tessela um arquivo STEP (.stp/.step, AP203/AP214/AP242) para o
JSON de geometria do viewer: `{ pos, col, idx }` em METROS, Y-up, indexado e
deduplicado — o mesmo contrato do `oq3d.py` e do `parse_ifc.py`.

Por que precisa de um kernel CAD: o STEP é B-rep paramétrico (planos, cilindros,
toros, NURBS). Não há triângulo nenhum no arquivo; a malha nasce aqui. Usa o
OpenCASCADE via `OCP` (pacote `cadquery-ocp`) — o mesmo kernel do FreeCAD.

    pip install --user --break-system-packages cadquery-ocp

O que sai, além dos buffers:

    partes    [{ nome, cor, triangulos, vertices }]  uma por sólido (ou por
              forma livre sem sólido), na mesma ordem em que as malhas foram
              concatenadas — o editor re-segmenta por componentes, mas o nome
              do sólido vem daqui
    unidade   a unidade declarada no STEP ('MM', 'M', 'INCH'…)
    bbox_mm   caixa envolvente em milímetros, para conferência
    fonte     nome do arquivo

UNIDADES E EIXOS. O OpenCASCADE lê o STEP e converte para milímetros, seja qual
for a unidade declarada (`xstep.cascade.unit`). Daqui sai em metros (×0,001) e
com a troca de eixos do projeto: STEP/IFC são Z-up, o viewer é Y-up, então
`(x, y, z) → (x, z, −y)`. É a mesma conversão do IFC — o STEP é o formato
irmão, ISO 10303-21, e o Inventor/SolidWorks/CATIA exportam Z-up.

CORES. `STEPCAFControl_Reader` com `SetColorMode(True)` traz a cor por face
(`XCAFDoc_ColorSurf`) quando existe, senão a cor do sólido (`ColorGen`), senão o
cinza padrão do viewer. Cor por face manda: vira cor por vértice na malha, com
os vértices da face separados (o dedup funde só posição+cor iguais, então faces
de cores diferentes não se soldam — exatamente o que o editor precisa para
re-segmentar).

SENTIDO DOS TRIÂNGULOS. `BRep_Tool.Triangulation` devolve os triângulos no
sentido da superfície paramétrica; uma face com `Orientation() == REVERSED`
tem a normal para dentro. Inverter a ordem nessas faces é obrigatório, senão
metade do sólido fica com a normal ao contrário e o viewer a mostra escura.

QUALIDADE. `--deflexao` (mm) é a distância máxima entre a malha e a superfície;
`--angulo` (rad) o desvio angular. 0,2 mm / 0,35 rad dá densidade parecida com
a das malhas do AltoQi (a peça 2831A09 de 152 mm sai com ~7.500 triângulos;
0,05 mm dobra para ~20.000).

Uso:
    python3 scripts/step_to_geo.py peca.stp saida.json [--deflexao 0.2] [--angulo 0.35]
    python3 scripts/step_to_geo.py peca.stp --info      # só inspeciona, não grava
"""
import argparse
import json
import os
import sys
import time

try:
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorGen, XCAFDoc_ColorSurf
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_LabelSequence
    from OCP.Quantity import Quantity_Color
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRep import BRep_Tool
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID, TopAbs_REVERSED
    from OCP.TopoDS import TopoDS
    from OCP.TopLoc import TopLoc_Location
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Interface import Interface_Static
    HAS_OCP = True
except ImportError:  # pragma: no cover
    HAS_OCP = False

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dedup import dedup  # noqa: E402  o mesmo dedup float32 do pipeline

MM_TO_M = 0.001
COR_PADRAO = (0.533, 0.588, 0.667)      # o cinza do viewer para malha sem cor


def _nome(label):
    n = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), n):
        return n.Get().ToExtString()
    return ''


def _cor(color_tool, shape, kinds):
    c = Quantity_Color()
    for kind in kinds:
        if color_tool.GetColor(shape, kind, c):
            return (round(c.Red(), 4), round(c.Green(), 4), round(c.Blue(), 4))
    return None


def abrir(caminho):
    """Lê o STEP num documento XCAF (formas + nomes + cores). Devolve (shape_tool, color_tool, rótulos livres, unidade)."""
    if not HAS_OCP:
        raise SystemExit('OCP não instalado — pip install --user --break-system-packages cadquery-ocp')
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'))
    app.NewDocument(TCollection_ExtendedString('MDTV-XCAF'), doc)
    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetNameMode(True)
    if reader.ReadFile(caminho) != IFSelect_RetDone:
        raise SystemExit(f'{caminho}: o OpenCASCADE não conseguiu ler o STEP')
    unidade = Interface_Static.CVal_s('xstep.cascade.unit')
    reader.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    labels = TDF_LabelSequence()
    st.GetFreeShapes(labels)
    # O documento, o leitor e a sequência TÊM de continuar vivos enquanto os
    # rótulos forem usados: são referências para dentro do documento, e o
    # Python liberá-los aqui dava segfault no primeiro `FindAttribute`.
    return {'doc': doc, 'reader': reader, 'st': st, 'ct': ct, 'labels': labels, 'unidade': unidade}


def _solidos(shape):
    """Sólidos de uma forma; se não houver nenhum (shell solta), a forma inteira."""
    # `ex.Current()` devolve uma referência que morre no `Next()`; guardar a
    # cópia tipada (TopoDS.Solid_s) evita o segfault ao tesselar depois.
    out = []
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        out.append(TopoDS.Solid_s(ex.Current()))
        ex.Next()
    return out or [shape]


def tesselar(shape, color_tool, cor_solido, deflexao, angulo, pos, col):
    """
    Malha de uma forma → acrescenta a `pos` (mm, Z-up, expandida) e `col`.
    Devolve o número de triângulos. Expandida de propósito: o dedup no fim
    solda o que tem mesma posição E cor, como o pipeline faz.
    """
    BRepMesh_IncrementalMesh(shape, deflexao, False, angulo, True)
    ntri = 0
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        face = TopoDS.Face_s(ex.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is not None:
            trsf = loc.Transformation()
            cor = _cor(color_tool, face, (XCAFDoc_ColorSurf,)) or cor_solido
            reversed_ = face.Orientation() == TopAbs_REVERSED
            nodes = [tri.Node(i).Transformed(trsf) for i in range(1, tri.NbNodes() + 1)]
            for i in range(1, tri.NbTriangles() + 1):
                a, b, c = tri.Triangle(i).Get()
                if reversed_:
                    b, c = c, b
                for k in (a, b, c):
                    p = nodes[k - 1]
                    pos.extend((p.X(), p.Y(), p.Z()))
                    col.extend(cor)
                ntri += 1
        ex.Next()
    return ntri


def converter(caminho, deflexao=0.2, angulo=0.35):
    t0 = time.time()
    x = abrir(caminho)
    st, ct, labels, unidade = x['st'], x['ct'], x['labels'], x['unidade']
    pos_mm, col = [], []
    partes = []
    bbox = Bnd_Box()
    for li in range(1, labels.Length() + 1):
        lab = labels.Value(li)
        shape = st.GetShape_s(lab)          # já com a posição da montagem aplicada
        BRepBndLib.Add_s(shape, bbox)
        nome_forma = _nome(lab) or os.path.splitext(os.path.basename(caminho))[0]
        cor_forma = _cor(ct, shape, (XCAFDoc_ColorSurf, XCAFDoc_ColorGen)) or COR_PADRAO
        solidos = _solidos(shape)
        for i, sol in enumerate(solidos, start=1):
            cor_sol = _cor(ct, sol, (XCAFDoc_ColorSurf, XCAFDoc_ColorGen)) or cor_forma
            antes = len(pos_mm) // 9
            n = tesselar(sol, ct, cor_sol, deflexao, angulo, pos_mm, col)
            partes.append({
                'nome': nome_forma if len(solidos) == 1 else f'{nome_forma} · sólido {i}',
                'cor': list(cor_sol),
                'triangulos': n,
                'triangulo_inicial': antes,
            })
    if not pos_mm:
        raise SystemExit(f'{caminho}: nenhuma face tesselável — o STEP tem só curvas ou pontos?')

    # mm, Z-up → m, Y-up  (x, y, z) → (x, z, −y)
    pos = [0.0] * len(pos_mm)
    for i in range(0, len(pos_mm), 3):
        x, y, z = pos_mm[i], pos_mm[i + 1], pos_mm[i + 2]
        pos[i] = round(x * MM_TO_M, 7)
        pos[i + 1] = round(z * MM_TO_M, 7)
        pos[i + 2] = round(-y * MM_TO_M, 7)

    geo, _n_orig, _n_dedup, _pct = dedup({'pos': pos, 'col': col})
    x0, y0, z0, x1, y1, z1 = bbox.Get()
    geo.update({
        'partes': partes,
        'unidade': unidade,
        'bbox_mm': [round(x1 - x0, 3), round(y1 - y0, 3), round(z1 - z0, 3)],
        'fonte': os.path.basename(caminho),
        'deflexao_mm': deflexao,
        'segundos': round(time.time() - t0, 2),
    })
    return geo


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('entrada')
    ap.add_argument('saida', nargs='?')
    ap.add_argument('--deflexao', type=float, default=0.2, help='desvio linear máximo, em mm (padrão 0,2)')
    ap.add_argument('--angulo', type=float, default=0.35, help='desvio angular máximo, em rad (padrão 0,35)')
    ap.add_argument('--info', action='store_true', help='só imprime o resumo')
    args = ap.parse_args()

    geo = converter(args.entrada, args.deflexao, args.angulo)
    nv, nt = len(geo['pos']) // 3, len(geo['idx']) // 3
    bb = geo['bbox_mm']
    fmt = lambda n: f'{n:,}'.replace(',', '.')
    print(f"{geo['fonte']}: unidade {geo['unidade']}, {len(geo['partes'])} parte(s), "
          f"{fmt(nv)} vértices, {fmt(nt)} triângulos, bbox {bb[0]:.1f}×{bb[1]:.1f}×{bb[2]:.1f} mm, "
          f"{geo['segundos']} s")
    for p in geo['partes']:
        print(f"  {p['nome']}: {p['triangulos']} △, cor {tuple(round(c, 2) for c in p['cor'])}")
    if args.info or not args.saida:
        return
    with open(args.saida, 'w', encoding='utf-8') as f:
        json.dump(geo, f, separators=(',', ':'))
    print(f'  → {args.saida} ({os.path.getsize(args.saida) / 1024:.0f} KB)')


if __name__ == '__main__':
    main()
