#!/usr/bin/env python3
"""
step_to_geo.py — tessela um arquivo STEP (.stp/.step, AP203/AP214/AP242) ou IGES (.igs/.iges)
para o JSON de geometria do viewer: `{ pos, col, idx }` em METROS, Y-up, indexado e
deduplicado — o mesmo contrato do `oq3d.py` e do `parse_ifc.py`.

Por que precisa de um kernel CAD: STEP e IGES são B-rep paramétrico (planos, cilindros,
toros, NURBS). Não há triângulo nenhum no arquivo; a malha nasce aqui. Usa o
OpenCASCADE via `OCP` (pacote `cadquery-ocp`) — o mesmo kernel do FreeCAD.

    pip install --user --break-system-packages cadquery-ocp

O que sai, além dos buffers:

    partes    [{ nome, cor, triangulos, vertices }]  uma por sólido (ou por
              forma livre sem sólido), na mesma ordem em que as malhas foram
              concatenadas — o editor re-segmenta por componentes, mas o nome
              do sólido vem daqui
    formato   'step' | 'iges'
    unidade   a unidade do kernel depois da leitura (sempre 'MM' — ver abaixo)
    bbox_mm   caixa envolvente em milímetros, para conferência
    volume_cm3  volume dos sólidos (soma), para conferência; ausente se só há cascas
    costurado   True quando a geometria veio em faces soltas e foi costurada aqui
    fonte     nome do arquivo

UNIDADES E EIXOS. O OpenCASCADE lê o arquivo e converte para milímetros, seja qual
for a unidade declarada (`xstep.cascade.unit`). Daqui sai em metros (×0,001) e
com a troca de eixos do projeto: STEP/IGES/IFC são Z-up, o viewer é Y-up, então
`(x, y, z) → (x, z, −y)`. É a mesma conversão do IFC — o STEP é o formato
irmão, ISO 10303-21, e o Inventor/SolidWorks/CATIA exportam Z-up.

IGES — FACES SOLTAS E COSTURA. O IGES não tem sólido (o tipo 186 MSBO quase nunca é
usado): o SolidWorks exporta cada face como superfície aparada (tipo 144) e o leitor
devolve N formas livres, uma por face, sem orientação consistente — tesselar assim dá
metade das normais para dentro (o viewer mostra a peça escura, e o volume assinado da
malha sai negativo; visto nos 10 IGES da Tupy, S7.17). O que se faz: `BRepBuilderAPI_Sewing`
(tolerância 0,01 mm) costura as faces em cascas, `BRepBuilderAPI_MakeSolid` +
`ShapeFix_Solid` fecham cada casca num sólido, e o **volume assinado decide a orientação**:
negativo → `Reverse()`. Isso cobre o caso em que a casca não fecha de todo (o TAMPÃO da
Tupy fica com 10 arestas livres e o `ShapeFix_Solid` não inverte). O mesmo caminho vale
para um STEP que venha só com cascas. As cores por face sobrevivem à costura porque as
faces costuradas são mapeadas de volta às originais (`Sewing.Modified`).

CORES. `STEPCAFControl_Reader`/`IGESCAFControl_Reader` com `SetColorMode(True)` trazem a
cor por face (`XCAFDoc_ColorSurf`) quando existe, senão a cor do sólido (`ColorGen`), senão
o cinza padrão do viewer. Cor por face manda: vira cor por vértice na malha, com
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
0,05 mm dobra para ~20.000). Peças com rosca (o adaptador Tupy) passam de 50.000 a 0,2 mm.

Uso:
    python3 -m bim_pipeline.cli.step_iges peca.stp saida.json [--deflexao 0.2] [--angulo 0.35]
    python3 -m bim_pipeline.cli.step_iges peca.igs saida.json
    python3 -m bim_pipeline.cli.step_iges peca.stp --info      # só inspeciona, não grava
"""
import argparse
import json
import os
import sys
import time

try:
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.IGESCAFControl import IGESCAFControl_Reader
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorGen, XCAFDoc_ColorSurf
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_LabelSequence
    from OCP.Quantity import Quantity_Color
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRep import BRep_Tool, BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID, TopAbs_SHELL, TopAbs_REVERSED
    from OCP.TopoDS import TopoDS, TopoDS_Compound
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Interface import Interface_Static
    HAS_OCP = True
except ImportError:  # pragma: no cover
    HAS_OCP = False

from bim_pipeline.geometria.dedup import dedup  # noqa: E402  o mesmo dedup float32 do pipeline
from bim_pipeline.geometria.eixos import MM_TO_M, plano_zup_para_viewer  # noqa: E402

COR_PADRAO = (0.533, 0.588, 0.667)      # o cinza do viewer para malha sem cor
EXT_IGES = ('.igs', '.iges')
EXT_STEP = ('.stp', '.step', '.p21')
TOLERANCIA_COSTURA_MM = 0.01


def formato_de(caminho):
    ext = os.path.splitext(caminho)[1].lower()
    if ext in EXT_IGES:
        return 'iges'
    if ext in EXT_STEP:
        return 'step'
    raise SystemExit(f'{caminho}: extensão {ext!r} não é STEP ({", ".join(EXT_STEP)}) nem IGES ({", ".join(EXT_IGES)})')


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
    """Lê o STEP/IGES num documento XCAF (formas + nomes + cores). Devolve dict com shape_tool, color_tool, rótulos livres, unidade, formato."""
    if not HAS_OCP:
        raise SystemExit('OCP não instalado — pip install --user --break-system-packages cadquery-ocp')
    formato = formato_de(caminho)
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'))
    app.NewDocument(TCollection_ExtendedString('MDTV-XCAF'), doc)
    reader = IGESCAFControl_Reader() if formato == 'iges' else STEPCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetNameMode(True)
    if reader.ReadFile(caminho) != IFSelect_RetDone:
        raise SystemExit(f'{caminho}: o OpenCASCADE não conseguiu ler o {formato.upper()}')
    unidade = Interface_Static.CVal_s('xstep.cascade.unit')
    reader.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    labels = TDF_LabelSequence()
    st.GetFreeShapes(labels)
    # O documento, o leitor e a sequência TÊM de continuar vivos enquanto os
    # rótulos forem usados: são referências para dentro do documento, e o
    # Python liberá-los aqui dava segfault no primeiro `FindAttribute`.
    return {'doc': doc, 'reader': reader, 'st': st, 'ct': ct, 'labels': labels, 'unidade': unidade, 'formato': formato}


def _explorar(shape, tipo, cast):
    # `ex.Current()` devolve uma referência que morre no `Next()`; guardar a
    # cópia tipada (TopoDS.Solid_s etc.) evita o segfault ao tesselar depois.
    out = []
    ex = TopExp_Explorer(shape, tipo)
    while ex.More():
        out.append(cast(ex.Current()))
        ex.Next()
    return out


def _solidos(shape):
    """Sólidos de uma forma; lista vazia se não houver nenhum."""
    return _explorar(shape, TopAbs_SOLID, TopoDS.Solid_s)


def volume_cm3(shape):
    """Volume assinado (cm³) pelas propriedades do B-rep: negativo = orientação para dentro."""
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass() / 1000.0


def costurar(shape, color_tool, tolerancia=TOLERANCIA_COSTURA_MM):
    """
    Faces soltas → sólidos orientados. Devolve `(solidos, cores_por_face, arestas_livres)`:
    `cores_por_face` mapeia cada face costurada à cor da face original (as faces novas não
    estão no documento XCAF, então `color_tool.GetColor` não as conhece).
    """
    faces = _explorar(shape, TopAbs_FACE, TopoDS.Face_s)
    sew = BRepBuilderAPI_Sewing(tolerancia)
    for f in faces:
        sew.Add(f)
    sew.Perform()
    sewn = sew.SewedShape()

    cores = TopTools_IndexedMapOfShape()
    lista = []
    for f in faces:
        cor = _cor(color_tool, f, (XCAFDoc_ColorSurf, XCAFDoc_ColorGen))
        if cor is None:
            continue
        nova = sew.Modified(f) if sew.IsModified(f) else (sew.ModifiedSubShape(f) if sew.IsModifiedSubShape(f) else f)
        if cores.Add(nova) == len(lista) + 1:
            lista.append(cor)

    solidos = []
    for shell in _explorar(sewn, TopAbs_SHELL, TopoDS.Shell_s):
        ms = BRepBuilderAPI_MakeSolid(shell)
        if not ms.IsDone():
            solidos.append(shell)      # casca que não vira sólido: tessela como está
            continue
        fx = ShapeFix_Solid(ms.Solid())
        fx.Perform()
        sol = TopoDS.Solid_s(fx.Solid()) if fx.Solid().ShapeType() == TopAbs_SOLID else ms.Solid()
        if volume_cm3(sol) < 0:
            sol.Reverse()
        solidos.append(sol)
    return solidos, (cores, lista), sew.NbFreeEdges()


def tesselar(shape, color_tool, cor_solido, deflexao, angulo, pos, col, cores_por_face=None):
    """
    Malha de uma forma → acrescenta a `pos` (mm, Z-up, expandida) e `col`.
    Devolve o número de triângulos. Expandida de propósito: o dedup no fim
    solda o que tem mesma posição E cor, como o pipeline faz.
    `cores_por_face` = `(TopTools_IndexedMapOfShape, [cor])` das faces costuradas.
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
            cor = None
            if cores_por_face is not None:
                i = cores_por_face[0].FindIndex(face)
                if i > 0:
                    cor = cores_por_face[1][i - 1]
            cor = cor or _cor(color_tool, face, (XCAFDoc_ColorSurf,)) or cor_solido
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


def _itens(x, caminho):
    """
    O que tesselar: `[(nome, forma, cor_da_forma)]`. STEP: um item por forma livre (montagem
    já posicionada). IGES: TODAS as formas livres num compound só — são as faces de uma peça,
    não peças distintas — com o nome do arquivo.
    """
    st, ct, labels = x['st'], x['ct'], x['labels']
    stem = os.path.splitext(os.path.basename(caminho))[0]
    formas = [(labels.Value(i), st.GetShape_s(labels.Value(i))) for i in range(1, labels.Length() + 1)]
    if x['formato'] == 'iges' and formas:
        comp = TopoDS_Compound()
        bb = BRep_Builder()
        bb.MakeCompound(comp)
        for _lab, sh in formas:
            bb.Add(comp, sh)
        return [(stem, comp, COR_PADRAO)]
    return [(_nome(lab) or stem, sh, _cor(ct, sh, (XCAFDoc_ColorSurf, XCAFDoc_ColorGen)) or COR_PADRAO)
            for lab, sh in formas]


def converter(caminho, deflexao=0.2, angulo=0.35):
    t0 = time.time()
    x = abrir(caminho)
    ct, unidade = x['ct'], x['unidade']
    pos_mm, col = [], []
    partes = []
    bbox = Bnd_Box()
    costurado = False
    arestas_livres = 0
    volume = 0.0
    for nome_forma, shape, cor_forma in _itens(x, caminho):
        BRepBndLib.Add_s(shape, bbox)
        solidos = _solidos(shape)
        cores_por_face = None
        if not solidos:
            solidos, cores_por_face, livres = costurar(shape, ct)
            costurado = True
            arestas_livres += livres
            if not solidos:
                solidos = [shape]
        for i, sol in enumerate(solidos, start=1):
            cor_sol = (cores_por_face[1][0] if cores_por_face and cores_por_face[1] else None) \
                or _cor(ct, sol, (XCAFDoc_ColorSurf, XCAFDoc_ColorGen)) or cor_forma
            antes = len(pos_mm) // 9
            n = tesselar(sol, ct, cor_sol, deflexao, angulo, pos_mm, col, cores_por_face)
            if sol.ShapeType() == TopAbs_SOLID:
                volume += volume_cm3(sol)
            partes.append({
                'nome': nome_forma if len(solidos) == 1 else f'{nome_forma} · sólido {i}',
                'cor': list(cor_sol),
                'triangulos': n,
                'triangulo_inicial': antes,
            })
    if not pos_mm:
        raise SystemExit(f'{caminho}: nenhuma face tesselável — o {x["formato"].upper()} tem só curvas ou pontos?')

    # mm, Z-up → m, Y-up (bim_pipeline.geometria.eixos)
    pos = plano_zup_para_viewer(pos_mm, MM_TO_M, casas=7)

    geo, _n_orig, _n_dedup, _pct = dedup({'pos': pos, 'col': col})
    x0, y0, z0, x1, y1, z1 = bbox.Get()
    geo.update({
        'partes': partes,
        'formato': x['formato'],
        'unidade': unidade,
        'bbox_mm': [round(x1 - x0, 3), round(y1 - y0, 3), round(z1 - z0, 3)],
        'fonte': os.path.basename(caminho),
        'deflexao_mm': deflexao,
        'segundos': round(time.time() - t0, 2),
    })
    if any(p['triangulos'] for p in partes) and volume:
        geo['volume_cm3'] = round(volume, 3)
    if costurado:
        geo['costurado'] = True
        geo['arestas_livres'] = arestas_livres
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
    extra = ''
    if geo.get('costurado'):
        extra = f", costurado ({geo['arestas_livres']} aresta(s) livre(s))"
    if 'volume_cm3' in geo:
        extra += f", volume {geo['volume_cm3']:.1f} cm³"
    print(f"{geo['fonte']}: {geo['formato'].upper()} em {geo['unidade']}, {len(geo['partes'])} parte(s), "
          f"{fmt(nv)} vértices, {fmt(nt)} triângulos, bbox {bb[0]:.1f}×{bb[1]:.1f}×{bb[2]:.1f} mm{extra}, "
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
