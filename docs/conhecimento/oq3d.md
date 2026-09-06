# OQ3D — o formato binário da geometria dentro do `.aq`

Especificação do formato **OQ3D** (`OQ3D 3D Objects File`): o blob
`SIMBOLOGIA_3D.SIMBOLOGIA_3D` do `.aq` do AltoQi Builder. É a razão de o projeto não
precisar dos IFCs para gerar 3D — forma, cor e miniatura estão todas aqui, e é a mesma
geometria que o AltoQi exporta como IFC (triângulos idênticos onde o IFC é tessellated;
forma convergente onde é B-rep).

## Cabeçalho — 37 bytes, um deles é informação

```
offset  bytes                      significado
0       3a 01 01 00 00             5 bytes opacos, idênticos em toda biblioteca e schema conhecidos
5       'OQ3D 3D Objects File'     20 bytes de assinatura
25      02 00 00 00                u32 = 2, versão do arquivo
29      N  00 00 00                u32 = número de objetos-raiz
33      00 00 00 00                u32 = 0
```

Não se sabe o que os 5 bytes iniciais significam; sabe-se que não variam.

## Árvore serializada estilo Delphi

```
0x5B <len:u32> <ClassName>   abre um objeto
...payload...
0x5D                         fecha
```

O byte que precede um `0x5B` varia com o contexto (`\x02\x5b`, `\x01\x09\x00\x00\x00\x5b`…)
— não entra no padrão de busca, ancore só no `0x5B`. E `0x5B`/`0x5D` ocorrem naturalmente
dentro de doubles: os blocos de tamanho conhecido têm de ser consumidos por inteiro antes
de qualquer varredura (ver armadilha das raízes, abaixo). Nada na árvore é alinhado — um
`double` pode começar num offset que não é múltiplo de 8.

### Classes com dados

```
TQi3DIndexedTriangleMeshData
    u32 versao (2 ou 3 — layout idêntico) | u32 nCoords | u32 reservado
    nCoords doubles                 → nCoords/3 vértices (x, y, z)
    u32 nIdx | u32 reservado
    nIdx u32                        → nIdx/3 triângulos

TCoatingColor
    u32 versao | u32 flag | u8 R | u8 G | u8 B | u8 A     (cor UNIFORME da malha)

TCoordinateTransformation3D
    u32 versao | 12 doubles         → rotação 3×3 COLUMN-major + translação
```

**A versão da malha pode ser 2 ou 3, com o mesmo layout byte a byte** (mesma cauda de 19
bytes entre malhas). Um leitor que só aceita a versão 2 não consome o bloco da versão 3 —
e a geometria correspondente é perdida por inteiro, contada como "peça sem 3D". Aceite
`versao in (2, 3)`.

**A rotação é column-major:** o elemento `(i, j)` está em `r[j*3 + i]`. Lida como
row-major, sai transposta e desloca toda instância cuja rotação não seja simétrica — o
bug não muda a contagem de triângulos, só a posição, o que o torna fácil de passar
despercebido. Um parser deve devolver a matriz já transposta para row-major.

### Classes de estrutura (sem dados próprios)

```
TQi3DReusedObject(guid)            instância
  TQi3DReusableObject                definição — inline (opcional) ou por referência
    TQi3DTriangleMesh
      TCoatingColor
      TQi3DIndexedTriangleMeshData
  TCoordinateTransformation3D        origem — quase sempre identidade
  TCoordinateTransformation3D        alvo  — posiciona a instância

TQi3DObjectGroup                   agrupa malhas dentro de uma definição
```

O **último** `TCoordinateTransformation3D` filho direto é o que posiciona. O par
origem/alvo espelha `MappingOrigin`/`MappingTarget` do `IFCCARTESIANTRANSFORMATIONOPERATOR3D`.

## Instâncias por referência — resolvidas pelo índice de serialização

A maioria dos `TQi3DReusedObject` **não** traz a definição inline: referencia uma
`TQi3DReusableObject` já serializada antes. Layout do payload:

```
+0   u32 versão (2 ou 3)
+28  u32 tamanho do GUID (sempre 36)
+32  GUID, 36 bytes ASCII    ← único por instância, NUNCA foi a chave
...  bloco de 15 bytes (versão 2) ou 16 bytes (versão 3)
+B   u8 discriminador:  0x02 = definição inline  |  0x01 = seguem 4 bytes de referência
```

**A referência é o índice de serialização, base 1, contado sobre TODOS os objetos da
árvore em ordem de documento** — não é o GUID. Duas hipóteses foram testadas e
refutadas: um `u32` próximo ao início do payload como id de instância (valores distintos,
não índice de definição), e "a última definição vista" (não explica o padrão observado).
Só as sete classes da árvore aparecem no fluxo, então o contador não dessincroniza.

Validado em 10 bibliotecas: 2.960 `TQi3DReusedObject`, dos quais 1.096 por referência —
todos resolvem para uma `TQi3DReusableObject`. Ignorar essas instâncias some com ~30% dos
triângulos numa biblioteca de conexões.

## Unidades e eixos

**Centímetros, Z-up** — a mesma orientação do IFC nativo. Ver `geometria.md` para a
tabela completa de conversões.

## Correspondência com o IFC

| OQ3D | IFC4 |
|---|---|
| `TQi3DObjectGroup` | `IFCELEMENTASSEMBLY` |
| `TQi3DReusableObject` | `IFCREPRESENTATIONMAP` |
| `TQi3DReusedObject` | `IFCMAPPEDITEM` |
| `TQi3DIndexedTriangleMeshData` | `IFCTRIANGULATEDFACESET` |
| `TCoordinateTransformation3D` | `IFCLOCALPLACEMENT` |
| `TCoatingColor` | `IFCINDEXEDCOLOURMAP` |

A contagem de entidades bate exatamente (18 `TQi3DReusedObject` ↔ 18 `IFCMAPPEDITEM`
numa biblioteca conferida): o exportador IFC é tradução direta desta estrutura. A cor é
uniforme por malha no OQ3D; o exportador a converte em cor por face ao fundir as malhas
num único face set.

## Raízes declaradas podem divergir do parse

O campo em +29 serve de verificação de parse, e revelou dois defeitos reais. **O parse
encontra sempre MAIS raízes do que o cabeçalho declara, nunca menos.** Medido em todas as
783 geometrias de 12 bibliotecas de dois fabricantes: 54 divergiam (6,9%), em 6
bibliotecas.

31 dessas eram o bug de versão de malha acima (bloco de versão 3 não consumido — o
scanner tolerante via `0x5B`/`0x5D` dentro dos doubles não lidos, e contava raízes a
mais; a geometria correspondente era perdida por inteiro). Corrigido aceitando
`versao in (2, 3)`.

As 23 restantes têm outra causa: um `0x5D` dentro de um double engana o scanner e
desempilha um nível, promovendo nós filhos a raiz. A diferença vai de +2 a +10 e não é
sempre par (+7 e +9 aparecem), o que descarta "um `0x5D` promove exatamente dois filhos"
como regra única — o desempilhamento espúrio acontece em quantidade variável dentro do
mesmo blob. Nesses casos a geometria emitida não muda (a coleta desce a árvore toda), mas
a hierarquia muda, e com ela a composição dos transforms dos nós promovidos: numa
biblioteca de equipamentos (malhas já em coordenadas de mundo) isso não aparece; numa
biblioteca de conexões deslocaria a peça.

## Bocais e o wireframe

Cores fixas verde `(1, 154, 63)` e azuis `(10, 84, 152)` / `(0, 116, 232)` marcam pontos
de conexão (macho/fêmea) desenhados pelo AltoQi — não são produto. Ficam fora do bbox da
peça e inflam a bounding box medida se não forem filtrados.

`SELECT *` em `SIMBOLOGIA_3D` traz também a coluna `WIREFRAME` — cerca de 70% do tamanho
do arquivo, a malha de arestas para planta e corte, inútil para um viewer web e cujo
formato não foi decifrado.

## Leitura tolerante e contrato de erro

Um leitor pode ser **tolerante**: varrer à procura de `0x5B`/`0x5D` e consumir por
inteiro só os três blocos de tamanho conhecido (malha, cor, transform), pulando todo o
resto sem precisar entender `TQi3DObjectGroup` ou o wireframe. O contrato de erro:

- blob sem assinatura ou **truncado** (contagem declarada excede o buffer) →
  erro antes de alocar (`OQ3DError`);
- bloco de malha com **layout desconhecido** (versão fora do conjunto aceito, zero
  coordenadas, contagem não múltipla de 3) → bloco **pulado** + aviso agregado
  (`OQ3DAvisoParse`), porque a geometria fica incompleta;
- contagem de raízes diferente do cabeçalho → aviso agregado (`OQ3DAvisoParse`).

Um parser que devolve o offset em silêncio nesses casos entrega geometria incompleta sem
que ninguém saiba. O aviso deve ser coletado por simbologia (não só um `warnings.warn`
solto) e mostrado ao operador com id e nome de cada uma — foi assim que o bug de versão 3
apareceu.

## Escrita

Um escritor não tem a liberdade de um leitor tolerante: o resto da árvore, que o leitor
pula, é exatamente o que o escritor precisa saber. A moldura foi copiada byte a byte de
uma `SIMBOLOGIA_3D` real (a menor malha disponível), com buracos só nos dados que se
controla — nada é inventado.

O escritor emite **uma raiz por malha, sempre com a definição inline** (discriminador
`0x02`). Nunca gera instância por referência (`0x01`), nem `TQi3DObjectGroup`, nem
`WIREFRAME`. Custo de não reaproveitar malha: reescrever uma simbologia real dá ~1,01×
o tamanho do original — porque aquela geometria já trazia as malhas embutidas, sem
WIREFRAME e sem instâncias por referência para começar.

Três coisas que só aparecem escrevendo:

- **A cor é gravada DUAS vezes** — no payload de `TQi3DTriangleMesh` e em
  `TCoatingColor`, com os mesmos 4 bytes. O leitor usa só a segunda; o escritor tem de
  pôr as duas.
- **A rotação tem de ser transposta de volta para colunas.** O leitor devolve row-major;
  gravar assim produz a transposta, e a instância sai do lugar sem mudar nenhuma
  contagem de triângulos. O teste que prova isso escreve uma rotação **e a sua
  transposta**, e exige que os resultados difiram — sem essa contraprova, uma rotação
  simétrica passaria e não provaria nada.
- **Nada é alinhado.** O `double` do payload de `TQi3DReusedObject` começa num offset
  que não é múltiplo de 8; ler com acesso alinhado quebra.

> **Malha inventada precisa de checagem topológica, e de olhar.** Duas classes de erro
> passam por bounding box, contagem de triângulos e round-trip binário: (a) um perfil de
> revolução que fecha em si mesmo sem soldar o último anel no primeiro deixa `2 × lados`
> arestas de borda — sólido que parece fechado e mostra o interior pela costura; (b)
> malhas corretas em posição relativa errada (peça montada torta). A primeira se pega
> contando arestas compartilhadas por exatamente dois triângulos (ver `geometria.md`); a
> segunda só se pega abrindo o viewer e olhando.

## Validação contra o IFC

O IFC da mesma biblioteca é o gabarito. Em biblioteca **tessellated**
(`IFCTRIANGULATEDFACESET`) a conferência é exata: reconstrói-se o IFC a partir do STEP
(placement do produto × mapped item) e compara-se o **conjunto de pontos** — contagem de
triângulos idêntica confirma que as instâncias por referência resolveram; pontos
idênticos confirmam que os transforms estão na convenção certa. Em biblioteca **B-rep**
(`IFCADVANCEDBREP`) a tesselação é independente e só a forma é comparável.

Três armadilhas na comparação:

| Armadilha | Por quê |
|---|---|
| Comparar só a bounding box | Uma rotação e a sua transposta podem gerar a mesma caixa — bbox não distingue rotação de transposta. |
| Alinhar pelo centróide | O OQ3D guarda várias malhas como sopa de triângulos; o IFC solda os vértices — os centróides têm pesos diferentes. Alinhe pelo canto da bbox. |
| Igualdade de conjunto arredondado | Coordenadas na fronteira de arredondamento caem para lados diferentes nos dois lados. Compare por tolerância (~10 µm). |

## Ferramentas

`oq3d_anatomy` dissecta um blob byte a byte — assinatura, cada marcador de abertura com
seu offset, o payload consumido quando o tamanho é conhecido, e o **gap**: os bytes entre
o fim do payload conhecido e o próximo marcador, em hexadecimal. É o que falta
documentar para escrever um novo bloco.

`oq3d_roundtrip` valida o escritor: escreve, relê com o próprio parser e compara vértice
a vértice — incluindo o caso da rotação com sua transposta (para provar a convenção) e o
caso de reescrever uma geometria real de produção (a prova mais forte: a malha não foi
inventada, sobrevive ao round-trip com tolerância de 10⁻⁹ cm).

## Onde está no código

- `biblioteca/bim_pipeline/aq/oq3d.py` — leitor (`is_oq3d`, `parse`, `extract`,
  `to_buffers`, `bbox`, `stats`, `MESH_VERSOES`, `OQ3DError`, `OQ3DAvisoParse`).
- `biblioteca/bim_pipeline/aq/oq3d_writer.py` — escritor.
- `biblioteca/bim_pipeline/cli/ferramentas/oq3d_anatomy.py` — dissecação byte a byte.
- `biblioteca/bim_pipeline/geometria/eixos.py` — conversão de eixos e unidades (ver
  `geometria.md`).
- Proveniência da engenharia reversa (histórico, não normativo):
  `docs/historico/estudos/oq3d/README.md`,
  `docs/historico/estudos/escrita-aq-de-pdf/estudo/02-escrever-oq3d.md`.

## Ver também

- `docs/conhecimento/geometria.md` — o contrato `{pos, col, idx}`, as conversões de eixos
  e o dedup que todo consumidor de OQ3D precisa aplicar.
- `docs/conhecimento/ifc.md` — o caminho equivalente a partir de IFC puro.
- `docs/skills/leitor-biblioteca-aq/SKILL.md` — a skill operacional, com a receita de
  escrita de um `.aq` inteiro (schema, enums, cp1252) em torno deste formato.
- `CONCEPTS.md` — verbetes "OQ3D", "Simbologia 3D", "Bocal".
