# OQ3D — a geometria dentro do `.aq` (`www/apps/ingestao/pipeline/oq3d.py`)

> Movido do `CLAUDE.md` em 2026-09-04 (S7.8, item I22 da auditoria). O conteúdo é o que estava lá,
> com as afirmações desatualizadas de I23 corrigidas no lugar; onde diz "este arquivo", "acima" ou
> "no histórico", leia-se o `CLAUDE.md` antigo — o histórico está em `docs/sessoes/`. **Manter aqui**
> a partir de agora: o `CLAUDE.md` só aponta para este arquivo.

Formato **OQ3D** (`OQ3D 3D Objects File`), no BLOB `SIMBOLOGIA_3D.SIMBOLOGIA_3D`.

### Cabeçalho — 37 bytes, e um deles é informação

Documentado em 2026-09-02, junto com o escritor. O `oq3d.py` só procura a assinatura e
pula direto para a árvore, mas o cabeçalho tem um campo útil:

```
offset  bytes                      significado
0       3a 01 01 00 00             5 bytes OPACOS, idênticos nas 12 bibliotecas
5       'OQ3D 3D Objects File'     20 bytes de assinatura
25      02 00 00 00                u32 = 2, versão do arquivo
29      N  00 00 00                u32 = NÚMERO DE OBJETOS-RAIZ
33      00 00 00 00                u32 = 0
```

Os 5 primeiros bytes são constantes nas 12 bibliotecas e nas 6 versões de schema
(552–607). Não se sabe o que significam; sabe-se que não variam.

> **O campo em +29 serve de verificação de parse, e revelou DOIS defeitos reais.**
> O parse encontra **sempre mais** raízes do que o cabeçalho declara, nunca menos.
> Medido em **todas** as 783 geometrias das 12 bibliotecas de fabricante: **54 divergiam
> (6,9%), em 6 bibliotecas** — as cinco da Intelbras que têm geometria e a Maxbar, esta com
> 31 de 135.
>
> **Corrigido em 2026-09-03 (S7.6): as 31 da Maxbar eram outro bug.** Elas gravam
> `TQi3DIndexedTriangleMeshData` **versão 3** (e o arquivo também é versão 3 em +25); o
> parser só aceitava a 2, não consumia o bloco, e o scanner tolerante via `0x5B`/`0x5D`
> dentro dos doubles — daí as raízes a mais. **A geometria dessas 31 simbologias (56 peças)
> era perdida por inteiro** e o build as contava como "peças sem 3D (tubos/kits)". O layout
> da versão 3 é byte a byte igual ao da 2 (mesma cauda de 19 bytes entre malhas); aceitar
> `ver in (2, 3)` (`oq3d.MESH_VERSOES`, e `MESH_VERSOES` no `oq3d-parser.ts`) devolve
> bbox plausível (70 × 70 × 9 cm), índices válidos e contagem de raízes exata. Restam **23
> divergências, todas na Intelbras** (CFTV 4, Cont. Acesso 4, PPCI 4, SDAI 6, Sensor 5),
> essas sim com geometria completa e a causa abaixo. Teste:
> `tests/test_oq3d.py::test_maxbar_malhas_versao_3_agora_tem_geometria`.
> 
> A diferença vai de **+2 a +10 e não é sempre par** (+7 e +9 aparecem), o que descarta
> "um `0x5D` desempilha um nível e promove dois filhos" como regra única: o
> desempilhamento espúrio acontece em quantidade variável dentro do mesmo blob.
>
> Nesses 23 casos a geometria emitida não muda — o `_collect` desce a árvore toda —, mas a
> hierarquia muda, e com ela a composição dos transforms dos nós promovidos. Na Intelbras
> (equipamentos) as malhas já vêm em coordenadas de mundo, então não aparece; numa
> biblioteca de conexões deslocaria a peça.
>
> O `parse()` avisa com `OQ3DAvisoParse` quando isso acontece (2026-09-02) e, desde a S7.6,
> **o aviso chega ao operador**: `build_catalog_from_aq` coleta os avisos por simbologia e
> `resumo_diag` imprime `AVISO: N simbologia(s) com aviso de parse` com id e nome de cada
> uma. Antes o `warnings.warn` ia para o stderr, uma vez por linha de código, sem dizer de
> qual simbologia era (I3).

Árvore de objetos serializada no estilo Delphi:

```
0x5B <len:u32> <ClassName>   abre um objeto
...payload...
0x5D                         fecha
```

### Classes que carregam dados

```
TQi3DIndexedTriangleMeshData
    u32 versao(2 ou 3 — layout idêntico; a 3 aparece na Maxbar) | u32 nCoords | u32 reservado
    nCoords doubles                 → nCoords/3 vértices (x,y,z)
    u32 nIdx | u32 reservado
    nIdx u32                        → nIdx/3 triângulos
TCoatingColor
    u32 versao | u32 flag | u8 R | u8 G | u8 B | u8 A    (cor UNIFORME da malha)
TCoordinateTransformation3D
    u32 versao | 12 doubles         → rotação 3×3 COLUMN-major + translação
```

**A rotação é column-major:** o elemento `(i, j)` está em `r[j*3 + i]`. Lida como
row-major, sai transposta e desloca toda instância cuja rotação não seja
simétrica. `parse()` já devolve transposta para row-major.

Hierarquia: `TQi3DReusedObject(guid)` → `TQi3DReusableObject` (definição inline,
opcional) → `TQi3DTriangleMesh` → `TCoatingColor` + malha. O **último**
`TCoordinateTransformation3D` filho direto é o que posiciona; o par origem/alvo
espelha `MappingOrigin`/`MappingTarget` do IFC.

### Correspondência com o IFC

| OQ3D | IFC4 |
|---|---|
| `TQi3DObjectGroup` | `IFCELEMENTASSEMBLY` |
| `TQi3DReusableObject` | `IFCREPRESENTATIONMAP` |
| `TQi3DReusedObject` | `IFCMAPPEDITEM` |
| `TQi3DIndexedTriangleMeshData` | `IFCTRIANGULATEDFACESET` |
| `TCoordinateTransformation3D` | `IFCLOCALPLACEMENT` |
| `TCoatingColor` | `IFCINDEXEDCOLOURMAP` |

A contagem de entidades bate exatamente (18 `TQi3DReusedObject` ↔ 18
`IFCMAPPEDITEM`): o exportador IFC é tradução direta desta estrutura.

### Unidades

**Centímetros, Z-up** — a mesma orientação do IFC nativo.
Para Three.js: `x, y=z, z=-y`, multiplicado por 0.01.
Para **escrever** OQ3D a partir de geometria de viewer, o inverso:
`oq3d_x = three_x·100`, `oq3d_y = −three_z·100`, `oq3d_z = three_y·100`.

### Escrever OQ3D

Feito em 2026-09-02: `eng-reversa/tools/oq3d_writer.py`. Anatomia byte a byte em
`eng-reversa/estudo/02-escrever-oq3d.md`. O que muda em relação a ler:

O `oq3d.py` é um leitor **tolerante** — varre à procura de `0x5B`/`0x5D` e consome por
inteiro só os três blocos de tamanho conhecido (malha, cor, transform), pulando todo o
resto. Um escritor não tem essa liberdade, e o resto é justamente o que ele precisa
saber. A moldura foi copiada byte a byte da `SIMBOLOGIA_3D` 169 da Amanco, com buracos
só nos dados que se controla.

Três coisas que só aparecem escrevendo:

- **A cor é gravada duas vezes** — no payload de `TQi3DTriangleMesh` e em
  `TCoatingColor`, com os mesmos 4 bytes. O leitor usa só a segunda; o escritor tem de
  pôr as duas.
- **A rotação tem de ser transposta de volta para colunas.** O `parse()` devolve
  row-major; gravar assim produz a transposta, e a instância sai do lugar **sem mudar
  nenhuma contagem** — o bug da S5.1, do lado da escrita. O teste que pega isso grava a
  rotação e a sua transposta e confere que dão resultados diferentes; sem essa
  contraprova, uma rotação simétrica passaria e não provaria nada.
- **Nada é alinhado.** O `double` do payload de `TQi3DReusedObject` começa num offset
  que não é múltiplo de 8.

O escritor emite uma malha por objeto-raiz, sempre com a definição inline
(discriminador `0x02`). Não gera instância por referência (`0x01`), `TQi3DObjectGroup`
nem `WIREFRAME`. Custo de não reaproveitar malha: reescrever a `SIMBOLOGIA_3D` 169 da
Amanco dá 52.249 bytes contra 51.927 do original — **1,01×**.

> **Malha inventada precisa de checagem topológica, e de olhar.** `eng-reversa` gerou
> forma paramétrica para 262 peças, e dois defeitos passaram por bounding box, contagem
> de triângulos e round-trip binário: (a) perfis de revolução que fecham em si mesmos
> ficavam com `2 × lados` arestas de borda — sólido que parece fechado e mostra o
> interior pela costura; (b) malhas corretas em posições relativas erradas — colar de
> joelho solto do corpo, sifão desmontado. A primeira classe se pega contando arestas
> compartilhadas por exatamente dois triângulos; **a segunda só se pega abrindo e
> olhando** (`eng-reversa/tools/olhar_preview.mjs`).

### Armadilhas

| Armadilha | Consequência |
|---|---|
| Ignorar os transforms | Funciona em equipamentos (malhas já em coordenadas de mundo) e **quebra** em conexões, montadas de malhas reaproveitadas — joelhos saem retos. Use sempre o parser de árvore. |
| Buscar `0x5B` junto do byte anterior | O byte que precede varia (`\x02\x5b`, `\x01\x09\x00\x00\x00\x5b`…). Ancore só no `0x5B`. |
| Varrer delimitadores byte a byte | `0x5B`/`0x5D` ocorrem dentro de doubles. Consuma por inteiro os blocos de tamanho conhecido antes de varrer. |
| Somar bocais na bounding box | Verde `(1,154,63)` e azul `(10,84,152)` são marcadores de conexão, não produto — inflam a bbox em ~2 cm. Use `skip_markers=True`. |
| `SELECT *` em `SIMBOLOGIA_3D` | Traz o `WIREFRAME`: 69–71% do arquivo (285 MB dos 412 MB da Amanco), inútil para viewer web. |
| Esquecer o `dedup()` | O caminho `.aq` **precisa** dedupar como o IFC faz. Sem isso o preview foi de 148 MB para 571 MB. |
| Ler a rotação como row-major | Ela é **column-major**. Sai transposta: instância rotacionada fora do lugar, sem mudar a contagem de triângulos. |
| Ignorar instâncias que referenciam a definição | 1.096 das 2.960 instâncias não trazem malha inline — some ~31% dos triângulos na Amanco. |

### API

```python
import oq3d
oq3d.is_oq3d(blob)                     # valida assinatura
oq3d.parse(blob)                       # árvore de nós
oq3d.extract(blob, skip_markers=True)  # [(verts_cm, tris, rgba)] com transforms
oq3d.to_buffers(blob)                  # {'pos','col','idx'} em metros, Y-up
oq3d.bbox(blob) / oq3d.stats(blob)     # validação e logs
oq3d.MESH_VERSOES                      # (2, 3) — versões de malha com layout conhecido
```

**Contrato de erro (igual ao `oq3d-parser.ts`, conferido em `tests/test_paridade_ts.py`):**
blob sem assinatura ou **truncado** (contagem declarada excede o buffer) → `OQ3DError`,
antes de alocar; bloco de malha com **layout desconhecido** (versão fora de
`MESH_VERSOES`, zero coordenadas, contagem não múltipla de 3) → bloco **pulado** +
`OQ3DAvisoParse`, porque a geometria fica incompleta; contagem de raízes diferente do
cabeçalho → `OQ3DAvisoParse`. Até a S7.6 o `_read_mesh` devolvia o offset em silêncio nos
dois primeiros casos, e o port TS já lançava — os dois lados divergiam.

### Instâncias repetidas — RESOLVIDO em 2026-08-30

A maioria dos `TQi3DReusedObject` **não** traz a definição inline: referencia uma
`TQi3DReusableObject` já serializada. Layout do payload:

```
+0   u32 versão (2 ou 3)
+28  u32 tamanho do GUID (sempre 36)
+32  GUID, 36 bytes ASCII    ← ÚNICO POR INSTÂNCIA, nunca foi a chave
...  bloco de 15 bytes (versão 2) ou 16 bytes (versão 3)
+B   u8 discriminador:  0x02 = definição inline  |  0x01 = seguem 4 bytes de referência
```

**A referência é o índice de serialização, base 1, contado sobre TODOS os objetos
da árvore em ordem de documento.** As duas hipóteses antigas foram testadas e
refutadas: o `u32` em `+8` é um id de instância (valores 2..19 na CAM-W21 2CV,
todos distintos — não índice de definição), e "a última definição vista" não
explica o padrão. Só as sete classes de `CLASSES` aparecem no fluxo, então o
contador não dessincroniza — verificado varrendo as 10 bibliotecas.

Validado: 2.960 `TQi3DReusedObject`, dos quais **1.096 por referência — todos**
resolvem para uma `TQi3DReusableObject`.

> Junto com este bug havia um segundo, que só apareceu ao conferir contra o IFC:
> a rotação de `TCoordinateTransformation3D` é **column-major**. Ele não muda a
> contagem de triângulos, só a posição — por isso passou despercebido. Era ele o
> responsável pela peça "solta no ar", não o das instâncias repetidas.

### Como conferir o parser contra o IFC

```bash
python3 docs/estudo-oq3d/valida_ifc.py Dancor        # exato: 13/13 pontos idênticos
python3 docs/estudo-oq3d/valida_ifc.py Amanco --limite 80
```

Em biblioteca tessellated (`IFCTRIANGULATEDFACESET`, ex. Dancor) a conferência é
exata: reconstrói-se o IFC do STEP (placement do produto × mapped item) e
compara-se o **conjunto de pontos**. Em B-rep (`IFCADVANCEDBREP`, ex. Amanco) a
tesselação é independente e só a forma é comparável.

Três armadilhas ao comparar, todas já resolvidas dentro do script:

| Armadilha | Por quê |
|---|---|
| Comparar só a bounding box | Uma rotação e a sua transposta podem gerar a **mesma** caixa. Compare os pontos. |
| Alinhar pelo centróide | O OQ3D guarda várias malhas como sopa de triângulos, o IFC solda os vértices — os centróides têm pesos diferentes. Alinhe pelo canto da bbox. |
| Igualdade de conjunto arredondado | Coordenadas na fronteira de arredondamento caem para lados diferentes. Compare por tolerância (~10 µm). |

O `MappingTarget` do IFC costuma ser **identidade**: quem posiciona cada
instância é o `ObjectPlacement` do `IfcProduct` — cada instância é um produto.
