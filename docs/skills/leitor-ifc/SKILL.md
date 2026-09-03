---
name: leitor-ifc
description: Transforma arquivos IFC4 em JSONs de geometria prontos para consumo em viewers 3D. Cobre parse de entidades STEP, resolução de transforms, conversão de coordenadas, cores por face (IFCINDEXEDCOLOURMAP) e geração de buffers de vértices. Se a origem for uma biblioteca AltoQi, verifique antes se há um .aq — ele traz a mesma geometria.
version: 1.7.0
author: Bilds / carlosnetoaltoqi
---

# Skill: leitor-ifc

Você é especialista em extrair geometria de arquivos IFC4 e transformá-la em dados estruturados prontos para consumo em viewers 3D (Three.js, Babylon.js, ou qualquer renderer que aceite buffers de vértices e índices).

Esta skill não assume nenhum projeto, tecnologia de frontend, ou localização de arquivos específica. Ao ser invocada, pergunte ao usuário:

1. Onde estão os arquivos `.IFC` (diretório de entrada)?
2. Onde salvar os JSONs gerados (diretório de saída)?
3. Qual é o mapeamento entre nome do arquivo IFC e nome do JSON de saída?

---

## Antes de começar: existe um `.aq` junto?

**Se os IFCs vieram de uma biblioteca do AltoQi Builder, pare e verifique se há um `.aq` disponível.** Ele carrega a mesma geometria — malha, cor e miniatura — no BLOB `SIMBOLOGIA_3D.SIMBOLOGIA_3D`, em formato binário (OQ3D). Ler de lá é **85× a 421× mais rápido**, e o vínculo peça → geometria é chave estrangeira, o que dispensa casar nome de arquivo com nome de peça.

Onde o IFC do AltoQi é tessellated, os triângulos batem **exatamente** com o `.aq`. Onde é B-rep (`IFCADVANCEDBREP`), a forma converge a menos de 1 mm com tesselação independente.

Use a skill **`leitor-biblioteca-aq`** nesse caso. O IFC continua sendo a fonte certa quando:

- não há `.aq` (o IFC veio de outro CAD — Revit, CATIA, 3DEXPERIENCE);
- há peças em IFC **ausentes** do banco (acontece: peça distribuída solta, sem cadastro);
- é preciso a variante exata que o exportador gerou (o AltoQi exporta duas por peça — com e sem luva de encaixe — e o banco guarda só a canônica).

---

## O parser

O script de referência está em `scripts/parse_ifc.py` neste repositório. Ele aceita argumentos de linha de comando:

```bash
python3 parse_ifc.py <diretório_entrada> <diretório_saída>
```

Processa todos os `.IFC` ou `.ifc` do diretório de entrada que tenham entrada no `FILE_MAP`. Edite o `FILE_MAP` no topo do script antes de rodar.

**Exemplo:**
```bash
python3 scripts/parse_ifc.py ~/Downloads/ifcs ~/meu-projeto/data
```

---

## Estrutura dos arquivos IFC4

### Hierarquia típica de entidades
```
IFCELEMENTASSEMBLY  (montagem raiz — pode ser IFCPRODUCT em outros exportadores)
  └── IFCRELAGGREGATES
       ├── IFCBUILDINGELEMENTPROXY   (sub-peça: motor, voluta, flange…)
       ├── IFCBUILDINGELEMENTPROXY
       └── …
```

Cada produto tem:
- `ObjectPlacement` → `IFCLOCALPLACEMENT` — posição no espaço mundial
- `Representation` → `IFCPRODUCTDEFINITIONSHAPE` → geometria triangulada

### Dois caminhos de geometria tessellada + um B-rep

**Caminho A — face set direto:**
```
IFCBUILDINGELEMENTPROXY
  → IFCPRODUCTDEFINITIONSHAPE
    → IFCSHAPEREPRESENTATION (ContextType='Tessellation')
      → IFCTRIANGULATEDFACESET
```

**Caminho B — instância compartilhada:**
```
IFCBUILDINGELEMENTPROXY
  → IFCPRODUCTDEFINITIONSHAPE
    → IFCSHAPEREPRESENTATION (ContextType='MappedRepresentation')
      → IFCMAPPEDITEM
           MappingSource → IFCREPRESENTATIONMAP
                             → IFCSHAPEREPRESENTATION   ← nível fácil de esquecer
                               → IFCTRIANGULATEDFACESET
           MappingTarget → IFCCARTESIANTRANSFORMATIONOPERATOR3D
```

O caminho B é usado para peças repetidas (ex: parafusos idênticos). O `MappingTarget` e `MappingOrigin` são frequentemente identidade — mas o `IFCLOCALPLACEMENT` de cada proxy ainda precisa ser aplicado.

> **Armadilha:** o `IFCREPRESENTATIONMAP` **não** aponta direto para o face set — há um `IFCSHAPEREPRESENTATION` no meio:
>
> ```
> #82 = IFCREPRESENTATIONMAP(#83, #29)
> #29 = IFCSHAPEREPRESENTATION(#18,'Body','Tessellation',(#31))
> #31 = IFCTRIANGULATEDFACESET
> ```
>
> Procurar o face set direto dentro do `IFCREPRESENTATIONMAP` faz o parser desistir em silêncio e **descartar toda a geometria instanciada**. Numa bomba com 18 `IFCMAPPEDITEM`, isso custou 3.231 triângulos — 13,8% da peça, todos os parafusos.

**Caminho C — B-rep paramétrico (IFCADVANCEDBREP):**

Exportadores como **AltoQi Hidráulico / Amanco** geram `IFCADVANCEDBREP` em vez de `IFCTRIANGULATEDFACESET`. Esses arquivos não contêm geometria tessellada explícita — o parser manual não consegue extrair vértices. Detecção e fallback:

```python
try:
    import ifcopenshell
    import ifcopenshell.geom
    HAS_IFCOPENSHELL = True
except ImportError:
    HAS_IFCOPENSHELL = False

def parse_ifc_file(ifc_path, default_rgb=None):
    with open(ifc_path, encoding='utf-8', errors='replace') as f:
        content = f.read()

    # Detecção automática de B-rep
    if 'IFCADVANCEDBREP' in content and 'IFCTRIANGULATEDFACESET' not in content:
        if HAS_IFCOPENSHELL:
            return _parse_ifc_brep(ifc_path, default_rgb)
        else:
            print('AVISO: arquivo usa IFCADVANCEDBREP mas ifcopenshell não está instalado.')
            print('       Instale com: pip install ifcopenshell')
            return {'pos': [], 'col': []}
    # ... continua com parser manual
```

```python
def _parse_ifc_brep(ifc_path, default_rgb):
    """Tesselliza IFCADVANCEDBREP via ifcopenshell.geom."""
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    ifc_model = ifcopenshell.open(ifc_path)

    brep_types = [
        'IfcBuildingElementProxy', 'IfcElementAssembly',
        'IfcFlowFitting', 'IfcFlowTerminal', 'IfcFlowSegment',
        'IfcMember', 'IfcPlate', 'IfcBeam', 'IfcColumn',
        'IfcMechanicalFastener', 'IfcDiscreteAccessory',
    ]
    pos_out, col_out = [], []
    for btype in brep_types:
        for product in ifc_model.by_type(btype):
            try:
                shape = ifcopenshell.geom.create_shape(settings, product)
            except Exception:
                continue
            verts = shape.geometry.verts   # [x,y,z, x,y,z, ...]
            faces = shape.geometry.faces   # [i0,i1,i2, ...]
            if not verts or not faces:
                continue
            materials = getattr(shape.geometry, 'materials', [])
            mat_ids   = getattr(shape.geometry, 'material_ids', [])
            for tri_i in range(len(faces) // 3):
                if materials and tri_i < len(mat_ids):
                    try:
                        m = materials[mat_ids[tri_i]]
                        rgb = [m.diffuse.r, m.diffuse.g, m.diffuse.b]
                    except (IndexError, AttributeError):
                        rgb = default_rgb
                else:
                    rgb = default_rgb
                for vi in (faces[tri_i*3], faces[tri_i*3+1], faces[tri_i*3+2]):
                    x, y, z = verts[vi*3], verts[vi*3+1], verts[vi*3+2]
                    pos_out += [x, z, -y]   # IFC Z-up → Three.js Y-up (aplicado por ifcopenshell)
                    col_out += rgb
    return {'pos': pos_out, 'col': col_out}
```

> `USE_WORLD_COORDS` já aplica todo o `IFCLOCALPLACEMENT` — não aplicar transform manualmente em cima.

### Índices de atributos por exportador (IFCBUILDINGELEMENTPROXY / IFCELEMENTASSEMBLY)

O schema IFC4 define:
```
#id = IFCBUILDINGELEMENTPROXY(GlobalId, OwnerHistory, Name, Description,
                               ObjectType, ObjectPlacement, Representation, Tag, PredefinedType);
```
Índice 0-based: ObjectPlacement = **5**, Representation = **6**.

Exportadores como **3DEXPERIENCE / CATIA** preenchem `ObjectType` com `'AECARCHITECTURALELEMENT'` (campo não-nulo), o que **está correto** segundo o schema. A armadilha é usar `parts[4]` e `parts[5]` como fazem parsers escritos para exportadores que omitem `ObjectType='$'`.

```python
parts = split_top(args)
if len(parts) < 7:
    continue
lp_str  = parts[5]   # ObjectPlacement — índice 5 (não 4)
rep_str = parts[6]   # Representation  — índice 6 (não 5)
```

### Atributos do IFCTRIANGULATEDFACESET — índice correto do CoordIndex

```
IFCTRIANGULATEDFACESET(Coordinates, Normals, Closed, CoordIndex, PnIndex)
```

| Índice | Atributo | Conteúdo |
|--------|----------|----------|
| 0 | Coordinates | `#id` do IFCCARTESIANPOINTLIST3D |
| 1 | Normals | `$` ou lista de normais |
| 2 | Closed | `.T.` ou `.F.` |
| **3** | **CoordIndex** | `((i0,i1,i2),(i0,i1,i2),...)` |
| 4 | PnIndex | `$` ou lista de índices |

**Erro clássico:** ler `fs_parts[1]` (Normals) como CoordIndex. O resultado são índices nonsense que geram 0 triângulos válidos.

```python
fs_parts = split_top(fs_args)
if len(fs_parts) < 4:
    return
coord_index_str = fs_parts[3]   # CoordIndex está no índice 3
```

---

## O bug crítico — IFCLOCALPLACEMENT ignorado

**Este é o erro mais comum em parsers IFC caseiros.**

Parsers ingênuos aplicam apenas `IFCCARTESIANTRANSFORMATIONOPERATOR3D` (que em muitos exportadores é identidade) e ignoram o `IFCLOCALPLACEMENT`. O resultado: cada sub-peça renderiza na sua origem local — motor, voluta e flanges aparecem separados por metros.

**A transform correta por vértice:**
```
v_world = T_LP_hierarquia × T_mapping_target × inv(T_mapping_origin) × v_local
```

Na maioria dos exportadores CAD:
- `T_mapping_target` = identidade
- `T_mapping_origin` = identidade
- Então: `v_world = T_LP × v_local`

**Resolução recursiva do LP:**
```python
def resolve_lp(entity_index, lp_id):
    """Retorna a matriz 4×4 mundial acumulando toda a hierarquia de LocalPlacements."""
    _, args = entity_index[lp_id]
    parts = split_top(args)
    # parts[0] = PlacementRelTo (pai, $ = raiz mundial)
    # parts[1] = RelativePlacement (IFCAXIS2PLACEMENT3D)
    M_rel = axis2placement_mat(entity_index, int(parts[1].lstrip('#')))
    if parts[0] != '$':
        M_parent = resolve_lp(entity_index, int(parts[0].lstrip('#')))
        return mat_mul(M_parent, M_rel)
    return M_rel
```

### IFCAXIS2PLACEMENT3D → Matriz 4×4

```
IFCAXIS2PLACEMENT3D(Location, Axis, RefDirection)
  Location     = IFCCARTESIANPOINT  (translação)
  Axis         = IFCDIRECTION       (eixo Z local; padrão [0,0,1])
  RefDirection = IFCDIRECTION       (eixo X local; padrão [1,0,0])
```

Construção via Gram-Schmidt:
```
Z = normalize(Axis)
X = normalize(RefDirection − (RefDirection·Z)·Z)
Y = cross(Z, X)

M (row-major 4×4) =
  [ Xx  Yx  Zx  Tx ]
  [ Xy  Yy  Zy  Ty ]
  [ Xz  Yz  Zz  Tz ]
  [  0   0   0   1 ]
```

---

## Unidades — verificar sempre

O IFC declara a unidade em `IFCSIUNIT`. Verifique antes de processar:

```python
# Grep no arquivo:
import re
m = re.search(r'IFCSIUNIT\([^)]*LENGTHUNIT[^)]*\)', content)
```

Exportadores como CATIA declaram `MILLIMETRE` mas escrevem as coordenadas em metros — não aplicar fator de conversão nesses casos. Revit normalmente é consistente (declara e usa metros). Verifique a magnitude dos valores: coordenadas de um equipamento industrial típico em metros estão na faixa 0.01–5.0; se estiver na faixa 10–5000, está em milímetros de verdade.

---

## Conversão de eixos: IFC → Three.js (Y-up)

IFC usa Z-up. Three.js usa Y-up. Aplicar **após** o transform LP:

```python
# v = [x, y, z] já no espaço mundial IFC (Z-up)
THREE_x =  v[0]
THREE_y =  v[2]   # Z do IFC vira Y no Three.js
THREE_z = -v[1]   # Y do IFC inverte e vira Z
```

Para outros renderers (Babylon.js também é Y-up), a mesma conversão se aplica.
Para engines Z-up (Godot, Blender), não converter.

---

## Armadilhas de parsing STEP — regex e floats

### parse_floats: notação científica sem dígito fracionário

Exportadores **CATIA / 3DEXPERIENCE** escrevem coordenadas como `-4.E-16` ou `1.E+00` — notação científica onde **não há dígitos entre o ponto decimal e o expoente**. A regex canônica `[0-9]*\.?[0-9]+` exige ao menos um dígito após o ponto, então extrai `-4` e `-16` separados em vez de `-4.0E-16`.

**Sintoma:** sub-peças da montagem aparecem deslocadas por metros exatamente iguais ao expoente (ex: Z=-16m).

**Regex correta:**
```python
def parse_floats(s):
    """Extrai floats — suporta -4.E-16 (sem dígito após o ponto decimal)."""
    return [float(x) for x in re.findall(
        r'[-+]?(?:[0-9]+\.?[0-9]*|[0-9]*\.[0-9]+)(?:[eE][-+]?[0-9]+)?', s
    )]
```

A alternância `[0-9]+\.?[0-9]*` aceita parte inteira obrigatória com ponto e fração opcionais; `[0-9]*\.[0-9]+` aceita `.5` sem parte inteira. Juntas cobrem todos os formatos: `-4.E-16`, `1.E+00`, `-0.075`, `.5`, `3`.

### build_entity_index: regex greedy que consome o fechamento

Regex com grupo opcional não-anchorado **não faz backtrack** quando `(.*)` é greedy:

```python
# ERRADA — (.*)  consome ') ;' final; o grupo opcional nunca captura
m = re.match(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)(?:\)\s*;?)?\s*$', line)
# Resultado: args = '$,#46) ;'  → int('46) ;') → ValueError
```

```python
# CORRETA — ancora no último ) da linha
m = re.match(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*;?\s*$', line)
# Resultado: args = '$,#46'  → int('46') → OK
```

A âncora `\)\s*;?\s*$` força `(.*)` a recuar até encontrar o último `)` antes do fim da linha.

---

## Armadilha: split por vírgula em strings STEP

O formato STEP (`ISO-10303-21`) permite strings com aspas simples e vírgulas internas:
```
'MOTOR WEG 3,0CV T 220V'
```
Um `split(',')` simples quebra esse campo e desloca todos os índices subsequentes.

Use sempre o `split_top()` que respeita profundidade de parênteses e strings:

```python
def split_top(s):
    parts = []; depth = 0; in_str = False; cur = []
    for c in s:
        if c == "'":
            in_str = not in_str; cur.append(c)
        elif in_str:
            cur.append(c)
        elif c == ',' and depth == 0:
            parts.append(''.join(cur).strip()); cur = []
        else:
            if c == '(': depth += 1
            elif c == ')': depth -= 1
            cur.append(c)
    parts.append(''.join(cur).strip())
    return parts
```

---

## Cores por face — IFCINDEXEDCOLOURMAP

IFC4 armazena cor por face (triângulo) usando dois tipos de entidade **standalone** — elas existem no arquivo sem aparecer como filho de nenhuma outra entidade; a ligação é feita do mapa para o face set, não o contrário.

### Entidades envolvidas

```
IFCCOLOURRGBLIST(((r1,g1,b1),(r2,g2,b2),...))
  — paleta de cores RGB (0–1). Pode ter N cores.

IFCINDEXEDCOLOURMAP(FaceSetRef, Opacity, ColourRGBListRef, ColourIndex)
  — uma entrada por face set colorido. Campos:
    FaceSetRef      : #id do IFCTRIANGULATEDFACESET
    Opacity         : REAL (1.0 = totalmente opaco)
    ColourRGBListRef: #id do IFCCOLOURRGBLIST
    ColourIndex     : lista flat de inteiros 1-based, um por triângulo
```

`ColourIndex[i]` é o índice (base 1) da cor na paleta para o triângulo `i`. O número de entradas em `ColourIndex` é igual ao número de triângulos no `CoordIndex` do face set — relação 1:1 confirmada.

### Exemplo real (exportador AltoQi/CATIA)

```
#33 = IFCCOLOURRGBLIST(((0.835,0.071,0.071),(1.,1.,1.)));
      -- paleta: [vermelho, branco]

#32 = IFCINDEXEDCOLOURMAP(#31, 1., #33,
        (1,1,1,...,2,2,2,...,1,1,...));
      -- triângulos com índice 1 = vermelho (corpo da bomba)
      -- triângulos com índice 2 = branco (logotipo DANCOR)
```

Alguns face sets têm 3+ cores (ex: vermelho, latão/bronze, branco para peças de diferentes materiais).

### Como detectar e extrair

```python
def build_face_color_map(content, entity_index):
    """
    Retorna dict: {face_set_id (int) -> (colours_list, colour_indices)}
      colours_list   : list of [r, g, b] (0–1 floats)
      colour_indices : list of int (1-based, one per triangle)
    """
    import re
    face_color_map = {}
    for cm_id_str in re.findall(r'#(\d+)\s*=\s*IFCINDEXEDCOLOURMAP\s*\(', content):
        cm_id = int(cm_id_str)
        _, args = entity_index[cm_id]
        parts = split_top(args)
        face_set_id = int(parts[0].lstrip('#'))
        colour_list_id = int(parts[2].lstrip('#'))

        # Parse ColourIndex (4th arg): flat list of 1-based ints
        colour_indices = [int(x) for x in re.findall(r'\d+', parts[3])]

        # Parse IFCCOLOURRGBLIST: outer wrapper parens then (r,g,b) tuples
        _, cargs = entity_index[colour_list_id]
        inner = cargs.strip()
        if inner.startswith('('): inner = inner[1:]
        if inner.endswith(')'): inner = inner[:-1]
        colours = []
        for m in re.finditer(r'\(([0-9.,\s]+)\)', inner):
            vals = [float(x.strip()) for x in m.group(1).split(',') if x.strip()]
            colours.append(vals)

        face_color_map[face_set_id] = (colours, colour_indices)
    return face_color_map
```

### Como aplicar ao gerar a geometria

Quando um face set tem mapa de cor, **não compartilhe vértices** — expanda cada triângulo em 3 vértices independentes e repita a cor do triângulo nos 3. Isso elimina o `idx[]` e torna o `col[]` denso por vértice.

```python
def emit_triangles_with_color(coord_list, face_indices, lp_matrix,
                               colour_palette, colour_index_list,
                               pos_out, col_out):
    """
    coord_list      : list of [x,y,z] — pontos do IFCCARTESIANPOINTLIST3D
    face_indices    : list of (i0,i1,i2) — 1-based, do CoordIndex
    lp_matrix       : matriz 4×4 de transform (world space)
    colour_palette  : list of [r,g,b]
    colour_index_list: list of int (1-based), len == len(face_indices)
    pos_out, col_out: listas mutáveis de saída (append in-place)
    """
    for tri_idx, (i0, i1, i2) in enumerate(face_indices):
        r, g, b = colour_palette[colour_index_list[tri_idx] - 1]
        for vi in (i0, i1, i2):
            p = coord_list[vi - 1]                 # 1-based → 0-based
            v = apply_matrix(lp_matrix, p)          # world space
            pos_out += [v[0], v[2], -v[1]]         # IFC Z-up → Three.js Y-up
            col_out += [r, g, b]

# Sem cor (fallback):
def emit_triangles_uniform(coord_list, face_indices, lp_matrix,
                            default_rgb, pos_out, col_out, idx_out):
    base = len(pos_out) // 3
    for p in coord_list:
        v = apply_matrix(lp_matrix, p)
        pos_out += [v[0], v[2], -v[1]]
        col_out += default_rgb
    for i0, i1, i2 in face_indices:
        idx_out += [base + i0 - 1, base + i1 - 1, base + i2 - 1]
```

---

## Formato de saída JSON

```json
{
  "pos": [x0, y0, z0, x1, y1, z1, ...],
  "col": [r0, g0, b0, r1, g1, b1, ...],
  "idx": [a0, b0, c0, ...]
}
```

| Campo | Tipo | Quando presente | Descrição |
|---|---|---|---|
| `pos` | `float[]` | sempre | Vértices flat (3 floats por vértice), metros, Y-up |
| `col` | `float[]` | sempre | Cor por vértice, 0–1 RGB. Use `[0.72, 0.75, 0.80]` para aço sem cor IFC |
| `idx` | `int[]` | sem cores IFC | Índices de triângulos flat, 0-based. **Ausente** quando `IFCINDEXEDCOLOURMAP` presente (geometria expandida) |

**Regra:** se `data.idx` existe, geometria é indexada (cor uniforme); se ausente, cada 3 vértices de `pos[]` formam um triângulo e `col[]` é por vértice expandido.

---

## Integração com Three.js

```javascript
const data = await fetch('/caminho/para/modelo.json').then(r => r.json());

const geom = new THREE.BufferGeometry();
geom.setAttribute('position', new THREE.Float32BufferAttribute(data.pos, 3));

// Guard: col pode ser [] para geometria sem cores IFC (ex: conexões Amanco via IFCADVANCEDBREP)
const hasCol = data.col && data.col.length > 0;
if (hasCol) geom.setAttribute('color', new THREE.Float32BufferAttribute(data.col, 3));

// Guard: idx está ausente em geometria expandida (quando IFCINDEXEDCOLOURMAP presente)
if (data.idx) geom.setIndex(data.idx);
geom.computeVertexNormals();

// Centralizar na origem
geom.computeBoundingBox();
const center = geom.boundingBox.getCenter(new THREE.Vector3());
const size   = geom.boundingBox.getSize(new THREE.Vector3()).length();

// vertexColors: true ativa cores por vértice; quando true, color base = 0xffffff
// (Three.js multiplica: branco × cor do vértice = cor correta)
// Quando false, color = cinza padrão para aço sem cor IFC
const mat = new THREE.MeshStandardMaterial({
  vertexColors: hasCol,
  color: hasCol ? 0xffffff : 0x8896AA,
  metalness: 0.3,
  roughness: 0.6,
});
const mesh = new THREE.Mesh(geom, mat);
mesh.position.copy(center.negate());

// Câmera em função do tamanho do modelo
camera.position.set(size * 0.85, size * 0.32, size * 0.85);
camera.lookAt(0, 0, 0);
```

**Iluminação recomendada para peças industriais:**
```javascript
scene.add(new THREE.AmbientLight(0xffffff, 0.65));
const key = new THREE.DirectionalLight(0xffffff, 0.95);
key.position.set(2, 3, 2); scene.add(key);
const fill = new THREE.DirectionalLight(0xC8D8F0, 0.35);
fill.position.set(-2, 1, -1); scene.add(fill);
```

---

## Padrão de thumbnail estática + click-to-3D (performance)

Para páginas com múltiplos modelos, evite iniciar todos os viewers simultaneamente:

```javascript
// 1. Carregar o modelo e renderizar UM frame estático (sem loop)
renderer.render(scene, camera);

// 2. Ativar OrbitControls + animação somente ao clicar
canvas.addEventListener('click', () => {
  const controls = new OrbitControls(camera, canvas);
  controls.autoRotate = true;
  controls.enableDamping = true;
  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();
}, { once: true });

// 3. Carregar só quando o elemento entrar na viewport
const io = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (e.isIntersecting) { loadViewer(e.target); io.unobserve(e.target); }
  });
}, { rootMargin: '120px' });
```

---

## FILE_MAP — como configurar

No topo de `scripts/parse_ifc.py`, edite o dicionário `FILE_MAP`:

```python
FILE_MAP = {
    'nome-exato-do-arquivo.IFC': 'nome-de-saida.json',
    'outro-arquivo.IFC':         'outro-modelo.json',
}
```

O parser tenta correspondência exata primeiro; se não encontrar, faz fuzzy match por prefixo de 20 caracteres (útil para nomes com caracteres especiais como aspas em polegadas).

---

## O IFC como gabarito: conferir OUTRO parser contra ele

Um IFC bem lido é a melhor referência para validar um parser de outro formato que
descreva a mesma peça (foi assim que dois bugs do OQ3D apareceram). Em arquivo
**tessellated** dá para conferir de forma **exata** — e sem tesselador nenhum, porque os
vértices já estão no arquivo:

```python
import numpy as np, ifcopenshell
import ifcopenshell.util.placement as P

f = ifcopenshell.open(caminho)
pts, ntri = [], 0

def add(fs, M):
    global ntri
    c = np.array(fs.Coordinates.CoordList, float)
    pts.append((np.c_[c, np.ones(len(c))] @ M.T)[:, :3])
    ntri += len(fs.CoordIndex)

for prod in f.by_type('IfcProduct'):
    if not getattr(prod, 'Representation', None):
        continue
    M0 = P.get_local_placement(prod.ObjectPlacement)
    for r in prod.Representation.Representations:
        for it in r.Items:
            if it.is_a('IfcTriangulatedFaceSet'):
                add(it, M0)
            elif it.is_a('IfcMappedItem'):
                M = (M0
                     @ P.get_cartesiantransformationoperator3d(it.MappingTarget)
                     @ P.get_axis2placement(it.MappingSource.MappingOrigin))
                for sub in it.MappingSource.MappedRepresentation.Items:
                    if sub.is_a('IfcTriangulatedFaceSet'):
                        add(sub, M)
```

**Cada instância costuma ser um `IfcProduct` próprio**, com `MappingTarget` identidade —
quem posiciona é o `ObjectPlacement` do produto, não o operador de transformação.

### Quatro armadilhas ao comparar duas geometrias

| Armadilha | Por quê |
|---|---|
| **Comparar só a bounding box** | Uma rotação e a sua **transposta** podem gerar a mesma caixa. Uma bbox idêntica não prova que os transforms estão certos — compare o conjunto de pontos. |
| **Alinhar pelo centróide** | Um formato pode guardar sopa de triângulos (vértices repetidos) e o outro soldar os vértices; os centróides ficam com pesos diferentes. Alinhe pelo **canto da bounding box**. |
| **Igualdade de conjunto arredondado** | Coordenadas em cima da fronteira de arredondamento caem para lados diferentes nos dois lados. Compare **por tolerância** (~10 µm), ordenando os pontos únicos. |
| **Usar a contagem do `ifcopenshell` como verdade** | O tesselador descarta triângulos degenerados. Numa peça com um decalque plano de espessura zero ele devolveu 27.375 onde o STEP declara **27.425** — 50 a menos. Para arquivo tessellated, conte pelo `CoordIndex`, não pelo tesselador. |

A contagem de triângulos é o teste mais barato e mais decisivo: some `len(CoordIndex)`
dos face sets diretos com os dos mapped items (multiplicados pelas instâncias). Se o
outro parser não bate nesse número, ele está perdendo geometria.

---

## Escrever IFC que este parser lê — o caminho inverso

Feito em `bilds-bim-3d` (`www/apps/web/src/components/bim-editor/ifc-export.ts`), a partir
de um `{pos, col, idx}` em metros Y-up, e conferido com o próprio `parse_ifc.py`
(mesmos triângulos, 14 µm de desvio máximo) e com `ifcopenshell.validate` (0 erros). Cada
regra abaixo é uma armadilha deste documento vista pelo outro lado:

| Regra ao escrever | Por quê |
|---|---|
| **Uma entidade por linha**, `#id=TIPO(args);` | `build_entity_index` casa por linha; face set em várias linhas é descartado em silêncio |
| **A montagem não tem Representation** — geometria só nas `IFCBUILDINGELEMENTPROXY` | o parser processa `IFCELEMENTASSEMBLY` *e* proxies; malha nos dois conta em dobro |
| **`IFCSIUNIT … .METRE.` com valores em metros** | o parser não converte unidade, só troca eixos — a incoerência do CATIA (declara mm, escreve m) é a armadilha da seção "Unidades" |
| **Eixos: `ifc = (x, −z, y)`** a partir de Y-up | inverso exato de `ifc_to_threejs` (`x, z, −y`) |
| **Transformação rígida → `IFCLOCALPLACEMENT`; escala → assar nos vértices** | `IFCAXIS2PLACEMENT3D` só expressa rotação+translação. Com `C: (x,y,z)→(x,−z,y)`: `Axis = C·coluna_Y`, `RefDirection = C·coluna_X`, `Location = C·t` — o `axis2placement_mat` refaz por Gram-Schmidt |
| **`REAL` sempre com ponto, nunca `1e-7`** | `parse_floats` e a regex do `IFCCOLOURRGBLIST` (`[0-9.,\s]+`) não aceitam expoente |
| **`IFCINDEXEDCOLOURMAP(#fs, 1., #rgblist, (i,…))`**, índice **1-based**, um por triângulo | é o que `build_face_color_map` lê; o parser então expande os vértices e some com `idx` |
| **`IFCSTYLEDITEM` além do mapa de cor** | muitos viewers ignoram `IFCINDEXEDCOLOURMAP`; o estilo de superfície garante a cor dominante |
| **`Closed = .T.` só sem aresta de borda** | malha de fabricante tem 25–32% de arestas abertas; `.T.` seria mentira |
| **Strings: `'` → `''`, não-ASCII em `\X2\hhhh\X0\`** | "Incêndio" chega íntegro ao `ifcopenshell`; `split_top` respeita as aspas |
| **`IFCPROPERTYSET` ligado à montagem** | as informações do produto (nome, série, specs, potência) viajam com a geometria |

Ao conferir o arquivo gerado, valem as **quatro armadilhas de comparação** acima: compare o
conjunto de pontos por tolerância (~10 µm), espere alguns pontos na fronteira do
arredondamento (122 em 16.580 a 14 µm), e conte triângulos pelo `CoordIndex` — o
`ifcopenshell.geom` devolve menos (descarta degenerados).

---

## O parser como biblioteca — IFC entrando num editor

`parse_ifc.parse_ifc_file(caminho)` é importável e devolve `{pos, col}` (expandido, quando
há `IFCINDEXEDCOLOURMAP`) ou `{pos, col, idx}`. Para servir de **entrada** de um viewer ou
editor (feito em `bilds-bim-3d/scripts/ifc_to_geo.py`), faltam três coisas que o parser
não faz de propósito:

1. **Deduplicar** com a quantização float32 (`dedup.py`) — obrigatório antes de gravar.
2. **Decidir a unidade pela magnitude, não só pela declaração.** O parser não escala. O
   CATIA declara `MILLIMETRE` e escreve metros; o Revit declara e usa o mesmo. Regra que
   funciona: escalar ×0,001 **só** quando o arquivo declara `.MILLI.` **e** a bbox bruta
   passa de 50 (uma "peça de 50 m" é uma peça de 50 mm mal declarada). Guarde a decisão
   (`escala_aplicada`) junto da geometria — quem olhar um modelo 1000× errado precisa saber
   o que foi feito.
3. **Nomes das partes**: `ifcopenshell.open(f).by_type('IfcProduct')` com `Representation`
   dá nome e tipo de cada produto; sem `ifcopenshell`, uma regex sobre as entidades de
   elemento resolve. A divisão real em partes, no editor, é por componentes conexos.

Conferência: um IFC gerado pelo próprio editor (seção anterior) e reimportado tem de voltar
com a **mesma contagem de triângulos** — 27.937 na bomba 2CV editada, 7.506 na peça STEP.

---

## Diagnóstico de problemas

| Sintoma | Causa provável | Solução |
|---|---|---|
| Peças separadas por metros | LP ignorado | Verificar `resolve_lp()` — deve acumular hierarquia recursivamente |
| Modelo ~1000× maior que o esperado | Conversão mm→m desnecessária | Verificar magnitude das coordenadas brutas antes de converter |
| `ObjectPlacement` em índice errado | `split(',')` simples | Substituir por `split_top()` |
| Saída vazia / 0 triângulos | `IFCELEMENTASSEMBLY` sendo processado em vez dos filhos | Pular entidades do tipo assembly no loop principal |
| Espelhamento de partes | Sinal errado na conversão de eixos | `THREE_z = -IFC_y`, não `+IFC_y` |
| JSON corrompido em nome com vírgula | `FILE_MAP` com chave errada | Usar o nome exato do arquivo; aspas e vírgulas fazem parte do nome |
| Modelo cinza quando arquivo tem cores | `IFCINDEXEDCOLOURMAP` não extraído | Chamar `build_face_color_map()` antes do loop principal; passar mapa para `emit_triangles_with_color()` |
| 0 cores extraídas do `IFCCOLOURRGBLIST` | Regex busca `\(\d+,\d+,\d+\)` mas floats têm casas decimais | Usar `re.finditer(r'\(([0-9.,\s]+)\)', inner)` |
| `col[]` presente mas Three.js ignora | Material sem `vertexColors: true` | Definir `new THREE.MeshStandardMaterial({ vertexColors: true })` |
| Cores corretas mas model sem faceting | Geometria indexada com `vertexColors` | Cores por face exigem geometria expandida (sem `idx[]`) ou chamar `geom.toNonIndexed()` |
| Sub-peça deslocada por exatamente N metros | `parse_floats` quebra `-N.E-exp` em dois números | Usar regex `[-+]?(?:[0-9]+\.?[0-9]*\|[0-9]*\.[0-9]+)(?:[eE][-+]?[0-9]+)?` |
| `ValueError: invalid literal for int()` em `resolve_lp` | Regex greedy em `build_entity_index` inclui `) ;` nos args | Usar regex ancorada `(.*)\)\s*;?\s*$` |
| 0 vértices em IFC Amanco / AltoQi Hidráulico | Arquivo usa `IFCADVANCEDBREP`, não `IFCTRIANGULATEDFACESET` | Detectar `IFCADVANCEDBREP` e usar `_parse_ifc_brep()` via `ifcopenshell` |
| `ObjectPlacement` retorna `$` mas o produto tem placement | Lendo `parts[4]` em vez de `parts[5]` | Exportadores 3DEXPERIENCE preenchem `ObjectType` — ObjectPlacement está em parts[5] |
| CoordIndex retorna normais em vez de índices | Lendo `fs_parts[1]` (Normals) em vez de `fs_parts[3]` (CoordIndex) | `IFCTRIANGULATEDFACESET` tem 5 campos; CoordIndex é o índice 3 |
| Contagem do `ifcopenshell` menor que a do STEP | Tesselador descarta triângulos degenerados (decalque plano, espessura zero) | Em arquivo tessellated, contar por `len(CoordIndex)` — não pelo tesselador |
| Bbox bate mas a peça está visivelmente errada | Bbox não distingue uma rotação da sua transposta | Comparar conjunto de pontos, alinhado pelo canto da bbox |

---

## Histórico

**1.7.0** — Nova seção "O parser como biblioteca — IFC entrando num editor": o que falta ao `parse_ifc_file` para servir de entrada (dedup, unidade decidida pela declaração **e** pela magnitude, nomes via `ifcopenshell`) e a conferência por round-trip com o exportador da 1.6.0.

**1.6.0** — Nova seção "Escrever IFC que este parser lê": as regras para gerar IFC4 a partir de um `{pos,col,idx}` (uma entidade por linha, montagem sem Representation, METRE coerente, eixos `(x,−z,y)`, placement rígido vs escala assada, REAL sem expoente, mapa de cor 1-based + `IFCSTYLEDITEM`, `Closed` honesto, strings `\X2\`, propriedades). Cada uma é uma armadilha deste documento vista pelo lado de quem escreve. Conferido com o próprio `parse_ifc.py` (mesmos triângulos, 14 µm) e `ifcopenshell.validate` (0 erros).

**1.5.0** — Nova seção "O IFC como gabarito": como reconstruir a geometria de um arquivo tessellated direto do STEP (sem tesselador, exato) e usá-la para validar o parser de outro formato. Quatro armadilhas de comparação, todas encontradas na prática: bbox não distingue rotação de transposta, centróide não serve de âncora quando um lado solda vértices e o outro não, igualdade de conjunto arredondado falha na fronteira, e o `ifcopenshell` descarta degenerados (50 triângulos a menos que o STEP numa peça real).

**1.4.0** — Aviso no início: se a origem for uma biblioteca AltoQi, o `.aq` traz a mesma geometria e é muito mais rápido de ler (ver `leitor-biblioteca-aq`). Listados os casos em que o IFC continua sendo a fonte certa.

**1.3.1** — Bug do `IFCMAPPEDITEM`: falta um nível de indireção até o face set.

**1.3.0** — Cinco bugs de parsing STEP documentados com suas correções.
