---
name: leitor-step
description: Lê arquivos STEP (.stp/.step — ISO 10303 AP203/AP214/AP242, B-rep paramétrico de CAD como Inventor, SolidWorks, CATIA) e os tessela para o JSON de geometria do viewer ({pos, col, idx} em metros, Y-up) com OpenCASCADE em Python (OCP). Cobre unidades, nomes e cores via XCAF, sentido dos triângulos, montagens, deflexão, e as armadilhas de referência morta que dão segfault. O caminho de saída para IFC4 e .aq está nas skills irmãs.
version: 1.0.0
author: Bilds / carlosnetoaltoqi
---

# Skill: leitor-step

Você é especialista em transformar arquivos STEP em malha pronta para viewer 3D. Ao ser
invocada, pergunte o caminho do `.stp` e o destino do JSON. Não assuma diretórios.

---

## O que um STEP é — e por que o parser de IFC não basta

STEP é **ISO 10303-21**, o mesmo formato textual do IFC (`#id=TIPO(...);`), com outro
schema: `AUTOMOTIVE_DESIGN` (AP214), `CONFIG_CONTROL_DESIGN` (AP203) ou AP242. A
geometria é **B-rep paramétrico** — `ADVANCED_FACE` sobre `PLANE`, `CYLINDRICAL_SURFACE`,
`TOROIDAL_SURFACE`, `B_SPLINE_SURFACE` — com topologia de arestas e vértices. **Não há
triângulo nenhum no arquivo.** Ler as entidades é trivial; a malha exige um kernel CAD que
tessele as superfícies. Um STEP de 33 KB (26 faces) vira 7.500 triângulos.

Reconheça pelo cabeçalho:

```
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));   ← AP214
#32=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.));        ← unidade
#8=PRODUCT('2831A09','2831A09',$,(#7));                          ← nome da peça
```

## O kernel: OpenCASCADE via OCP

```bash
pip install --user --break-system-packages cadquery-ocp     # OpenCASCADE 7.9, ~165 MB
python3 -c "from OCP.STEPControl import STEPControl_Reader; print('OK')"
```

É o mesmo kernel do FreeCAD. O `ifcopenshell`, mesmo instalado, **não expõe** leitor de
STEP. Sem `--break-system-packages` o pip do Ubuntu recusa (PEP 668) — o pacote vai para
`~/.local`, não toca o Python do sistema.

Script de referência: `scripts/step_to_geo.py` do repositório `bilds-bim-3d`.

```bash
python3 scripts/step_to_geo.py peca.stp saida.json [--deflexao 0.2] [--angulo 0.35]
python3 scripts/step_to_geo.py peca.stp --info
```

## A receita, e cada armadilha dela

```python
from OCP.STEPCAFControl import STEPCAFControl_Reader        # XCAF: formas + nomes + cores
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
from OCP.Interface import Interface_Static

app = XCAFApp_Application.GetApplication_s()
doc = TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'))
app.NewDocument(TCollection_ExtendedString('MDTV-XCAF'), doc)
reader = STEPCAFControl_Reader(); reader.SetColorMode(True); reader.SetNameMode(True)
assert reader.ReadFile(caminho) == IFSelect_RetDone
unidade = Interface_Static.CVal_s('xstep.cascade.unit')     # 'MM' — o que o OCC converteu PARA
reader.Transfer(doc)
st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
labels = TDF_LabelSequence(); st.GetFreeShapes(labels)
```

| Armadilha | O que acontece | Regra |
|---|---|---|
| **Referência morta → segfault** | `doc`, `reader` e a `TDF_LabelSequence` saem de escopo e o Python os libera; o primeiro `label.FindAttribute` morre com *Segmentation fault*, sem traceback útil | Mantenha os três vivos enquanto usar os rótulos (devolva-os juntos). Rode com `python3 -X faulthandler` para achar a linha |
| **`ex.Current()` guardado para depois** | `TopExp_Explorer.Current()` devolve uma referência que morre no `Next()`; tesselar depois dá segfault | Copie tipado na hora: `TopoDS.Solid_s(ex.Current())`, `TopoDS.Face_s(...)` |
| **`GetColor` com rótulo** | `XCAFDoc_ColorTool.GetColor(label, tipo, cor)` não existe na binding — `TypeError` | Passe a **forma**: `ct.GetColor(shape, XCAFDoc_ColorSurf, cor)`; tente `ColorSurf` (face) antes de `ColorGen` (sólido) |
| **Unidade** | O OCC converte tudo para mm internamente, seja o arquivo em mm, m ou polegada | Depois da leitura, `×0.001` para metros — sempre, não "só se declarar mm". Confira a magnitude da bbox |
| **Eixos** | STEP é Z-up, como o IFC; o viewer é Y-up | `(x, y, z) → (x, z, −y)` — a mesma conversão do `parse_ifc.py` |
| **Sentido dos triângulos** | `BRep_Tool.Triangulation` segue a superfície paramétrica; face com `Orientation() == TopAbs_REVERSED` tem normal para dentro | Troque `b, c` nessas faces, senão metade do sólido fica escura no viewer |
| **Posição na montagem** | Sub-formas têm `TopLoc_Location` própria | `st.GetShape_s(label)` do rótulo livre já aplica; e `BRep_Tool.Triangulation_s(face, loc)` devolve o `loc` a aplicar em cada nó: `tri.Node(i).Transformed(loc.Transformation())` |
| **Deflexão** | Pouca = facetado; muita = pesado | `BRepMesh_IncrementalMesh(shape, 0.2, False, 0.35, True)` (mm, rad) dá densidade parecida com a do AltoQi: 152 mm → 7.500 △; 0,05 mm → 20.000 |

Tesselação de uma forma:

```python
BRepMesh_IncrementalMesh(shape, deflexao_mm, False, angulo_rad, True)
ex = TopExp_Explorer(shape, TopAbs_FACE)
while ex.More():
    face = TopoDS.Face_s(ex.Current()); loc = TopLoc_Location()
    tri = BRep_Tool.Triangulation_s(face, loc)
    if tri is not None:
        trsf = loc.Transformation()
        cor = cor_da_face or cor_do_solido or (0.533, 0.588, 0.667)
        rev = face.Orientation() == TopAbs_REVERSED
        nodes = [tri.Node(i).Transformed(trsf) for i in range(1, tri.NbNodes() + 1)]
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            if rev: b, c = c, b
            for k in (a, b, c):
                p = nodes[k - 1]
                pos += [p.X(), p.Y(), p.Z()]      # mm, Z-up — converter depois
                col += cor
    ex.Next()
```

Emita **expandido** (3 vértices por triângulo) e deduplique no fim com a quantização
float32 do pipeline (`scripts/dedup.py`): a chave inclui a cor, então faces de cores
diferentes não se soldam — e é isso que permite ao editor re-segmentar por componentes.

## Saída

O mesmo contrato das outras skills — `{ pos, col, idx }`, metros, Y-up — mais metadados
que valem a pena guardar: `partes` (nome e cor por sólido), `unidade`, `bbox_mm`, `fonte`,
`deflexao_mm`. No `bilds-bim-3d` esse JSON entra no editor 3D (`POST /step/importar`),
sai como IFC4 (`ifc-export.ts`, skill `leitor-ifc`) ou como `.aq` (`scripts/geo_to_aq.py`,
skill `leitor-biblioteca-aq`).

## Como conferir

- **Bbox** em mm contra o que o CAD mostra (a 2831A09 é 152 × 107 × 152 mm).
- **Contagem** de triângulos a duas deflexões: deve crescer ao afinar.
- **Aparência**: abrir no viewer; face escura = sentido errado.
- **Round-trip** pelos parsers do projeto depois de exportar: `parse_ifc.py` lê o IFC com
  os mesmos triângulos; `read_aq.py` + `oq3d.py` leem o `.aq` com a mesma bbox e cor.

## Diagnóstico

| Sintoma | Causa | Solução |
|---|---|---|
| `Segmentation fault` sem traceback | documento XCAF ou rótulos liberados; ou `ex.Current()` guardado | manter `doc`/`reader`/sequência vivos; copiar com `TopoDS.X_s()`; `-X faulthandler` |
| `TypeError: GetColor(): incompatible function arguments` | passou rótulo em vez de forma | `GetColor(shape, tipo, Quantity_Color())` |
| `error: externally-managed-environment` no pip | PEP 668 do Ubuntu | `pip install --user --break-system-packages cadquery-ocp` |
| Modelo 1000× maior | esqueceu o ×0,001 (o OCC entrega mm) | converter sempre para metros |
| Modelo deitado | esqueceu a troca de eixos Z-up → Y-up | `(x, z, −y)` |
| Faces escuras / interior visível | sentido não invertido em faces REVERSED | trocar `b, c` |
| Tudo cinza num STEP colorido | `SetColorMode(False)` ou leitor `STEPControl_Reader` (sem XCAF) | usar `STEPCAFControl_Reader` |
| 0 faces tesseláveis | STEP só com curvas/pontos (wireframe) ou `Transfer` não chamado | conferir `st.GetFreeShapes` > 0 |

## Histórico

**1.0.0** — Criada em 2026-09-03 a partir da importação da peça `2831A09.stp` (Autodesk
Inventor, AP214, mm) no editor 3D do `bilds-bim-3d`: receita XCAF completa, as duas
armadilhas de referência morta (documento e explorer) que deram segfault na primeira
versão, unidade/eixos/sentido, e a conferência por round-trip pelos parsers do projeto.
