---
name: leitor-ifc
description: Transforma arquivos IFC4 em JSONs de geometria prontos para consumo em viewers 3D. Cobre parse de entidades STEP, resolução de transforms, conversão de coordenadas, cores por face (IFCINDEXEDCOLOURMAP), geração de buffers de vértices e deduplicação de vértices pós-parse.
version: 1.5.0
author: Bilds / carlosnetoaltoqi
---

# Skill: leitor-ifc

Você é especialista em extrair geometria de arquivos IFC4 e transformá-la em dados estruturados prontos para consumo em viewers 3D (Three.js, Babylon.js, ou qualquer renderer que aceite buffers de vértices e índices).

Esta skill não assume nenhum projeto, tecnologia de frontend, ou localização de arquivos específica. Ao ser invocada, pergunte ao usuário:

1. Onde estão os arquivos `.IFC` (diretório de entrada)?
2. Onde salvar os JSONs gerados (diretório de saída)?
3. Qual é o mapeamento entre nome do arquivo IFC e nome do JSON de saída?

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

### Dois caminhos de geometria

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
           MappingSource → IFCREPRESENTATIONMAP → IFCTRIANGULATEDFACESET
           MappingTarget → IFCCARTESIANTRANSFORMATIONOPERATOR3D
```

O caminho B é usado para peças repetidas (ex: parafusos idênticos). O `MappingTarget` e `MappingOrigin` são frequentemente identidade — mas o `IFCLOCALPLACEMENT` de cada proxy ainda precisa ser aplicado.

### Schema de campos das entidades principais

**IFCBUILDINGELEMENTPROXY** (e todos os subtipos de IFCELEMENT):
```
[0] GlobalId
[1] OwnerHistory
[2] Name
[3] Description
[4] ObjectType          ← string, não é referência
[5] ObjectPlacement     ← #id do IFCLOCALPLACEMENT
[6] Representation      ← #id do IFCPRODUCTDEFINITIONSHAPE
[7] Tag
[8] PredefinedType
```
Erro clássico: ler `parts[4]` como ObjectPlacement — é ObjectType (string), `int()` falha silenciosamente.

**IFCLOCALPLACEMENT**:
```
[0] PlacementRelTo      ← #id do pai, ou $ para raiz mundial
[1] RelativePlacement   ← #id do IFCAXIS2PLACEMENT3D
```

**IFCTRIANGULATEDFACESET** (IFC4):
```
[0] Coordinates         ← #id do IFCCARTESIANPOINTLIST3D
[1] Normals             ← lista de normais (opcional, pode ser $)
[2] Closed              ← LOGICAL (opcional, pode ser $)
[3] CoordIndex          ← lista de (i0,i1,i2) — os índices reais dos triângulos
[4] PnIndex             ← (opcional) índice alternativo de pontos
```
Erro clássico: usar `parts[1]` como CoordIndex — são as normais (floats enormes). O CoordIndex real está em `parts[3]`; guard mínimo: `if len(fs_parts) < 4: return`.

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

## Armadilha: regex de indexação STEP capturando `) ;` nos args

**Este bug produz sintoma de 0 vértices, difícil de diagnosticar.**

O parser constrói um índice `entity_id → (type, args_string)` parseando linha a linha o arquivo STEP. O erro comum é usar `)` opcional na regex:

```python
# ERRADO — ) é opcional, então .* captura ") ;" dentro dos args
re.match(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)(?:\)\s*;?)?\s*$', line)
```

O `.*` guloso consome tudo incluindo o `) ;` final, então `args` vira `#27,#46) ;` em vez de `#27,#46`. O `split_top()` produz `['#27', '#46) ;']` e `int('#46) ;'.lstrip('#'))` lança `ValueError` — a entidade é silenciosamente ignorada.

**Correto — `)` obrigatório, backtracking remove o final:**
```python
# CORRETO — ) obrigatório faz .* retroceder até o último )
m = re.match(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*;?\s*$', line)
if not m:
    # Fallback: linha sem ) final (entidade parcial ou malformada)
    m = re.match(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)', line)
```

Com `)` obrigatório, para `#43=IFCLOCALPLACEMENT(#27,#46);`:
- `.*` inicialmente consome `#27,#46);`
- Backtrack para deixar `\)` casar o `)` final
- `args` = `#27,#46` — correto

**Diagnóstico**: se o parser indexa entidades mas retorna 0 vértices, imprimir `idx[lp_id]` para algum `IFCLOCALPLACEMENT` e verificar se os args têm `) ;` no final.

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

## Armadilha: regex de float STEP não trata mantissa sem dígitos após o ponto

**Este bug produz o sintoma "fragmentos de peça a vários metros de distância no
viewer 3D" — historicamente atribuído a `IFCLOCALPLACEMENT` aberrante no arquivo
de origem, mas em pelo menos um caso confirmado a causa real era esta.**

O formato STEP permite mantissa sem nenhum dígito depois do ponto quando há
expoente — valores praticamente zero são frequentemente escritos assim por
exportadores CAD:
```
-4.E-16
2.E+05
```

Uma regex de float que trata os dígitos após o ponto como sempre opcionais
falha nesse caso:

```python
# ERRADO — [0-9]+ no final é obrigatório, então o motor de regex não consegue
# casar o '.' seguido direto de 'E': ele para em '-4' (sem consumir o '.'),
# e o 'E-16' restante forma um número FANTASMA separado.
re.findall(r'[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?', '-4.E-16')
# → ['-4', '-16']   (deveria ser um único valor: -4e-16 ≈ 0)
```

Um valor que deveria ser ~0 vira **dois valores espúrios grandes** (`-4.0` e
`-16.0`). Quando isso cai na `Location` (translação) de um `IFCAXIS2PLACEMENT3D`
dentro da cadeia de `IFCLOCALPLACEMENT`, o componente inteiro é deslocado alguns
metros — exatamente o padrão "fragmento isolado longe do corpo principal" descrito
na seção de outliers. O mesmo bug corrompe silenciosamente vetores de direção
(rotação errada) e vértices de malha (`IFCCARTESIANPOINTLIST3D`) sempre que a
coordenada bruta tiver esse formato — não é exclusivo de translações, só é mais
visível ali.

**Correto — mantissa exige dígito antes OU depois do ponto, nunca os dois
opcionais ao mesmo tempo:**

```python
def parse_floats(s):
    return [float(x) for x in re.findall(
        r'[-+]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)(?:[eE][-+]?[0-9]+)?', s
    )]

parse_floats('-4.E-16')   # → [-4e-16]  (correto)
parse_floats('-0.07485,-4.E-16,1.2E-15')  # → 3 valores, não 4
```

**Diagnóstico**: antes de suspeitar de posicionamento aberrante no IFC de
origem, confirmar se o arquivo tem esse padrão:
```bash
grep -oE '[-+]?[0-9]+\.[eE][-+]?[0-9]+' arquivo.ifc | wc -l
```
Se houver ocorrências, rastrear a cadeia de `IFCLOCALPLACEMENT` do componente
afetado (`resolve_lp()` por proxy) e comparar a translação calculada com o valor
bruto do `IFCCARTESIANPOINT` de origem — se o valor bruto for `~0` (notação
`N.E±NN`) e o calculado for um número redondo grande (4.0, 5.0, 16.0…), é este
bug, não um erro de modelagem.

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
| `idx` | `int[]` | geometria indexada | Índices de triângulos flat, 0-based. Ausente apenas na saída expandida imediata do parse; presente após deduplicação. |

**Dois estágios possíveis:**

1. **Saída expandida (direto do parser com IFCINDEXEDCOLOURMAP)** — sem `idx`. Cada 3 vértices de `pos[]` formam um triângulo. Arquivos grandes (vértices repetidos por triângulo adjacente).

2. **Saída indexada (após deduplicação)** — tem `idx`. Vértices únicos em `pos[]`/`col[]`, triângulos em `idx[]`. **Este é o formato preferido para produção** — 80% menos vértices, arquivo 3–5× menor antes do gzip.

O viewer Three.js deve suportar ambos: `if (data.idx) geom.setIndex(data.idx)`.

---

## Otimização pós-parse — deduplicação de vértices

Após gerar o JSON expandido com cores, rode a deduplicação antes de commitar. Reduz 80% dos vértices e 3–5× o tamanho do arquivo. Para 14 modelos DANCOR: ~80MB expandido → ~25MB indexado → ~4.5MB gzip total.

```python
import json, struct

def dedup_json(src_path, dst_path):
    """Converte geometria expandida {pos,col} em indexada {pos,col,idx}."""
    with open(src_path) as f:
        data = json.load(f)

    pos = data['pos']
    col = data['col']
    n = len(pos) // 3

    seen = {}   # (x,y,z,r,g,b) → índice
    new_pos, new_col, new_idx = [], [], []

    def quantize(v):
        return struct.pack('f', v)  # 32-bit float — mesma precisão do BufferAttribute

    for i in range(n):
        key = (quantize(pos[i*3]), quantize(pos[i*3+1]), quantize(pos[i*3+2]),
               quantize(col[i*3]), quantize(col[i*3+1]), quantize(col[i*3+2]))
        if key not in seen:
            seen[key] = len(new_pos) // 3
            new_pos += pos[i*3:i*3+3]
            new_col += col[i*3:i*3+3]
        new_idx.append(seen[key])

    result = {'pos': new_pos, 'col': new_col, 'idx': new_idx}
    with open(dst_path, 'w') as f:
        json.dump(result, f, separators=(',', ':'))

    orig  = len(pos) // 3
    dedup = len(new_pos) // 3
    print(f'{src_path}: {orig} → {dedup} vértices ({100*(1-dedup/orig):.0f}% redução)')
```

**Quando rodar:** sempre após o parse com cores, antes de copiar os JSONs para `apps/lps/data/`. O formato indexado (`{pos, col, idx}`) é o padrão para produção.

---

## Integração com Three.js

O código abaixo suporta ambos os formatos (expandido e indexado) e ativa `vertexColors` automaticamente quando `col` está presente:

```javascript
const data = await fetch('/caminho/para/modelo.json').then(r => r.json());

const geom = new THREE.BufferGeometry();
geom.setAttribute('position', new THREE.Float32BufferAttribute(data.pos, 3));

const hasColors = data.col && data.col.length > 0;
if (hasColors) geom.setAttribute('color', new THREE.Float32BufferAttribute(data.col, 3));
if (data.idx)  geom.setIndex(data.idx);   // ausente = geometria expandida (sem índices)
geom.computeVertexNormals();

// Centralizar na origem
geom.computeBoundingBox();
const center = geom.boundingBox.getCenter(new THREE.Vector3());
const size   = geom.boundingBox.getSize(new THREE.Vector3()).length();

const mat = new THREE.MeshStandardMaterial({
  vertexColors: hasColors,          // ativa cores IFC quando presentes
  color: hasColors ? 0xffffff : 0x8896AA,  // base branca com vertexColors, cinza sem
  metalness: 0.25,
  roughness: 0.55,
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

## Diagnóstico de problemas

| Sintoma | Causa provável | Solução |
|---|---|---|
| 0 vértices, entidades indexadas mas ignoradas | Regex `build_entity_index` com `)` opcional — `.*` captura `) ;` nos args | Usar `\((.*)\)\s*;?` com `)` obrigatório (ver seção "Armadilha: regex") |
| Índices de face absurdos (bilhões) | `parts[1]` usado como CoordIndex — é Normals; CoordIndex está em `parts[3]` | Corrigir para `fs_parts[3]`; guard `if len(fs_parts) < 4: return` |
| Peças separadas por metros | LP ignorado | Verificar `resolve_lp()` — deve acumular hierarquia recursivamente |
| Fragmentos pequenos longe do corpo (ex: cluster a 5m ou 16m, translação "redonda" tipo 4.0/16.0) | **Checar primeiro** `parse_floats()` — mantissa STEP tipo `-4.E-16` sem dígito após o ponto vira dois valores fantasmas (ver seção "Armadilha: regex de float STEP" acima). Só depois de descartar isso, suspeitar de LP aberrante real no arquivo (bug do modelador) | `grep -oE '[-+]?[0-9]+\.[eE][-+]?[0-9]+' arquivo.ifc` — se houver match, é o bug de regex, não o IFC. Se `parse_floats()` já estiver corrigido e o problema persistir, aí sim filtrar vértices outlier no JSON final (ver seção abaixo) |
| Modelo ~1000× maior que o esperado | Conversão mm→m desnecessária | Verificar magnitude das coordenadas brutas antes de converter |
| `ObjectPlacement` em índice errado | `split(',')` simples | Substituir por `split_top()` |
| Saída vazia / 0 triângulos | `IFCELEMENTASSEMBLY` sendo processado em vez dos filhos | Pular entidades do tipo assembly no loop principal |
| Espelhamento de partes | Sinal errado na conversão de eixos | `THREE_z = -IFC_y`, não `+IFC_y` |
| JSON corrompido em nome com vírgula | `FILE_MAP` com chave errada | Usar o nome exato do arquivo; aspas e vírgulas fazem parte do nome |
| Modelo cinza quando arquivo tem cores | `IFCINDEXEDCOLOURMAP` não extraído | Chamar `build_face_color_map()` antes do loop principal; passar mapa para `emit_triangles_with_color()` |
| 0 cores extraídas do `IFCCOLOURRGBLIST` | Regex busca `\(\d+,\d+,\d+\)` mas floats têm casas decimais | Usar `re.finditer(r'\(([0-9.,\s]+)\)', inner)` |
| `col[]` presente mas Three.js ignora | Material sem `vertexColors: true` | Definir `new THREE.MeshStandardMaterial({ vertexColors: true })` |
| Cores corretas mas model sem faceting | Geometria indexada com `vertexColors` | Cores por face exigem geometria expandida (sem `idx[]`) ou chamar `geom.toNonIndexed()` |

---

## Pós-processamento — filtrar vértices outlier no JSON

Alguns exportadores (AltoQi, CATIA) produzem IFCs com `IFCLOCALPLACEMENT` aberrante em um ou mais sub-componentes — translação de 5m, 16m ou mais — enquanto o restante do modelo fica em ±0.5m. O parser aplica a transform corretamente; o problema está nos dados fonte.

**Como identificar**: após gerar o JSON, calcular o range de cada eixo. Se algum eixo tiver span > 2× o que seria esperado para o equipamento (ex: bomba industrial compacta com span > 2m), há outlier.

**Como confirmar a causa**: iterar sobre todos os produtos no IFC e calcular a translação acumulada via `resolve_lp()`. O proxy com translação aberrante é o culpado.

**Solução — filtro por threshold no JSON gerado:**

```python
import json

def filter_outliers(json_path, threshold=3.0):
    """Remove vértices e triângulos além de `threshold` metros da origem."""
    with open(json_path) as f:
        data = json.load(f)

    pos = data['pos']
    col = data.get('col', [])
    idx = data.get('idx')

    if idx is not None:
        # Formato indexado: filtrar vértices, depois triângulos
        n = len(pos) // 3
        keep = [i for i in range(n)
                if abs(pos[i*3]) <= threshold
                and abs(pos[i*3+1]) <= threshold
                and abs(pos[i*3+2]) <= threshold]
        keep_set = set(keep)
        remap = {old: new for new, old in enumerate(keep)}
        new_pos, new_col = [], []
        for i in keep:
            new_pos += pos[i*3:i*3+3]
            if col: new_col += col[i*3:i*3+3]
        new_idx = []
        for t in range(len(idx) // 3):
            a, b, c = idx[t*3], idx[t*3+1], idx[t*3+2]
            if a in keep_set and b in keep_set and c in keep_set:
                new_idx += [remap[a], remap[b], remap[c]]
        result = {'pos': new_pos, 'idx': new_idx}
        if new_col: result['col'] = new_col
    else:
        # Formato expandido (sem idx): filtrar por triângulo
        n_tris = len(pos) // 9
        new_pos, new_col = [], []
        for t in range(n_tris):
            tp = pos[t*9:(t+1)*9]
            if all(abs(tp[i*3+j]) <= threshold for i in range(3) for j in range(3)):
                new_pos += tp
                if col: new_col += col[t*9:(t+1)*9]
        result = {'pos': new_pos}
        if new_col: result['col'] = new_col

    with open(json_path, 'w') as f:
        json.dump(result, f, separators=(',', ':'))
```

**Threshold recomendado por tipo de equipamento:**

| Equipamento | Threshold seguro |
|---|---|
| Bomba de incêndio compacta (série W, TJM) | 3m |
| Válvula / fitting | 2m |
| Equipamento de grande porte (chiller, caldeira) | 10m |

---

## Segurança — filtro de tipo no fallback ifcopenshell

`ifc_file.by_type('IFCPRODUCT')` devolve **todo** elemento com `Representation`, incluindo não-físicos. Filtro obrigatório:

```python
if (not product.is_a('IfcElement')
        or product.is_a('IfcFeatureElement')   # vazios de furo/recorte — excluir mesmo sendo IfcElement
        or product.is_a('IfcVirtualElement')):  # limite de espaço/porta aberta — subtype de IfcElement, NÃO de IfcFeatureElement
    continue
```

`IfcVirtualElement` tem `Representation` sólida válida (superfície planar) e vira geometria fantasma visível no viewer se não for filtrado. Não está coberto por `IfcFeatureElement` — exige exclusão explícita.

O bloco de extração de geometria e cores deve estar em `try/except` separado do `create_shape()`:

```python
try:
    shape = ifcopenshell.geom.create_shape(settings, product)
except Exception:
    continue
try:
    geom = shape.geometry
    # ... mat_colors, loop de triângulos ...
except Exception:
    continue  # falha em cor/material não deve abortar o parse inteiro
```

Sempre verificar o bounding box do JSON resultante antes de publicar — deve corresponder às dimensões físicas do equipamento.
