# 2026-08-23 — Diagnóstico e correção de bugs do parse_ifc.py

**Data:** 2026-08-23 · Registro **extraído do `CLAUDE.md`** em 2026-09-04 (S7.8, I22) — esta
sessão não tinha arquivo próprio; o texto abaixo é o que havia lá, sem alteração.

---

**Contexto:** primeira vez que o pipeline foi rodado do zero após limpeza total do `output/`.
Os arquivos de geo que existiam localmente (gitignored) nunca tinham sido regenerados desde
a criação do projeto — esta sessão revelou que o código commitado nunca havia sido validado
contra os IFCs reais.

**Bug 1 — Índices errados no parser STEP (Dancor / CATIA / 3DEXPERIENCE)**

`parse_ifc.py` lia `parts[4]` como `ObjectPlacement` e `parts[5]` como `Representation`.
No IFC4 exportado pelo 3DEXPERIENCE, o índice 4 (0-based) é `ObjectType`
(`'AECARCHITECTURALELEMENT'`), deslocando tudo em +1:

```
[4] ObjectType       = 'AECARCHITECTURALELEMENT'  ← o que estava sendo lido como LP
[5] ObjectPlacement  = #id do IFCLOCALPLACEMENT   ← correto
[6] Representation   = #id do IFCPRODUCTDEFINITIONSHAPE
```

O parser tentava `int('AECARCHITECTURALELEMENT')` → `ValueError` → pulava todos os
`IFCBUILDINGELEMENTPROXY` → 0 vértices para todos os 14 IFCs da Dancor.

**Correção aplicada:** `parts[4]→parts[5]` (ObjectPlacement) e `parts[5]→parts[6]`
(Representation). Guard `len(parts) < 7` atualizado de `< 6`.

**Bug 2 — IFCs da Amanco usam IFCADVANCEDBREP, não IFCTRIANGULATEDFACESET**

O `parse_ifc.py` só tratava geometria tessellada (`IFCTRIANGULATEDFACESET`).
Os IFCs da Amanco (exportados pelo AltoQi Hidráulico/Elétrico) usam B-rep paramétrico
(`IFCADVANCEDBREP`) — incompatível com o parser STEP puro.
Os geo files da Amanco em commits anteriores foram gerados em sessão com código diferente.

**Correção aplicada:** adicionado `_parse_ifc_brep()` que usa `ifcopenshell.geom`
para tessellizar B-rep automaticamente, com fallback de cor por material.
`parse_ifc_file()` detecta o tipo de geometria e roteia para o método correto.
`ifcopenshell>=0.8.0` adicionado ao `requirements.txt`.

**Bug 3 — `build_entity_index` capturava `) ;` como parte dos args**

A regex primária de `build_entity_index` usava `(.*)(?:\)\s*;?)?` onde o grupo opcional
nunca fazia backtrack — o `(.*)` greedy consumia o `) ;` final da linha.
Resultado: args de `IFCLOCALPLACEMENT(#27,#46) ;` eram indexados como `'#27,#46) ;'`.

Ao chamar `resolve_lp` → `split_top('#27,#46) ;')` → `['#27', '#46) ;']` →
`int('#46) ;'.lstrip('#'))` → `int('46) ;')` → `ValueError` → todas as entidades puladas.

**Correção aplicada:** substituição da regex bugada pela regex de fallback (que já estava
correta, usando `(.*)\)\s*;?\s*$` com backtracking forçado até o último `)` da linha):
```python
# Antes (bugado):
m = re.match(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)(?:\)\s*;?)?\s*$', line)
if not m:
    m = re.match(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*;?\s*$', line, re.DOTALL)

# Depois (correto — uma única regex):
m = re.match(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*;?\s*$', line)
```

**Bug 4 — `_process_faceset` lia CoordIndex do campo errado**

`IFCTRIANGULATEDFACESET` tem 5 atributos: `Coordinates, Normals, Closed, CoordIndex, PnIndex`.
O código lia `fs_parts[1]` (Normals) como CoordIndex em vez de `fs_parts[3]`.
Nos arquivos Dancor/CATIA, `Normals` contém vetores float (`((0.3,0.9,...),...)`) —
`parse_ints` extraía dígitos desses floats como "índices", gerando `IndexError` ao
acessar `coord_list[vi-1]`.

**Correção aplicada:** `coord_index_str = fs_parts[1]` → `fs_parts[3]`.
Guard atualizado de `len(fs_parts) < 2` → `< 4`.

**Estado pós-correção e validação:**
- Dancor: todos os 14 IFCs parseados com 50k–150k vértices cada; redução ~79% pelo dedup
- Pipeline completo rodou com sucesso: parse → dedup → catalog.json → preview HTML → ZIP
- Amanco: código de B-rep implementado (ifcopenshell), mas estrutura de dirs aninhada ainda
  limita quais categorias são detectadas pelo `scan_input` (problema arquitetural separado)
