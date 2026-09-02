# Escrever OQ3D — o formato binário da geometria, do lado de quem grava

O `scripts/oq3d.py` do projeto lê OQ3D e está validado em 12 bibliotecas. Mas
ele é um leitor **tolerante**: varre à procura de `0x5B`/`0x5D`, consome por
inteiro só os três blocos de tamanho conhecido (malha, cor, transform) e pula
todo o resto. Um escritor não tem essa liberdade — o AltoQi Builder conhece o
formato inteiro.

Este documento fecha as lacunas: o cabeçalho, os payloads dos objetos
contêineres e os bytes de fechamento, todos medidos byte a byte na
`SIMBOLOGIA_3D` 169 da Amanco (`DN150 - QUADRADA`, 51.927 bytes, a menor malha
das 12 bibliotecas).

A ferramenta que produziu isto é o `tools/oq3d_anatomy.py`, que imprime cada
marcador com o seu offset e, para cada objeto, o GAP — os bytes entre o fim do
payload conhecido e o próximo marcador. **O que o leitor pula é exatamente o
que o escritor precisa saber.**

---

## 1. O cabeçalho: 37 bytes, dos quais um é informação

```
offset  bytes                              significado
------  ---------------------------------  ---------------------------------
0       3a 01 01 00 00                     5 bytes OPACOS
5       'OQ3D 3D Objects File'             20 bytes de assinatura
25      02 00 00 00                        u32 = 2, versão do arquivo
29      N  00 00 00                        u32 = NÚMERO DE OBJETOS-RAIZ
33      00 00 00 00                        u32 = 0
```

Os 5 primeiros bytes são **idênticos nas 12 bibliotecas e nas 6 versões de
schema** (552, 562, 572, 582, 595, 607). Não sabemos o que significam —
`3a 01` não é o tamanho da assinatura (que seria `14 00 00 00`) e não segue o
padrão `0x5B <u32 len> <nome>` dos marcadores de classe. Sabemos que não
variam, e por isso o escritor os copia literalmente.

O campo em +29 é o **número de objetos-raiz**. Confirmado contra o parser em 22
das 24 amostras medidas (as duas menores geometrias de cada uma das 12
bibliotecas):

| Biblioteca | campo em +29 | raízes que o parser conta |
|---|---|---|
| Amanco | 3 / 2 | 3 / 2 |
| Dancor | 22 | 22 |
| Komeco (dois arquivos) | 1 | 1 |
| Maxbar | 1 | 1 |
| Intelbras CFTV | 6 / 1 | 6 / 1 |
| Intelbras Sensor Alarme | 4 | 4 |
| **Intelbras Cont_Acesso** | **110 / 157** | **112 / 159** |
| **Intelbras PPCI e SDAI** | **185** | **187** |

Nas duas que divergem, o parser conta **exatamente dois nós a mais**. A
divergência é do leitor, não do campo: o parser tolerante desempilha num
`0x5D` que caiu dentro de um `double`, e dois nós filhos são promovidos a raiz.
Vale como achado sobre o parser — ver
`05-achados-para-a-documentacao-do-projeto.md`.

---

## 2. A árvore de um objeto-raiz, byte a byte

Depois do cabeçalho vem um objeto-raiz por vez, cada um precedido de um byte
`0x02` ("segue item"). A forma canônica — a que o escritor emite, e que é
exatamente o primeiro objeto-raiz da `SIMBOLOGIA_3D` 169 da Amanco:

```
TQi3DReusedObject                  a instância
  TQi3DReusableObject                a definição, embutida
    TQi3DTriangleMesh
      TCoatingColor                    cor uniforme
      TQi3DIndexedTriangleMeshData     vértices e triângulos
    TCoordinateTransformation3D        origem  (identidade)
  TCoordinateTransformation3D        alvo — posiciona a instância
```

Os offsets abaixo são relativos ao começo do objeto-raiz. Para a
`SIMBOLOGIA_3D` 169, com 276 vértices e 184 triângulos, o raiz tem 9.417 bytes
e **nenhum byte fica sem explicação**.

```
rel      conteúdo                                             tamanho
-------  ---------------------------------------------------  -------
0x0000   02                                                        1   segue item
0x0001   5B 11 00 00 00 'TQi3DReusedObject'                       22   marcador
0x0017   02 00 00 00                                                4   u32 versão = 2
0x001b   02 00 00 00                                                4   u32 = 2
0x001f   01 00 00 00                                                4   u32 índice da instância
0x0023   00 00 00 ff                                                4   RGBA de fallback
0x0027   01 00 00 00                                                4   u32 = 1
0x002b   00 00 00 00 00 00 f0 3f                                    8   double 1.0
0x0033   24 00 00 00                                                4   u32 = 36, tamanho do GUID
0x0037   'D89325B8-4C21-435E-B846-0A68789E42E2'                    36   GUID ASCII
0x005b   00 00 00 00 00 01 00 00 00 00 00 00 00 00 00             15   bloco da versão 2
0x006a   02                                                         1   DISCRIMINADOR: 02 = embutida
0x006b   5B 13 00 00 00 'TQi3DReusableObject'                      24   marcador
0x0083   02 00 00 00  02                                            5   u32 versão + segue item
0x0088   5B 11 00 00 00 'TQi3DTriangleMesh'                        22   marcador
0x009e   02 00 00 00  02 00 00 00  ff ff ff ff                     12
0x00aa   d8 cb b8 ff                                                4   RGBA (repete a cor!)
0x00ae   01 00 00 00                                                4   u32 = 1
0x00b2   00 00 00 00 00 00 f0 3f                                    8   double 1.0
0x00ba   00 00 00 00                                                4   u32 = 0
0x00be   00 00 00 00 00                                             5   5 zeros
0x00c3   01 00 00 00  01 00 00 00                                   8   dois u32 = 1
0x00cb   02                                                         1   segue item
0x00cc   5B 0D 00 00 00 'TCoatingColor'                            18   marcador
0x00de   02 00 00 00  02 00 00 00                                   8   u32 versão + u32 flag
0x00e6   d8 cb b8 ff                                                4   RGBA
0x00ea   5d 00 02                                                   3   fecha a cor, segue item
0x00ed   5B 1C 00 00 00 'TQi3DIndexedTriangleMeshData'             33   marcador
0x010e   02 00 00 00                                                4   u32 versão = 2
0x0112   3c 03 00 00                                                4   u32 nCoords = 828
0x0116   00 00 00 00                                                4   u32 reservado
0x011a   828 doubles                                             6624   vértices, cm, Z-up
0x1afa   28 02 00 00                                                4   u32 nIdx = 552
0x1afe   00 00 00 00                                                4   u32 reservado
0x1b02   552 u32                                                 2208   triângulos
0x23a2   00 × 16                                                   16   cauda da malha
0x23b2   5d 5d 00                                                   3   fecha malha, fecha mesh
0x23b5   5B 1B 00 00 00 'TCoordinateTransformation3D'              32   marcador
0x23d5   02 00 00 00                                                4   u32 versão = 2
0x23d9   12 doubles                                                96   rotação 3×3 + translação
0x2439   5d 5d                                                      2   fecha transform, fecha reusable
0x243b   5B 1B 00 00 00 'TCoordinateTransformation3D'              32   marcador
0x245b   02 00 00 00 + 12 doubles                                 100   o transform que POSICIONA
0x24bf   5d 01 00 00 00 01 00 00 00 5d                             10   fecha transform, dois u32, fecha raiz
```

### O que se aprende disso

**A cor aparece duas vezes.** Em `TQi3DTriangleMesh` (rel 0x00aa) e em
`TCoatingColor` (rel 0x00e6), com os mesmos 4 bytes. O leitor do projeto só usa
a segunda. Um escritor tem de gravar as duas.

**O discriminador em rel 0x006a decide a forma do objeto.** `0x02` significa
"a definição vem embutida, como filho `TQi3DReusableObject`"; `0x01` significa
"seguem 4 bytes com o índice de serialização da definição a herdar". O
escritor emite sempre `0x02`.

**Os bytes antes de um `0x5B` variam.** `00 00 00 02` antes da maioria,
`ff 5d 00 02` antes da malha indexada, `00 5d 5d 00` antes de um transform.
Confirma a armadilha já registrada na skill: **ancore a busca só no `0x5B`**, o
byte anterior não entra no padrão.

**Nada nesta árvore é alinhado.** O `double` em rel 0x002b começa num offset
que não é múltiplo de 8. Ler com `struct.unpack_from` resolve; assumir
alinhamento não.

---

## 3. A rotação é column-major — e o teste tem de provar isso

`TCoordinateTransformation3D` guarda 12 doubles: os 9 primeiros são a rotação
**em ordem de colunas** (o elemento `(i, j)` mora em `r[j*3 + i]`) e os 3
últimos a translação. O `scripts/oq3d.py` transpõe na leitura; um escritor tem
de transpor de volta.

Errar isso é o bug da sessão S5.1, e o perigoso dele é que **não muda nenhuma
contagem**: a malha tem os mesmos vértices e os mesmos triângulos, só sai do
lugar. Uma peça "solta no ar", e nenhum contador acusa.

Por isso o `tools/oq3d_roundtrip.py` faz duas coisas no caso 2:

1. escreve uma rotação composta de 90° em Z com 90° em X, aplica a mesma
   rotação aos vértices em Python, e compara ponto a ponto o que o leitor
   devolve;
2. **grava a transposta e confere que o resultado é diferente.** Sem esse
   segundo passo, o teste passaria com uma rotação simétrica e não provaria
   nada.

---

## 4. O que o escritor não faz

`tools/oq3d_writer.py` emite **uma malha por objeto-raiz, sempre com a
definição embutida**. Não gera:

- **instâncias por referência** (discriminador `0x01`), que é como o AltoQi
  economiza espaço quando a mesma malha aparece muitas vezes. São 1.096 das
  2.960 instâncias nas 12 bibliotecas. Ler exige resolvê-las; escrever não
  exige gerá-las.
- **`TQi3DObjectGroup`**, que agrupa malhas dentro de uma definição.
- **`WIREFRAME`**, a coluna de arestas para planta e corte. São 69–71% do
  tamanho de um `.aq` real (285 MB dos 412 MB da Amanco) e o formato não foi
  decifrado. Uma biblioteca sem ela provavelmente degrada a representação 2D.

O custo de não reaproveitar malhas: reescrever a `SIMBOLOGIA_3D` 169 da Amanco
com o escritor dá 52.249 bytes contra 51.927 do original — **1,01×**. Sem
WIREFRAME e sem instâncias por referência, e ainda assim praticamente do mesmo
tamanho, porque aquela geometria já traz as 4 malhas embutidas.

---

## 5. Unidades

**Centímetros, Z-up** — a mesma orientação do IFC nativo. Geometria vinda de um
viewer (metros, Y-up) precisa da conversão inversa **antes** de ser gravada:

```python
oq3d_x =  three_x * 100
oq3d_y = -three_z * 100
oq3d_z =  three_y * 100
```

O `roundtrip` confere isso pela bounding box: um tubo de 6 m sai com
`dz = 600,00 cm`.

---

## 6. A validação

`tools/oq3d_roundtrip.py`, seis casos, todos passando:

| Caso | O que prova |
|---|---|
| 1. uma malha, sem transform | o caminho básico: assinatura, vértices, triângulos, cor |
| 2. rotação não simétrica | a convenção column-major, com a contraprova da transposta |
| 3. quatro malhas, cores diferentes | o campo de contagem de raízes e a cor por malha |
| 4. filtro de bocais | o `skip_markers=True` do leitor reconhece o verde e o azul que gravamos |
| 5. bbox e stats | unidades e orientação |
| 6. reescrita de geometria real | 4 malhas e 676 triângulos da `SIMBOLOGIA_3D` 169 da Amanco, lidos, reescritos e relidos idênticos |

O caso 6 é o mais forte: a geometria não foi inventada por nós, veio de uma
biblioteca de produção, e sobreviveu ao round-trip vértice a vértice com
tolerância de 10⁻⁹ cm.
