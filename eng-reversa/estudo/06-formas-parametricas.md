# Formas paramétricas — o que é dado e o que é invenção

Este documento cobre a terceira variante do `.aq` gerado: a que tem geometria
para **todas** as 262 peças, produzida por parâmetro em `tools/formas.py`.

> **As formas não são as cotas da Akato.** O catálogo comercial não traz cota
> de forma nenhuma. O que está no arquivo é uma forma plausível, e a ressalva
> está gravada em três lugares dentro dele. Serve para visualizar, contar peça
> e detectar interferência grosseira; **não serve** para conferir encaixe ou
> colisão fina.

---

## 1. A separação entre dado e invenção

Três origens, e cada peça mistura as três:

| Origem | O que vem dela | Confiança |
|---|---|---|
| **Catálogo Akato** | diâmetro nominal, segundo diâmetro nas reduções, comprimento (tubo 6 m, sifão 62 cm, engate 30 cm), cor, tipo de junta | dado real |
| **Norma NBR 5648 / 5688** | espessura de parede por bitola | dado normativo |
| **`PROPORCOES` deste módulo** | bolsa, colar, braço, raio de curva, corpo de registro | **invenção** |

A tabela de invenção é pequena de propósito — sete regras para 23 formas:

```python
bolsa           = 0.60·DE + 4 mm      profundidade do encaixe
colar           = +3 mm               sobre-espessura da bolsa
braço           = bolsa + 0.35·DE     do centro do joelho à face
raio_longa      = 1.50·DE             eixo da curva longa
raio_curta      = 0.75·DE             eixo da curva curta
registro_diam   = 1.70·DE             corpo do registro de esfera
registro_comp   = 1.30·DE             comprimento do corpo
```

Espessura de parede fora das bitolas tabeladas cai em `max(1,5; 0,055·DE)` mm.

**Onde o catálogo não dá diâmetro nenhum** — os sifões, descritos só pelo
comprimento (`62cm`, `1,12m`, `80cm`) — o gerador usa 40 mm, que é a bitola de
saída de lavatório da NBR 5688. Está em `PADRAO_SEM_DIAMETRO`, e é a única peça
cujo diâmetro é suposto.

**Polegada → milímetro** usa a tabela de conversão da **própria Akato**, da
página 23 do catálogo, coluna PVC soldável. O `3/8"` e o `7/8"` não estão nela
— aparecem só no polietileno e nas válvulas de pia — e vêm de
`POLEGADA_EXTRA`, com 17 e 22 mm.

---

## 2. As primitivas

Quase todo o catálogo é sólido de revolução, e é isso que faz o módulo ser
pequeno.

**`revolucao(perfil, lados)`** — gira um perfil `[(r, z)]` em torno de Z. Dá
tubo, cap, luva, bucha de redução, nípel, anel de vedação, corpo de registro,
copo de sifão. Fecha com tampa onde o raio é zero.

> **Perfil fechado tem de ser soldado.** Todo perfil de peça vazada sai pela
> parede externa e volta pela interna, terminando no ponto de partida. Sem
> detectar isso, os dois anéis coincidem mas são vértices distintos, e a malha
> fica com `2 × lados` arestas de borda — um sólido que parece fechado e no
> viewer mostra o interior pela costura. Era o estado da primeira versão: 64
> arestas abertas por peça, em 15 das 21 formas.

**`varrer_tubo(caminho, r_ext, r_int, lados)`** — varre uma coroa circular ao
longo de um caminho planar no plano XZ. Dá joelho, curva, curva de
transposição e o U do sifão.

O caminho ser planar simplifica muito: a seção fica no plano perpendicular à
tangente, e como a tangente está sempre em XZ, o eixo Y serve de referência
fixa. Não precisa de transporte paralelo de quadro, que é onde uma varredura
genérica costuma torcer.

**`caixa`, `esfera`, `rotacionar_y`, `rotacionar_z`, `transladar`** — o resto.

---

## 3. As 23 formas, e como cada uma é montada

| Forma | Peças | Montagem | Parâmetros do catálogo |
|---|---|---|---|
| `tubo` | 12 | revolução de coroa | DE, comprimento (6 m, do título) |
| `luva` | 50 | corpo com colar nas duas pontas | DE |
| `nipel` | 3 | tubo curto sem colar | DE |
| `cap` | 11 | bolsa numa ponta, fundo fechado | DE |
| `plug` | 3 | tampão maciço + sextavado | DE |
| `anel` | 7 | toro de borracha | DE |
| `reducao` | 39 | tronco entre os dois DE, bolsa no maior | DE1, DE2 |
| `joelho` | 56 | varredura reto-arco-reto + colares | DE, ângulo e raio do título |
| `transposicao` | 3 | dois arcos opostos, desvio em S | DE |
| `te` | 33 | corpo passante + ramo a 90° | DE1, DE2 |
| `juncao` | 3 | corpo passante + ramo a 45° | DE1, DE2 |
| `registro` | 12 | corpo abaulado + haste + alavanca | DE |
| `valvula_retencao` | 1 | corpo abaulado + tampa | DE |
| `torneira_boia` | 1 | corpo + braço + flutuador | DE |
| `engate` | 4 | mangueira corrugada + 2 porcas | DE, comprimento |
| `sifao` | 8 | copo + U + saída, 1 a 3 ramos | comprimento, nº de ramos do título |
| `valvula_pia` | 7 | grelha + corpo roscado (+ ladrão) | DE, variante do título |
| `chuveiro` | 2 | pinha + braço (+ registro) | DE, "com/sem registro" |
| `caixa_sifonada` | 3 | corpo quadrado ou redondo + grelha + saída + 3 ou 5 entradas | corpo, saída, nº de entradas |
| `ralo` | 2 | corpo baixo + grelha + saída | DE, redondo/quadrado |
| `grelha` | 2 | moldura + 7 barras | DE |

O ângulo do joelho, o raio (longa/curta), o número de ramos do sifão, o número
de entradas da caixa sifonada e a cor (preto/branco) saem todos **do título da
família** — que é dado do catálogo, não invenção.

### Cores

As de PVC seguem o que o catálogo afirma na abertura de cada linha: **marrom**
no soldável tradicional, **azul** nas conexões com bucha de latão, **branca**
no roscável e no esgoto. O polietileno sai **preto** e os acessórios seguem o
que o título diz (`SIFÃO EXTENSÍVEL SIMPLES PRETO` × `BRANCO`). Latão, borracha
e metal são escolha de visualização.

---

## 4. A validação

`tools/formas_teste.py` roda as 262 peças e checa quatro coisas que um
round-trip binário não pega:

| Checagem | Por que |
|---|---|
| índice dentro da lista de vértices | malha degenerada |
| bbox entre 5 mm e 7 m | escala trocada de unidade |
| bbox ≤ 14 × DE, quando o catálogo não dá comprimento | proporção absurda |
| **arestas de borda = 0** | cada aresta de um sólido tem de ser compartilhada por exatamente dois triângulos; qualquer outra contagem é buraco |

Mais o round-trip pelo escritor OQ3D e pelo leitor do projeto, para uma peça de
cada forma.

Resultado: **262 de 262 peças, 240.920 triângulos, zero arestas abertas, zero
problemas.**

O teste da estanqueidade foi o que valeu a pena: pegou a costura não soldada da
`revolucao` (15 formas afetadas), o copo do sifão que terminava num anel solto
e a mangueira do engate aberta nas duas pontas. Nenhum desses três aparece em
contagem de triângulo, em bounding box ou no round-trip binário.

---

## 5. E o que só apareceu olhando

Topologia, escala e round-trip cobrem cada sólido **isolado**. Nenhum deles vê
a **posição relativa entre as malhas de uma peça** — e foi exatamente ali que
estavam os dois últimos defeitos, achados abrindo a página no Playwright
(`tools/olhar_preview.mjs`) e olhando as imagens.

**O colar do joelho flutuava solto.** O `caminho_curva` começa em
`z = −(braço − raio)`, e o colar de entrada estava sendo posto em `z = −braço`.
Sobrava um vão de exatamente `raio` entre o corpo e o colar. E o colar da
**saída** simplesmente não existia — eram 56 peças, todas as curvas e joelhos,
com um anel marrom pairando abaixo da peça. Agora os dois colares são
posicionados pelas pontas do próprio caminho, e o da saída é rotacionado para
a tangente de saída.

**O sifão estava desmontado.** Copo solto no alto, U pequeno no chão e tubo de
saída no meio do nada — três sólidos corretos em posições que não se
encontravam. A causa: o `caminho_curva` produz um `∩` (entra subindo, volta
descendo), e o sifão precisa de um `∪`. Foi reescrito com um caminho próprio,
`_caminho_u`, que desce, faz o U no fundo, sobe e entrega numa saída
horizontal.

Os dois passavam em **todas** as checagens automáticas: os sólidos eram
estanques, a bounding box era plausível e o round-trip binário fechava. A lição
é direta — **para geometria inventada, abrir e olhar é parte da validação, não
um extra.** Um mosaico de uma peça por forma custa um minuto e pega a classe de
erro que nenhum invariante numérico alcança.

---

## 6. Onde a ressalva fica gravada

Não depende de ninguém ter lido este documento. Está dentro do `.aq`, nos três
lugares em que um usuário vai encontrar:

1. **`GRUPO_SIMBOLOGIA_3D.NOME_GRUPO`** — `Joelho 90° Soldável (forma
   representativa)`. É o que aparece na árvore do AltoQi.
2. **Propriedade `Geometria 3D`, em cada uma das 262 peças** — *"forma
   representativa gerada por parâmetro; cotas de encaixe não são as do
   fabricante"*. É o que aparece na ficha do produto e na página publicada.
3. **`peca['specs']`** no `catalog.json`, porque a propriedade entra no mapa
   que o `build.py` monta.

A `CLASSE_SIMBOLOGIA_3D` fica **sem** a ressalva, com o nome da linha de
produto de verdade (`AKATO - PVC Água Fria Soldável`): é o primeiro passo da
cascata de inferência do `build.py`, e sujá-la faria o pipeline publicar
"forma representativa" como o nome da linha do catálogo. A ressalva vai no
grupo, um nível abaixo, que é onde não atrapalha a inferência.

---

## 7. Os três arquivos, e quando usar cada um

| Arquivo | Geometria | Tamanho | Para quê |
|---|---|---|---|
| `PVC Construção Civil (sem geometria)/` | nenhuma | 848 KB | o catálogo **fiel**: só o que o PDF diz. Orçamento, especificação, classificação IFC |
| `PVC Construção Civil/` | 12 tubos | 944 KB | demonstra o caminho da geometria com a única forma que o catálogo + norma determinam |
| `PVC Construção Civil (forma representativa)/` | 262 peças | 7,2 MB | visualização e interferência grosseira, com a ressalva gravada |

Os três passam nas 20 checagens do `validar_aq.py` e atravessam o `build.py`.
O terceiro publica **262 produtos, 262 geometrias, 0 peças sem forma 3D**, com
15,4 MB de JSON de geometria — média de 60 KB por peça.

---

## 8. O que faria isso virar geometria de produção

Em ordem de esforço, o mesmo caminho de
`04-lacunas-do-catalogo-comercial.md`:

1. **Tabela técnica da Akato** — substitui as sete proporções inventadas pelas
   cotas reais. É a troca de menor esforço e maior ganho: o módulo já está
   estruturado para isso, basta trocar `PROPORCOES` e `PAREDE_NBR` por valores
   do fabricante.
2. **IFC ou STEP da Akato** — dispensa o paramétrico. O projeto já lê IFC
   (`scripts/parse_ifc.py`) e o `oq3d_writer.py` fecha o outro lado.
3. **Medição das peças** — o que o próprio AltoQi faz.

Até lá, o que está no arquivo é honesto sobre o que é: forma plausível, cota
não conferida.
