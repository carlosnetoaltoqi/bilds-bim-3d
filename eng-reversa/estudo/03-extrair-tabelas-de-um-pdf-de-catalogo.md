# Extrair tabelas de um PDF de catálogo do Illustrator

O `AKATO-CATALOGO-CONSTRUCAO-CIVIL.pdf` tem 24 páginas, 87 tabelas de produto e
269 linhas. Nenhuma delas sai íntegra por extração de texto comum. Este
documento registra por quê e o que funciona — o método vale para qualquer
catálogo comercial diagramado no Illustrator, que é o formato em que
fabricantes distribuem catálogo.

Resultado: **269 produtos, 0 códigos repetidos, 0 linhas incompletas, 0 avisos**,
conferidos linha a linha contra o PDF.

---

## 1. Por que `extract_text()` não serve

O PDF foi gerado no Adobe Illustrator (`/Creator: Adobe Illustrator 30.6`) e
depois passou pelo iLovePDF. Cada célula de tabela é um operador de texto
independente, posicionado em coordenada absoluta. **A ordem de desenho não é a
ordem de leitura.**

O `extract_text()` do pypdf agrupa fragmentos vizinhos por heurística de
proximidade. Nessas tabelas de quatro colunas estreitas, ele cola células de
colunas diferentes:

```
células reais:  '21055' (x=87)  '400' (x=278)  '50mm' (x=154)  '10' (x=221)
extract_text:   '21055 40050mm 10'
```

Perde-se qual número é a embalagem e qual é a caixa master, e a descrição fica
grudada no master. Na página 6 isso acontece em 5 das 26 linhas — o suficiente
para inutilizar a extração e não o suficiente para ser óbvio.

**A camada de operadores não tem esse problema.** Interceptando `Tj`/`TJ` com
`visitor_operand_before`, `21055` chega sozinho, com x = 87,4 e y = 367,3.

```python
def antes(operador, operandos, cm, tm):
    if operador not in (b'Tj', b'TJ', b"'", b'"'):
        return
    texto = decodifica(operandos)
    # posição de dispositivo: tm APLICADO A cm
    x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
    y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]

pagina.extract_text(visitor_operand_before=antes)
```

### Três detalhes que erram silenciosamente

**A posição é `tm × cm`, não `tm`.** O `tm` é a matriz de texto e o `cm` a
matriz gráfica corrente. Usar só o `tm` põe fora do lugar todo texto dentro de
um grupo transformado — na primeira versão apareciam células em `y = −63`.

**O encoding é cp1252.** Os operandos vêm como bytes: `REDU\xc7\xc3O` é
`REDUÇÃO`. Mesma armadilha do `.aq`, mesma cascata de decodificação. Latin-1
decodifica sem erro e erra a faixa 0x80–0x9F.

**Arrays `TJ` trazem kerning intra-palavra.** `[b'CUR', 18, b'T', 92, b'A']` é
`CURVA`. Concatenar as partes de texto e ignorar os números é o certo: neste
PDF os saltos de coluna nunca acontecem dentro de um `TJ`, cada coluna tem o
seu próprio operador.

---

## 2. O problema de verdade: o `y` está corrompido

Com as células separadas, o passo óbvio seria agrupar por linha de base. **Não
funciona.**

O Illustrator desenha cada tabela por **blocos de coluna**, não por linhas: o
bloco dos códigos, depois o dos masters, depois o cabeçalho, depois o das
descrições, depois o das embalagens. Cada bloco é um objeto de texto com o seu
próprio entrelinhamento — e em vários deles o entrelinhamento está corrompido.

Na página 6, a família ADAPTADOR PARA CAIXA D'ÁGUA:

| Célula | `y` observado | `y` que a linha visual pede |
|---|---|---|
| código `21004` | 381,8 | ~381 |
| descrição `40mm x 1.1/4"` | **277,6** | ~381 |
| master `150` | **277,6** | ~381 |
| embalagem `5` | **277,6** | ~381 |
| embalagem da linha seguinte | **−63,4** | ~368 |

A descrição do `21004` está 104 pt abaixo do seu código, dentro da faixa
vertical da tabela de baixo. Uma embalagem cai fora da página. Agrupar por `y`
monta linhas erradas — e erradas de um jeito plausível, que passa por
conferência superficial.

### O que se preserva: a ordem

**A ordem dentro de cada bloco espelha exatamente a ordem visual das linhas.**
É o único invariante confiável do arquivo. Então o casamento é por **ordinal
dentro da coluna**: o i-ésimo código com a i-ésima descrição, a i-ésima
embalagem e o i-ésimo master.

---

## 3. O algoritmo

```
para cada página:
  1. juntar células partidas             (mesma linha de base, x adiantado ≤ 8 pt)
  2. dividir em duas regiões             (metade esquerda / metade direita)
  3. dentro de cada região, fatiar em tabelas pelos cabeçalhos CÓDIGO
  4. atribuir cada célula a uma coluna   (fronteira entre âncoras de cabeçalho)
  5. confirmar pelo tipo do conteúdo     (código / quantidade / descrição)
  6. casar as colunas por ordinal
  7. casar o título por posto na ordem de desenho
```

### 1. Juntar células partidas

O Illustrator parte células em vários operadores, de duas formas:

- **Mesmo x, mesmo y.** O pypdf reporta a mesma matriz de texto para `Tj`
  consecutivos dentro de um objeto — não acumula o avanço dos glifos. O código
  `21052` chega como `'2105'` + `'2'`.
- **x adiantado alguns pontos.** Com reposicionamento explícito: a descrição
  `1"` do nípel 21283 chega como `'1'` em x = 161,7 e `'"'` em x = 166,2.

O limite de 8 pt é seguro: as colunas estão a 50 pt ou mais uma da outra.

O segundo caso é o mais traiçoeiro. Sem juntar, o `'1'` é classificado como
quantidade, é recusado pela coluna DESCRIÇÃO e a descrição do produto sai como
`'"'`.

### 2. Duas regiões

Os painéis de produto vêm em duas colunas e as tabelas se intercalam na ordem
de desenho: tabela esquerda, tabela direita, tabela esquerda… Tratar a página
como uma sequência única mistura as duas.

### 3. Fatiar em tabelas

Uma tabela vai do seu cabeçalho `CÓDIGO` até o `CÓDIGO` seguinte **da mesma
região**. Com duas exceções, ambas de blocos desenhados **antes** do próprio
cabeçalho:

- **Uma corrida de códigos.** Página 7, as seis peças do JOELHO 90° SOLDÁVEL
  saem nas ordens 50 a 55 e o `CÓDIGO` só na 56. O recuo cobre a corrida
  inteira, parando no cabeçalho anterior.
- **A tabela inteira.** Página 11, o TÊ DE REDUÇÃO ROSCÁVEL tem masters,
  descrições e embalagens nas ordens 42 a 50, e o `CÓDIGO` na 51. Por isso a
  primeira tabela de cada região também recolhe o que veio antes do seu
  cabeçalho. É seguro porque, em todas as outras páginas, o que antecede o
  primeiro cabeçalho é título, texto de marketing ou número de página — e nada
  disso sobrevive à classificação de conteúdo.

### 4. A coluna é decidida por fronteira entre âncoras

Não por uma banda de largura fixa em volta de cada cabeçalho. Os valores são
centralizados na coluna, então a distância ao cabeçalho varia muito:

| Valor | x | x do `DESCRIÇÃO` | distância |
|---|---|---|---|
| `DN 100 x 100 x 50` (p. 16) | 158,6 | 164,3 | **−5,7** |
| `1.1/4"` (p. 21) | 154,1 | 137,0 | +17,1 |
| `1"` (p. 21) | 161,2 | 137,0 | **+24,2** |

Uma banda de `[−9, +21]` perderia o `1"` e manteria o `1.1/4"` — a família
sairia com 6 códigos e 4 descrições, desalinhando tudo a partir dali. A
fronteira entre âncoras resolve: a coluna vai do seu cabeçalho até o próximo.

Com um corte à direita da última coluna: o número da página fica em x = 601,2
contra o `MASTER` em 546,9 e, sendo `05` um inteiro, entraria como um master a
mais.

### 5. O tipo do conteúdo confirma

```
código      ^\*?\d{4,5}$
quantidade  ^\d{1,3}(\.\d{3})*$          (o master vem com separador de milhar)
descrição   \d\s*(?:mm|cm|m|g)\b | ["”] | \bDN\b
título      CAIXA ALTA, ≤ 24 caracteres, corpo entre 7,5 e 11,5 pt
```

**A regex de descrição é sensível à caixa, e isso é essencial.** Com
`re.IGNORECASE`, `NORMAL 6M` e `SOLDÁVEL 6M` — o `6M` do tubo de 6 metros —
casam com a unidade `m`. E `NORMAL 6M` cai na faixa x da coluna DESCRIÇÃO:
entrava como uma descrição a mais na família de cima e desalinhava a tabela
inteira. As unidades do catálogo são minúsculas; é isso que separa uma
descrição de um pedaço de título.

**E `'º'` não conta como minúscula.** O indicador ordinal masculino responde
`True` a `str.islower()` mas é categoria Unicode `Lo`, não `Ll`. Testando com
`islower()`, `CURVA 90º` é descartado como texto corrido e as 17 famílias de
esgoto perdem a primeira linha do título. O teste certo é
`unicodedata.category(c) == 'Ll'`.

### 6. Casar as colunas por ordinal

Com uma verificação de sanidade que o catálogo oferece de graça: **a caixa
master nunca é menor que a embalagem.** Quando as duas chegam trocadas, isso
corrige e registra o aviso. Nas 269 linhas do catálogo da Akato o invariante
nunca foi violado, e nas duas famílias em que embalagem e master são iguais
(TORNEIRA BOIA e ANEL PARA VASO, ambas 12) a troca é inofensiva.

### 7. O título por posto na ordem de desenho

O título é um bloco de linhas em CAIXA ALTA ao lado da foto. O `y` dele também
está corrompido — e de um jeito que **inverte a ordem**. Na página 18:

| Título | `y` do topo | `y` do cabeçalho da sua tabela |
|---|---|---|
| SIFÃO EXTENSÍVEL SIMPLES BRANCO | 218,2 | 459,7 |
| SIFÃO EXTENSÍVEL DUPLO BRANCO | 312,7 | 222,6 |

Ordenar por `y` troca os dois: o 36232 (62 cm e 1,12 m) sairia como DUPLO e o
36234 (80 cm) como SIMPLES. A **ordem de desenho** dos blocos de título, ao
contrário, acompanha a ordem visual dos painéis nas 24 páginas — inclusive nas
páginas 17 e 18, em que o título vem desenhado **depois** da sua própria
tabela.

Dois cortes descartam o que não é título de família:

- **recuo** — mais de 90 pt à direita da coluna CÓDIGO da região. Remove as
  legendas de margem (`SOLDÁVEL AKATO`, `ROSCÁVEL AKATO`) e os títulos de
  seção.
- **corpo** — entre 7,5 e 11,5 pt. Acima é título de seção (`ÁGUA FRIA` em
  19,2; `NOTAS` em 48,6); abaixo são os rótulos do infográfico da luva de
  correr na página 11, em 6,4 e 6,5 pt, que passam pelo recuo e contariam como
  um título a mais na região.

E os blocos de título só se juntam quando são **vizinhos na ordem de desenho**.
Sem essa checagem, dois títulos distantes que compartilham o x —
`ADAPTADOR PARA CAIXA D´ÁGUA` nas ordens 66-69 e `CURVA 90° CURTA` nas 98-100,
ambos em x = 475,9 — viram um bloco só, e a página fica com um título a menos
que o número de tabelas.

---

## 4. O progresso da depuração

Vale registrar, porque cada correção veio de um aviso do próprio extrator:

| Versão | Avisos | O que foi corrigido |
|---|---|---|
| 1 | 62 | atribuição por `y`; blocos de título não adjacentes fundidos; `'º'` tratado como minúscula |
| 2 | 41 | recuo de código cobrindo só uma célula; banda de coluna fixa |
| 3 | 3 | número de página entrando como quantidade |
| 4 | 1 | `NORMAL 6M` casando como descrição |
| 5 | **0** | tabela desenhada antes do próprio cabeçalho (página 11) |

O extrator emite um aviso sempre que o número de valores de uma coluna não bate
com o número de códigos. Essa checagem foi o que tornou a depuração possível:
sem ela, as 62 linhas erradas da primeira versão sairiam plausíveis.

---

## 5. Um brinde: a tabela de conversão

A página 23 traz a tabela POLEGADAS × MILÍMETROS da Akato, com as duas escalas
separadas — PVC soldável e PVC esgoto. Ela é o que liga as descrições em
polegada (roscável, polietileno) às descrições em milímetro (soldável, esgoto).

| Polegada | PVC soldável | PVC esgoto |
|---|---|---|
| 1/2" | 20 mm | — |
| 3/4" | 25 mm | — |
| 1" | 32 mm | — |
| 1.1/4" | 40 mm | — |
| 1.1/2" | 50 mm | 40 mm |
| 2" | 60 mm | 50 mm |
| 2.1/2" | 75 mm | — |
| 3" | 85 mm | 75 mm |
| 4" | 110 mm | 100 mm |
| 5" | 140 mm | — |
| 6" | 160 mm | 150 mm |
| 8" | 200 mm | 200 mm |

A extração linear dessa tabela sai como `4” 100 mm110 mm`, sem dizer qual valor
é de qual coluna. As coordenadas resolvem: o valor sob `PVC SOLDÁVEL` fica em
x ≈ 218-221 e o sob `PVC ESGOTO` em x ≈ 320-336. O resultado bate com as séries
normalizadas brasileiras — soldável 20/25/32/40/50/60/75/85/110, esgoto DN
40/50/75/100/150/200 —, que é a conferência independente que o método permitia.
