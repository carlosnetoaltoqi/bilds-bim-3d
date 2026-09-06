# STEP e IGES — B-rep paramétrico tesselado com OpenCASCADE (`bim_pipeline.conversores.step_iges`)

> Os dois formatos irmãos do IFC (mesmo ISO 10303-21, outro schema) e o kernel CAD que os transforma em malha.

---

## O que STEP e IGES são — e por que o parser de texto do IFC não serve

STEP é **ISO 10303-21**, o mesmo formato textual do IFC (`#id=TIPO(...);`), com outro schema:
`AUTOMOTIVE_DESIGN` (AP214), `CONFIG_CONTROL_DESIGN` (AP203) ou AP242. IGES (`.igs/.iges`) é o
formato irmão mais velho, de outro kernel de escrita, mas a mesma ideia de fundo. Em ambos a
geometria é **B-rep paramétrico** — `ADVANCED_FACE` sobre `PLANE`, `CYLINDRICAL_SURFACE`,
`TOROIDAL_SURFACE`, `B_SPLINE_SURFACE` (STEP) ou superfícies aparadas tipo 144 (IGES). **Não há
triângulo nenhum no arquivo.** Ler as entidades é trivial (é o mesmo texto do IFC); a malha exige
um kernel CAD que tessele as superfícies. Um STEP de 33 KB com 26 faces vira 7.500 triângulos.

Cabeçalho típico de STEP:

```
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));   ← AP214
#32=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.));        ← unidade
```

Cabeçalho típico de IGES (SolidWorks): `SolidWorks IGES file using analytic representation for
surfaces`, unidade `2HMM`. É a assinatura de que o arquivo vai chegar como faces soltas (ver
adiante) — nenhum sólido, nenhuma casca fechada.

STEP e IGES são **Z-up**, como o IFC; o viewer é **Y-up**. A conversão de eixos é a mesma
implementação do projeto (`bim_pipeline.geometria.eixos.plano_zup_para_viewer`), não uma cópia:
`(x, y, z) → (x, z, −y)`.

## O kernel: OpenCASCADE via OCP

```bash
pip install --user --break-system-packages cadquery-ocp     # OpenCASCADE 7.9, ~165 MB
python3 -c "from OCP.STEPControl import STEPControl_Reader; print('OK')"
```

É o mesmo kernel do FreeCAD. O `ifcopenshell`, mesmo instalado, **não expõe** leitor de STEP nem
de IGES. Sem `--break-system-packages` o pip do Ubuntu recusa (PEP 668) — o pacote vai para
`~/.local`, não toca o Python do sistema.

## A leitura: XCAF traz forma, nome e cor juntos

`STEPCAFControl_Reader` (STEP) e `IGESCAFControl_Reader` (IGES) — não os leitores simples
`STEPControl_Reader`/`IGESControl_Reader`, que devolvem só forma — carregam o arquivo num
documento XCAF (`TDocStd_Document`), o mesmo mecanismo do OpenCASCADE que guarda a árvore de
montagem com nomes e cores por face ou por sólido:

```python
app = XCAFApp_Application.GetApplication_s()
doc = TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'))
app.NewDocument(TCollection_ExtendedString('MDTV-XCAF'), doc)
reader = STEPCAFControl_Reader()          # ou IGESCAFControl_Reader() para .igs/.iges
reader.SetColorMode(True); reader.SetNameMode(True)
assert reader.ReadFile(caminho) == IFSelect_RetDone
unidade = Interface_Static.CVal_s('xstep.cascade.unit')     # 'MM' — o que o OCC converteu PARA
reader.Transfer(doc)
st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
labels = TDF_LabelSequence(); st.GetFreeShapes(labels)
```

**Unidade.** O OCC converte tudo para milímetros internamente, seja o arquivo em mm, m ou
polegada — a leitura de `xstep.cascade.unit` diz para onde converteu, não o que o arquivo
declarava. Depois da leitura, `×0,001` para metros sempre, não "só se declarar mm".

**Montagens e vários sólidos.** `st.GetFreeShapes(labels)` devolve uma forma livre por
componente de topo; cada uma pode conter mais de um sólido (`TopAbs_SOLID` via
`TopExp_Explorer`). O contrato de saída junta tudo em `partes`: uma entrada por sólido
tesselado (ou por forma livre sem sólido nenhum), na ordem em que as malhas foram
concatenadas — é daqui que o nome de cada parte vem, mesmo depois do editor re-segmentar por
componentes conexos.

### Armadilhas de referência morta — o segfault sem traceback

| Armadilha | O que acontece | Regra |
|---|---|---|
| **Documento/leitor/sequência liberados** | `doc`, `reader` e a `TDF_LabelSequence` saem de escopo e o Python os libera; o primeiro `label.FindAttribute` seguinte morre com *Segmentation fault*, sem traceback útil | Manter os três vivos enquanto os rótulos forem usados (devolvê-los juntos, como faz `abrir()`) |
| **`ex.Current()` guardado para depois** | `TopExp_Explorer.Current()` devolve uma referência que morre no `Next()`; tesselar mais tarde dá segfault | Copiar tipado na hora: `TopoDS.Solid_s(ex.Current())`, `TopoDS.Face_s(...)` |
| **`GetColor` com rótulo** | `XCAFDoc_ColorTool.GetColor(label, tipo, cor)` não existe na binding — `TypeError` | Passar a **forma**: `ct.GetColor(shape, XCAFDoc_ColorSurf, cor)`; tentar `ColorSurf` (face) antes de `ColorGen` (sólido) |

Rodar com `python3 -X faulthandler` é o que localiza a linha quando um desses escapa.

## Tesselação: deflexão, sentido dos triângulos, cor

```python
BRepMesh_IncrementalMesh(shape, deflexao_mm, False, angulo_rad, True)
```

`--deflexao` (mm) é a distância máxima entre a malha e a superfície; `--angulo` (rad) o desvio
angular. **0,2 mm / 0,35 rad** dá densidade parecida com a das malhas do AltoQi (uma peça de
152 mm sai com ~7.500 triângulos); **0,05 mm dobra** para ~20.000. Peças com rosca (um adaptador
roscado, por exemplo) passam de 50.000 triângulos a 0,2 mm — a rosca é geometria helicoidal fina
e o kernel precisa de muito mais facetas para acompanhar a curvatura.

**Sentido dos triângulos.** `BRep_Tool.Triangulation_s(face, loc)` devolve os triângulos no
sentido da superfície paramétrica; uma face com `Orientation() == TopAbs_REVERSED` tem a normal
para dentro. Trocar `b, c` nessas faces é obrigatório, senão metade do sólido fica com a normal
ao contrário e o viewer a mostra escura por dentro.

**Cor.** `SetColorMode(True)` traz a cor por face (`XCAFDoc_ColorSurf`) quando existe, senão a cor
do sólido (`XCAFDoc_ColorGen`), senão o cinza padrão do viewer, `(0.533, 0.588, 0.667)`. Cor por
face manda: vira cor por vértice na malha, com os vértices da face emitidos **expandidos** (3
por triângulo, sem compartilhar) — o dedup no fim (`bim_pipeline.geometria.dedup`) solda só
posição **e** cor iguais, então faces de cores diferentes nunca se fundem, e é isso que permite
ao editor re-segmentar por componentes.

## Saída

O mesmo contrato das outras skills — `{ pos, col, idx }`, metros, Y-up, indexado e deduplicado —
mais metadados de conferência:

| Campo | O que é |
|---|---|
| `partes` | `[{ nome, cor, triangulos, triangulo_inicial }]`, uma por sólido (ou por forma livre sem sólido) |
| `formato` | `'step'` ou `'iges'` |
| `unidade` | a unidade do kernel depois da leitura (sempre `'MM'`) |
| `bbox_mm` | caixa envolvente em milímetros, para conferência contra o que o CAD mostra |
| `volume_cm3` | volume dos sólidos (soma), para conferência; ausente se só há cascas sem sólido |
| `costurado` | `True` quando a geometria veio em faces soltas e foi costurada aqui (ver adiante) |
| `arestas_livres` | contagem de arestas que a costura não fechou; presente sempre que `costurado` está |
| `fonte` | nome do arquivo |
| `deflexao_mm`, `segundos` | parâmetro usado e tempo de conversão |

## IGES — faces soltas: a costura e a orientação pelo volume (skill 1.1.0)

O IGES é o caso em que o CAD de origem não grava sólido nenhum. Exportadores de CAD paramétrico
como o SolidWorks gravam "using analytic representation for surfaces": **cada face vira uma
superfície aparada (tipo 144) isolada** — o tipo 186 (MSBO, o "sólido" do IGES) quase nunca é
usado. `IGESCAFControl_Reader` devolve então N formas livres, uma por face — 160 a 639 por peça,
num catálogo real de conexões — sem orientação consistente entre elas: tesselar assim dá metade
das normais para dentro (peça escura no viewer) e o volume assinado da malha sai negativo em 8 de
10 arquivos vistos.

A receita que `step_iges.converter` aplica sempre que uma forma livre não contém nenhum
`TopAbs_SOLID` (vale igualmente para um STEP que só traga cascas — STEP de sólido não passa por
aqui):

1. **Juntar todas as formas livres da peça num `TopoDS_Compound`.** São as faces de UMA peça, não
   peças distintas — é por isso que o IGES vira um item só em `_itens()`, ao contrário do STEP,
   onde cada forma livre já é uma peça posicionada.
2. **`BRepBuilderAPI_Sewing(0,01 mm)`** com todas as faces do compound → `SewedShape()` com uma
   casca (peças simples) ou várias (montagens: um acoplamento angular e um tê mecânico têm 6).
3. **Por casca: `BRepBuilderAPI_MakeSolid` + `ShapeFix_Solid().Perform()`** — fecha o sólido
   quando a costura deu uma casca fechada.
4. **`BRepGProp.VolumeProperties_s`: volume negativo ⇒ `solid.Reverse()`.** Esta é a decisão
   central da receita: o `ShapeFix_Solid` **não** inverte uma casca que não fechou de todo — um
   tampão com furo, por exemplo, fica com 10 arestas livres e o fix não decide o sentido sozinho.
   É o volume assinado do B-rep que sempre decide, feche ou não a casca.
5. **Cores por remapeamento, não por busca direta.** As faces costuradas (`SewedShape()`) são
   objetos novos, fora do documento XCAF — `color_tool.GetColor` não as reconhece. A cor original
   de cada face é levada para a face nova via `sew.Modified(face)` (ou `ModifiedSubShape` quando
   a face não mudou de identidade), guardada num `TopTools_IndexedMapOfShape` antes de tesselar;
   sem esse mapa a peça inteira cairia no cinza padrão do viewer.

**Conferência:** o volume assinado da malha (soma de `a·(b×c)/6` sobre os triângulos, a mesma
fórmula do round-trip de IFC) tem de bater com o volume do B-rep dentro de ±1%, e ambos
positivos. O que a costura não consegue fechar fica com `arestas_livres > 0` e é reportado
honestamente — o campo `costurado` nunca aparece como verdadeiro para uma peça que na prática
ficou aberta; é a contagem de arestas livres que carrega essa informação, não a omissão dela.

**Prova por teste sintético.** `tests/biblioteca/test_step_to_geo.py` escreve, com o próprio
OpenCASCADE, uma caixa (`BRepPrimAPI_MakeBox`) e a grava em IGES só com as 6 faces soltas — sem
sólido, sem orientação garantida, exatamente como um exportador de CAD faria. O teste confere que
a costura fecha as 6 faces num sólido com o volume exato da caixa, zero arestas livres, e que o
volume assinado da malha final é positivo (normais para fora). A mesma caixa escrita em STEP
(sólido nativo no arquivo) passa pelo caminho antigo sem costurar e chega à mesma malha — prova
que a receita de costura só entra quando não há sólido, e não muda o resultado quando há.

Custo medido num catálogo real de conexões: 3 a 22 s por peça a 0,2 mm de deflexão (a rosca de um
adaptador e um flange passam de 55 mil triângulos e dominam o tempo).

## Como conferir

- **Bbox** em mm contra o que o CAD mostra.
- **Contagem** de triângulos a duas deflexões: deve crescer ao afinar.
- **Aparência**: abrir no viewer; face escura = sentido errado (ou IGES sem costurar).
- **Volume** (IGES/cascas): volume da malha ≈ volume B-rep, ±1%, ambos positivos.
- **Round-trip** pelos parsers do projeto depois de exportar: `parse_ifc.py` lê o IFC gerado com
  os mesmos triângulos; `read_aq.py` + `oq3d.py` leem o `.aq` com a mesma bbox e cor.

## Diagnóstico

| Sintoma | Causa | Solução |
|---|---|---|
| `Segmentation fault` sem traceback | documento XCAF ou rótulos liberados; ou `ex.Current()` guardado | manter `doc`/`reader`/sequência vivos; copiar com `TopoDS.X_s()`; `-X faulthandler` |
| `TypeError: GetColor(): incompatible function arguments` | passou rótulo em vez de forma | `GetColor(shape, tipo, Quantity_Color())` |
| `error: externally-managed-environment` no pip | PEP 668 do Ubuntu | `pip install --user --break-system-packages cadquery-ocp` |
| Modelo 1000× maior | esqueceu o ×0,001 (o OCC entrega mm) | converter sempre para metros |
| Modelo deitado | esqueceu a troca de eixos Z-up → Y-up | `(x, z, −y)`, mesma função de `eixos.py` |
| Faces escuras / interior visível | sentido não invertido em faces `REVERSED` | trocar `b, c` |
| Peça inteira escura, volume da malha negativo (IGES) | faces soltas não costuradas, ou costuradas sem checar o volume | costurar → `MakeSolid` → `ShapeFix_Solid` → `Reverse()` se `volume_cm3 < 0` |
| Peça cai no cinza padrão apesar de o CAD ter cor (IGES) | cor buscada nas faces costuradas em vez de remapeada | usar `sew.Modified(face_original)` antes de tesselar |
| `arestas_livres` alto e `costurado` marcado mesmo assim | esperado — o campo relata honestamente o que não fechou; não é bug, é a peça que não fechou no CAD de origem | reportar a contagem, não esconder |
| Tudo cinza num arquivo colorido | `SetColorMode(False)` ou leitor sem XCAF (`STEPControl_Reader`/`IGESControl_Reader`) | usar `STEPCAFControl_Reader`/`IGESCAFControl_Reader` |
| 0 faces tesseláveis | arquivo só com curvas/pontos (wireframe) ou `Transfer` não chamado | conferir `st.GetFreeShapes` > 0 |

## Correção mantida

A versão 1.0.0 da skill `leitor-step` citava uma rota `POST /step/importar` como destino do JSON
gerado. Essa rota não existe mais no serviço atual: a conversão hoje é exposta por
`POST /tesselar` no serviço de conversores (abaixo), e a importação de uma peça CAD para virar
produto de catálogo passa pelo serviço de criação de catálogos, não por uma rota dedicada de
STEP.

## Onde está no código

| O quê | Onde |
|---|---|
| Leitura XCAF (STEP e IGES), costura (`costurar`), volume assinado (`volume_cm3`), tesselação (`tesselar`), montagem do contrato (`converter`), `formato_de` | `biblioteca/bim_pipeline/conversores/step_iges.py` (CLI `python3 -m bim_pipeline.cli.step_iges <peca.stp\|.igs> <saida.json> [--deflexao] [--angulo] [--info]`) |
| Troca de eixos e escalas (única implementação, compartilhada com IFC) | `biblioteca/bim_pipeline/geometria/eixos.py` |
| Dedup float32 por `(pos, cor)` | `biblioteca/bim_pipeline/geometria/dedup.py` |
| Prova por teste sintético (caixa em IGES sem sólido, caixa em STEP com sólido) | `tests/biblioteca/test_step_to_geo.py` |
| Serviço que expõe a conversão (`POST /tesselar`, multipart `file` `.stp`/`.step`/`.igs`/`.iges`/`.ifc`) — síncrono, stateless | `servicos/conversores/src/conversores.controller.ts`; despacho por extensão em `pacotes/base/src/biblioteca.ts` (`formatoDe`, `Biblioteca.tesselar` → CLI `step_iges` ou `ifc`) |
| Importar uma peça CAD (STEP/IGES) como **produto de catálogo** (assíncrono, na fila) | `servicos/criador-de-catalogos` (`ImportacoesService`, `PipelineService`) |

## Ver também

- `docs/conhecimento/geometria.md` — o contrato `{pos, col, idx}`, eixos e dedup compartilhados por todos os conversores.
- `docs/conhecimento/ifc.md` — o formato irmão (mesmo ISO 10303-21, outro schema), leitura por parser de texto e por `ifcopenshell`, mesmo contrato de saída.
- `docs/conhecimento/plugin-cad-catalogo-web.md` — de onde vêm os IGES reais usados para validar a costura, e o pipeline de importação de catálogo que os consome.
- `docs/skills/leitor-step/` — a versão portável desta página, com o histórico 1.0.0 → 1.1.0.
