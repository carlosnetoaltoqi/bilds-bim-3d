# IFC4 — leitura, escrita e verificação (`bim_pipeline.conversores.{parse_ifc,ifc}`, `web/src/components/bim-editor/ifc-export.ts`)

> Se a origem for uma biblioteca do AltoQi Builder, o `.aq` traz a mesma geometria e é 85× a 421× mais
> rápido de ler (`aq-formato.md`, `oq3d.md`) — o IFC é a fonte certa quando não há `.aq`, quando há peça em
> IFC ausente do banco, ou quando se precisa da variante exata que o exportador gerou.

---

## Leitura

### Estrutura do arquivo e os três caminhos de geometria

```
IFCELEMENTASSEMBLY  (montagem raiz — pode ser outro IFCPRODUCT)
  └── IFCRELAGGREGATES
       ├── IFCBUILDINGELEMENTPROXY   (sub-peça: motor, voluta, flange…)
       └── …
```

Cada produto tem `ObjectPlacement → IFCLOCALPLACEMENT` (posição no mundo) e
`Representation → IFCPRODUCTDEFINITIONSHAPE` (geometria).

**A — face set direto:**
```
IFCBUILDINGELEMENTPROXY → IFCPRODUCTDEFINITIONSHAPE →
  IFCSHAPEREPRESENTATION (Tessellation) → IFCTRIANGULATEDFACESET
```

**B — instância compartilhada (peças repetidas, ex.: parafusos):**
```
IFCBUILDINGELEMENTPROXY → IFCPRODUCTDEFINITIONSHAPE →
  IFCSHAPEREPRESENTATION (MappedRepresentation) →
    IFCMAPPEDITEM
      MappingSource → IFCREPRESENTATIONMAP
                        → IFCSHAPEREPRESENTATION      ← nível fácil de esquecer
                          → IFCTRIANGULATEDFACESET
      MappingTarget → IFCCARTESIANTRANSFORMATIONOPERATOR3D
```

> **Armadilha:** o `IFCREPRESENTATIONMAP` **não** aponta direto para o face set — há um
> `IFCSHAPEREPRESENTATION` no meio. Procurar o face set direto dentro do mapa faz o parser desistir
> em silêncio e **descartar toda a geometria instanciada** — numa bomba com 18 `IFCMAPPEDITEM` isso
> custou 13,8 % dos triângulos, todos os parafusos.

**C — B-rep (`IFCADVANCEDBREP`, `IFCFACETEDBREP`, extrusões):** não há triângulo no arquivo; o
parser de texto não extrai nada. Detectar a ausência de `IFCTRIANGULATEDFACESET` e tesselar com
`ifcopenshell.geom` (`USE_WORLD_COORDS`, que já aplica todo o `IFCLOCALPLACEMENT` — não aplicar
transform em cima). É o que `parse_ifc._parse_ifc_brep` faz, iterando `IfcElement`.

### Índices de atributos — não confiar em `$`

```
IFCBUILDINGELEMENTPROXY(GlobalId, OwnerHistory, Name, Description, ObjectType,
                        ObjectPlacement, Representation, Tag, PredefinedType)
```
`ObjectPlacement` é o índice **5**, `Representation` o **6** (0-based). Exportadores que preenchem
`ObjectType` (3DEXPERIENCE/CATIA escrevem `'AECARCHITECTURALELEMENT'`) estão certos pelo schema; a
armadilha é ler `parts[4]`/`parts[5]` como fazem parsers escritos para quem deixa `$`.

```
IFCTRIANGULATEDFACESET(Coordinates, Normals, Closed, CoordIndex, PnIndex)
```
`CoordIndex` é o índice **3**. Ler o 1 (`Normals`) dá índices sem sentido e 0 triângulos.

### O bug mais comum — IFCLOCALPLACEMENT ignorado

Parsers ingênuos aplicam só `IFCCARTESIANTRANSFORMATIONOPERATOR3D` (identidade em muitos
exportadores) e ignoram `IFCLOCALPLACEMENT`. Resultado: cada sub-peça renderiza na sua origem local —
motor, voluta e flanges aparecem separados por metros.

```
v_world = T_LP_hierarquia × T_mapping_target × inv(T_mapping_origin) × v_local
```
Na maioria dos exportadores CAD `T_mapping_target = T_mapping_origin = I`, logo `v_world = T_LP × v_local`.
`resolve_lp()` acumula a hierarquia (`PlacementRelTo` → pai) recursivamente, com cache.

### IFCAXIS2PLACEMENT3D → matriz 4×4

```
IFCAXIS2PLACEMENT3D(Location, Axis, RefDirection)   Axis = Z local (padrão [0,0,1]); RefDirection = X local (padrão [1,0,0])

Z = normalize(Axis)
X = normalize(RefDirection − (RefDirection·Z)·Z)     ← Gram-Schmidt
Y = cross(Z, X)

M (row-major) =
  [ Xx  Yx  Zx  Tx ]
  [ Xy  Yy  Zy  Ty ]
  [ Xz  Yz  Zz  Tz ]
  [  0   0   0   1 ]
```

### Conversão de eixos: IFC (Z-up) → viewer (Y-up)

Aplicar **depois** do transform. É a regra única de `bim_pipeline.geometria.eixos`:

```python
viewer = (v[0], v[2], -v[1])     # Z do IFC vira Y; Y do IFC inverte e vira Z
```
Babylon.js é Y-up também; para engines Z-up (Godot, Blender) não converter.

### Unidades — declaração e magnitude

O IFC declara a unidade em `IFCSIUNIT(… .LENGTHUNIT. …)`. Alguns exportadores (CATIA) declaram
`MILLIMETRE` e escrevem em metros; Revit declara e usa o mesmo. O `parse_ifc` **não escala** — só
troca eixos. Quem decide é o conversor (`ifc.converter`), pela declaração **e** pela magnitude:
escalar ×0,001 **só** quando o arquivo declara `.MILLI.` **e** a bbox bruta passa de 50 (uma
"peça de 50 m" é uma peça de 50 mm mal declarada); `.CENTI.` idem com ×0,01. A decisão sai em
`escala_aplicada` junto da geometria — quem olhar um modelo 1000× errado precisa saber o que foi
feito. Ordem de grandeza para conferir a olho: equipamento industrial em metros fica em 0,01–5,0;
em 10–5000 está de fato em milímetros.

### Vértices outlier

Alguns exportadores produzem `IFCLOCALPLACEMENT` aberrante (translação de 5 m, 16 m) em
sub-componentes. O parser aplica corretamente — o defeito está nos dados. Identificar pela
bounding box do JSON e filtrar com limiar por tipo de equipamento, heurística:

- bomba compacta: 3 m
- válvula / conexão: 2 m
- equipamento grande (chiller): 10 m

### IFCINDEXEDCOLOURMAP — cores por face

Duas entidades **standalone** — não são filhas de nenhuma outra; a ligação vai do mapa para o face
set, não o contrário:

```
IFCCOLOURRGBLIST(((r,g,b),(r,g,b),…))                              paleta, 0–1
IFCINDEXEDCOLOURMAP(FaceSetRef, Opacity, ColourRGBListRef, ColourIndex)
```
`ColourIndex[i]` é o índice **base 1** da cor do triângulo `i`; tem tantas entradas quanto o
`CoordIndex` (1:1). Um face set pode ter 3 ou mais cores (corpo, latão, decalque).

Quando há mapa de cor: emitir triângulos **expandidos** (3 vértices por triângulo, sem compartilhar)
com a cor repetida nos três; o `idx` desaparece e `col` fica denso por vértice. O `dedup` compacta
depois — e como a cor entra na chave, faces de cores diferentes nunca se soldam, o que é o que
permite ao editor re-segmentar por componentes conexos. Regex para a paleta: `\(([0-9.,\s]+)\)` —
`\(\d+,\d+,\d+\)` devolve 0 cores porque os floats têm casas decimais.

### Parsing do texto STEP (ISO 10303-21) — as armadilhas que valem para qualquer consumidor

**`split_top()` em vez de `split(',')`.** Strings STEP podem ter vírgula dentro
(`'MOTOR 3,0CV T 220V'`); o split simples desloca todos os índices seguintes. `split_top` respeita
profundidade de parênteses e aspas.

**`parse_floats`: notação científica sem dígito fracionário.** CATIA/3DEXPERIENCE escrevem
`-4.E-16` e `1.E+00`. A regex canônica `[0-9]*\.?[0-9]+` exige dígito após o ponto e extrai `-4` e
`-16` separados. **Sintoma:** sub-peça deslocada por exatamente N metros iguais ao expoente
(Z = −16 m). Regex certa:

```python
r'[-+]?(?:[0-9]+\.?[0-9]*|[0-9]*\.[0-9]+)(?:[eE][-+]?[0-9]+)?'
```
A alternância cobre `-4.E-16`, `1.E+00`, `-0.075`, `.5` e `3`.

**`build_entity_index`: regex gulosa que consome o fechamento.** Com grupo opcional não ancorado,
`(.*)` engole o `) ;` final e `args` vira `'$,#46) ;'` → `int('46) ;')` → `ValueError` em `resolve_lp`:

```python
# ERRADA
r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)(?:\)\s*;?)?\s*$'
# CORRETA — a âncora força (.*) a recuar até o último )
r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*;?\s*$'
```

**Uma entidade por linha.** O índice casa `#id=TIPO(args);` linha a linha; uma entidade quebrada em
várias linhas (um face set grande, por exemplo) é **descartada em silêncio**. Quem escreve IFC para
este parser tem de respeitar isso (ver "Escrita").

### Dois caminhos: exato em Python puro × rápido via `ifcopenshell`

O `parse_ifc.py` indexa o arquivo inteiro por regex em Python. É exato para biblioteca de peça
(tessellated, com `IFCINDEXEDCOLOURMAP`), mas num IFC de projeto (Revit, 124 MB, 2,5 milhões de
entidades, B-rep facetado com 718 mil faces) leva minutos e gigabytes — e, atrás de uma requisição
HTTP síncrona, vira "Failed to fetch" sem log. Regra do conversor (`ifc.converter`, `LIMIAR_MB = 20`):

| Arquivo | Caminho |
|---|---|
| ≤ 20 MB **e** com `IFCTRIANGULATEDFACESET` | `parse_ifc.parse_ifc_file` — exato, lê `IFCINDEXEDCOLOURMAP` |
| maior, ou sem face set tessellated (`IFCCONNECTEDFACESET`, `IFCFACETEDBREP`, extrusões), ou `--forcar-rapido` | `ifcopenshell.geom.iterator(settings, f, n_cpus)` com `USE_WORLD_COORDS` |

O rápido também é o fallback quando o exato não acha geometria. Detalhes que custaram tempo:

- **Cor por material.** `shape.geometry.materials` e `material_ids` (um por triângulo), vindos de
  `IfcSurfaceStyle`. No `ifcopenshell` 0.8, `diffuse.r/g/b` são **métodos** — sem `()` não lança
  exceção e sai cinza em tudo. Tratar os dois casos (`_rgb_do_material`). O `IFCINDEXEDCOLOURMAP`
  **não** é lido neste caminho.
- **Unidade.** Com `USE_WORLD_COORDS` a saída já vem em **metros**, mesmo com `MILLIMETRE` declarado
  — a heurística da escala não dispara (a bbox fica pequena).
- **Degenerados.** O tesselador descarta triângulos de área zero (decalque plano): devolve menos
  triângulos do que o `CoordIndex` declara. Não é perda de geometria — mas por isso a contagem do
  `ifcopenshell` não serve de verdade para arquivo tessellated.
- **Dedup vetorizado.** 760 mil triângulos = 2,3 milhões de vértices expandidos; o dedup em laço
  Python demoraria minutos. `numpy.unique` sobre a chave `(pos, cor)` em float32 (view estruturada,
  `return_index` + `return_inverse`) faz em segundos — é o `dedup_arrays` da biblioteca.
- **Um produto só não paraleliza.** O iterador divide por produto; um único proxy gigante roda numa
  thread (221 s e 3,6 GB para as 718 mil faces). Isso tem de ficar **fora da requisição HTTP**:
  202 com um id e status consultável (o `stderr` do conversor serve de progresso).

O que o conversor acrescenta ao parser, de propósito fora dele: **dedup** com a quantização float32,
**unidade** decidida pela magnitude (acima), **partes** (nome e tipo de cada `IfcProduct` com
representação — via `ifcopenshell` ou, sem ele, regex sobre as entidades de elemento; a divisão
real em partes no editor é por componentes conexos), `bbox_mm`, `caminho` usado, `segundos`, e um
`aviso` acima de `--max-triangulos` (não corta a malha; só avisa que o editor no browser vai sofrer).

### Saída

O contrato do viewer: `pos` (float, metros, Y-up), `col` (RGB 0–1 por vértice), `idx` (0-based).
`parse_ifc_file` devolve `{pos, col}` expandido quando há mapa de cor ou `{pos, col, idx}` quando é
uniforme; o conversor sempre entrega indexado e deduplicado, mais `partes`, `unidade`,
`escala_aplicada`, `bbox_mm`, `fonte`, `cor_por_face`, `caminho`. Cor padrão para aço sem cor:
`[0.72, 0.75, 0.80]` no parser, `(0.533, 0.588, 0.667)` no conversor (o cinza do viewer).

---

## Escrita — o que um IFC precisa ter para o leitor lê-lo

O exportador do editor (`ifc-export.ts`) escreve IFC4 a partir de `{pos, col, idx}` em metros Y-up,
na mesma estrutura que o exportador do AltoQi produz:

```
IFCPROJECT → IFCSITE → IFCBUILDING → IFCBUILDINGSTOREY
  └─ IFCELEMENTASSEMBLY (o produto; SEM Representation própria)
       └─ IFCRELAGGREGATES → IFCBUILDINGELEMENTPROXY (uma por parte do editor)
            ├─ ObjectPlacement → IFCLOCALPLACEMENT → IFCAXIS2PLACEMENT3D
            └─ Representation → IFCPRODUCTDEFINITIONSHAPE → IFCSHAPEREPRESENTATION('Body','Tessellation')
                 → IFCTRIANGULATEDFACESET ← IFCINDEXEDCOLOURMAP (cor por face)
                                          ← IFCSTYLEDITEM (cor para viewers que ignoram o mapa)
```

Cada regra é uma armadilha da leitura vista pelo outro lado:

| Regra ao escrever | Por quê |
|---|---|
| **Uma entidade por linha**, `#id=TIPO(args);` | `build_entity_index` casa por linha; face set em várias linhas é descartado em silêncio |
| **A montagem não tem Representation** — malha só nas `IFCBUILDINGELEMENTPROXY` | o parser processa `IFCELEMENTASSEMBLY` *e* proxies; geometria nos dois conta em dobro |
| **`IFCSIUNIT … .METRE.` com valores em metros** | o parser não converte unidade; declarar mm e escrever m é a incoerência da seção "Unidades" |
| **Eixos: `ifc = (x, −z, y)`** a partir de Y-up | inverso exato de `(x, z, −y)`; é `viewer_para_zup` em `eixos.py` |
| **Transformação rígida → `IFCLOCALPLACEMENT`; escala → assada nos vértices** | `IFCAXIS2PLACEMENT3D` só expressa rotação + translação. Matriz ortonormal com det > 0 vai como placement; senão os vértices saem em coordenadas de mundo e o placement é identidade |
| **`REAL` sempre com ponto, nunca expoente** (`1.`, não `1`; `0.0000001`, não `1e-7`) | `parse_floats` e a regex da paleta (`[0-9.,\s]+`) não aceitam `e` |
| **`IFCINDEXEDCOLOURMAP(#fs, 1., #rgblist, (i,…))`**, índice **base 1**, um por triângulo, tamanho igual ao `CoordIndex` | é o que `build_face_color_map` lê; o parser então expande os vértices e some com `idx` |
| **`IFCSTYLEDITEM` além do mapa de cor** | muitos viewers ignoram `IFCINDEXEDCOLOURMAP`; o estilo de superfície garante a cor dominante |
| **`Closed = .T.` só sem aresta de borda** | malha de fabricante costuma ter um quarto a um terço das arestas abertas; `.T.` seria mentira — o exportador decide por `partStats` |
| **Strings: `'` → `''`; não-ASCII em `\X2\hhhh\X0\`** | "Incêndio" chega íntegro ao `ifcopenshell`; `split_top` respeita as aspas |
| **`IFCPROPERTYSET` ligado à montagem** | nome, série, specs, potência e conexões viajam com a geometria |

**Como montar o `IFCAXIS2PLACEMENT3D` a partir de uma matriz do viewer.** Com a conversão de eixos
`C: (x, y, z) → (x, −z, y)` aplicada às **colunas** da rotação:

```
Axis         = C · coluna_Y      (o "para cima" do viewer é o Z do IFC)
RefDirection = C · coluna_X
Location     = C · t
```
O `axis2placement_mat` do leitor refaz a base por Gram-Schmidt e chega à mesma matriz. Montar
Axis/RefDirection sem converter os eixos deixa a parte rotacionada fora do lugar — com a mesma
contagem de triângulos, o que engana quem só conta.

---

## Verificação de ida e volta

O `ifc-export.ts` é conferido pelo próprio leitor (`web/tools/testes-editor.sh`, exercitado por
`tests/servicos/test_editor_roundtrips.py`): exporta a geometria, relê com `parse_ifc.parse_ifc_file`
e compara com o `bake()` esperado; com `ifcopenshell` instalado, ainda lê o pset com acento e roda
`ifcopenshell.validate` (0 erros).

### O método certo — e o errado que passou por certo

**Não comparar conjuntos de pontos arredondados.** Coordenadas em cima da fronteira de
arredondamento caem para lados diferentes nos dois lados, e a fração "na fronteira" cresce com a
malha: num modelo de 44 mil vértices, buckets de 10 µm acusaram **2,2 % de divergência** onde o
desvio real, ponto a ponto, era **1,4 µm** — um limite percentual não resolve.

**O que se faz:**

1. **Parear cada vértice com o vizinho mais próximo do outro lado a ≤ 2 µm** — grade de célula
   igual à tolerância, busca nos 27 vizinhos; um par a ≤ tolerância está sempre numa célula vizinha.
2. **Nos dois sentidos** (esperado → IFC lido e IFC lido → esperado): só um sentido não pega vértice
   a mais no IFC.
3. **Exigir zero sem par** e imprimir o desvio máximo.
4. **Sair 1 na falha** — toda linha passa por `check()`; uma métrica que só imprime "FALHA" não protege nada.
5. **Autoteste sabotado** (`ROUNDTRIP_SABOTAR_IFC=1`): move um vértice do esperado 1 mm **depois** de
   exportar; a conferência tem de acusar nos dois sentidos e o script sair 1. Variável separada da
   sabotagem do `mesh-model`, senão o `set -e` para antes de chegar ao IFC.

**A tolerância vem da precisão de escrita, não do teste passar:** o exportador escreve `REAL` com 6
decimais em metros (0,5 µm por eixo) e o `IFCLOCALPLACEMENT` idem → pior caso teórico ~1,7 µm →
**2 µm**. Medido em duas dezenas de geometrias: 0 a 1,5 µm; peças com menos de 3 partes dão 0,00 µm
(o round-trip não aplica rotação nem escala). **Rastro da correção:** a skill 1.6.0 citava "14 µm de
desvio máximo" e aceitava "122 em 16.580 vértices na fronteira" — era artefato da comparação por
conjuntos arredondados, não erro do exportador; corrigido na 1.8.1 e nos documentos de origem.

**Contar triângulos pelo `CoordIndex`**, não pelo tesselador: o `ifcopenshell.geom` descarta
degenerados e devolve menos. Um IFC gerado pelo editor e reimportado tem de voltar com a mesma
contagem — é o teste mais barato e mais decisivo.

**Custo:** ~10 s por geometria grande em Python puro (laço sobre 44 mil vértices com numpy por
ponto). Para uma só, ok; numa varredura de centenas de geometrias, conte dezenas de minutos.

### O IFC como gabarito — validar o leitor de OUTRO formato (OQ3D)

Um IFC tessellated bem lido é a melhor referência para validar o parser de outro formato que
descreva a mesma peça — foi assim que dois bugs do leitor OQ3D apareceram. Em arquivo tessellated
a conferência é **exata e sem tesselador**: os vértices já estão no arquivo.

```python
import numpy as np, ifcopenshell
import ifcopenshell.util.placement as P

f = ifcopenshell.open(caminho); pts, ntri = [], 0
def add(fs, M):
    global ntri
    c = np.array(fs.Coordinates.CoordList, float)
    pts.append((np.c_[c, np.ones(len(c))] @ M.T)[:, :3]); ntri += len(fs.CoordIndex)

for prod in f.by_type('IfcProduct'):
    if not getattr(prod, 'Representation', None): continue
    M0 = P.get_local_placement(prod.ObjectPlacement)
    for r in prod.Representation.Representations:
        for it in r.Items:
            if it.is_a('IfcTriangulatedFaceSet'): add(it, M0)
            elif it.is_a('IfcMappedItem'):
                M = (M0 @ P.get_cartesiantransformationoperator3d(it.MappingTarget)
                        @ P.get_axis2placement(it.MappingSource.MappingOrigin))
                for sub in it.MappingSource.MappedRepresentation.Items:
                    if sub.is_a('IfcTriangulatedFaceSet'): add(sub, M)
```

Em B-rep (`IFCADVANCEDBREP`) a tesselação é independente e só a **forma** é comparável (converge a
menos de 1 mm). Armadilhas ao comparar as duas geometrias — as três específicas do OQ3D primeiro:

| Armadilha | Por quê |
|---|---|
| **Bocais** — somar os marcadores de conexão na bounding box | no OQ3D os bocais são componentes próprios, identificáveis pela cor (verde/azul); não são produto e inflam a bbox em ~2 cm. Filtrá-los antes de medir |
| **Tolerância** — igualdade de conjunto arredondado | a fronteira de arredondamento (acima). Parear vizinho mais próximo a ≤ 2 µm nos dois sentidos, zero sem par; **não** "comparar por tolerância de ~10 µm" |
| **Instâncias** — rotação lida na ordem errada | no OQ3D a rotação da instância é column-major; lida como row-major sai **transposta** e a instância vai para fora do lugar **sem mudar a contagem de triângulos** — e uma rotação e a sua transposta podem dar a **mesma bbox**. No IFC, `MappingTarget` costuma ser identidade: cada instância é um `IfcProduct` próprio e quem posiciona é o `ObjectPlacement` |
| Comparar só a bounding box | não distingue rotação de transposta (acima). Compare o conjunto de pontos |
| Alinhar pelo centróide | um formato guarda sopa de triângulos (vértices repetidos), o outro solda; os centróides ficam com pesos diferentes. Alinhe pelo **canto da bbox** |
| Usar a contagem do `ifcopenshell` como verdade | descarta degenerados. Em arquivo tessellated, some `len(CoordIndex)` dos face sets diretos e dos mapped items (× instâncias) |

---

## Diagnóstico rápido

| Sintoma | Causa provável |
|---|---|
| Peças separadas por metros | `IFCLOCALPLACEMENT` ignorado — `resolve_lp` tem de acumular a hierarquia |
| Sub-peça deslocada por exatamente N metros | `parse_floats` quebra `-N.E-exp` em dois números |
| `ValueError: invalid literal for int()` em `resolve_lp` | regex gulosa em `build_entity_index` inclui `) ;` nos args |
| Modelo 1000× maior | conversão mm→m aplicada a arquivo que já está em metros — conferir a magnitude |
| Modelo cinza com cores no arquivo | `IFCINDEXEDCOLOURMAP` não extraído; ou, no caminho rápido, `diffuse.r` lido como atributo em vez de método |
| Espelhamento | sinal errado: `viewer_z = −ifc_y`, não `+ifc_y` |
| Parafusos/detalhes faltando | `IFCMAPPEDITEM` sem o nível `IFCSHAPEREPRESENTATION` intermediário |
| Saída vazia | arquivo B-rep sem `ifcopenshell`; ou o loop processa a montagem em vez dos filhos |
| IFC exportado abre em dobro | a montagem recebeu Representation |
| IFC exportado: parser ignora um face set | entidade em várias linhas |
| IFC exportado: parte rotacionada fora do lugar | Axis/RefDirection montados sem converter os eixos |
| Round-trip acusa "N sem par" com desvio ≤ 2 µm | erro real (ou a fixture mudou — o teste usa a primeira geometria do storage) |
| Contagem do `ifcopenshell` menor que a do STEP | degenerados descartados — contar pelo `CoordIndex` |

---

## Onde está no código

| O quê | Onde |
|---|---|
| Parser de texto STEP/IFC4 (caminho exato): `split_top`, `parse_floats`, `build_entity_index`, `resolve_lp`, `axis2placement_mat`, `build_face_color_map`, `emit_colored`/`emit_uniform`, `_parse_ifc_brep`, `parse_ifc_file` | `biblioteca/bim_pipeline/conversores/parse_ifc.py` (CLI `python3 -m bim_pipeline.cli.parse_ifc <ifc> <dir> [--slug]`) |
| Conversor IFC → contrato do viewer: escolha exato × rápido (`LIMIAR_MB`), `rapido_ifcopenshell`, `_rgb_do_material`, unidade pela magnitude, `partes`, `escala_aplicada` | `biblioteca/bim_pipeline/conversores/ifc.py` (CLI `python3 -m bim_pipeline.cli.ifc <ifc> <saida.json> [--info] [--forcar-rapido] [--max-triangulos]`) |
| Troca de eixos e escalas (única implementação) | `biblioteca/bim_pipeline/geometria/eixos.py` |
| Dedup float32 por `(pos, cor)`, escalar e vetorizado | `biblioteca/bim_pipeline/geometria/dedup.py` |
| Exportador IFC4 do editor (`real()`, `str()`, placement rígido × escala assada, mapa de cor, `IFCSTYLEDITEM`, `Closed`, psets) | `web/src/components/bim-editor/ifc-export.ts` |
| Conferência de ida e volta (pareamento a ≤ 2 µm, exit 1, `ROUNDTRIP_SABOTAR_IFC`) | `web/tools/testes-editor.sh` + `web/tools/roundtrip-ifc-export.mts`; teste em `tests/servicos/test_editor_roundtrips.py` |
| Serviço que expõe a conversão (`POST /tesselar`, multipart `file` `.ifc`/`.stp`/`.igs`) — síncrono, stateless, :4300 | `servicos/conversores/src/conversores.controller.ts`; despacho por extensão em `pacotes/base/src/biblioteca.ts` (`Biblioteca.tesselar` → CLI `ifc` ou `step_iges`) |
| Importar um IFC como **catálogo** (assíncrono, na fila) | `servicos/criador-de-catalogos` (`POST /importacoes`, arquivo CAD) |

## Ver também

- `docs/conhecimento/step-iges.md` — o formato irmão (mesmo ISO 10303-21, outro schema), B-rep tesselado com OpenCASCADE, mesmo contrato de saída.
- `docs/conhecimento/oq3d.md` — a geometria dentro do `.aq` e a correspondência OQ3D ↔ IFC (`TQi3DReusedObject` ↔ `IFCMAPPEDITEM`).
- `docs/conhecimento/aq-formato.md` — quando o `.aq` dispensa o IFC.
- `docs/conhecimento/diagnostico.md` — tabela sintoma → causa de todo o pipeline.
- `docs/skills/leitor-ifc/SKILL.md` — a versão portável desta página, com o exemplo de integração Three.js.
