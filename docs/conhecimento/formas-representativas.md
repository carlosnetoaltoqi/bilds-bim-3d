# Formas representativas — geometria paramétrica quando o fabricante não publica cota

> Proveniência: `docs/historico/estudos/escrita-aq-de-pdf/estudo/06-formas-parametricas.md`,
> do estudo de escrita de um `.aq` a partir de um catálogo comercial em PDF (ver
> `pdf-catalogo.md`). Aplicado a um catálogo real de PVC hidráulico — 262 peças com geometria,
> zero arestas de borda, aceito pelo pipeline do projeto. Nomes de fabricante ficam só no
> histórico (ADR-016); aqui fica a técnica.

## O problema: catálogo comercial não tem cota de forma

Um catálogo comercial (`pdf-catalogo.md`) diz o diâmetro nominal, o código e a embalagem de
cada peça, e **nada** sobre raio de curva, profundidade de bolsa ou espessura de colar. Sem
essas cotas não há malha possível fiel ao produto do fabricante. Quando o objetivo do `.aq`
inclui visualização 3D e contagem de peça — não só orçamento e especificação — a saída sem
geometria não basta, e inventar cota fingindo que é dado do fabricante é pior que não ter
geometria: o resultado pareceria confiável e não é.

A saída é gerar uma malha **explicitamente marcada como aproximada**: plausível o bastante
para visualizar e contar, honesta sobre não servir para conferir encaixe.

## Separar DADO, NORMA e INVENÇÃO

Toda peça gerada por este método mistura três origens, e a regra de cada uma precisa estar
explícita no código, não só na cabeça de quem escreveu:

| Origem | O que vem dela | Confiança |
|---|---|---|
| **DADO** (do catálogo) | diâmetro nominal, segundo diâmetro nas reduções, comprimento total quando o catálogo o dá (no título ou na descrição) | dado real |
| **NORMA** (técnica) | espessura de parede — NBR 5648 (tubo/conexão soldável de PVC) e NBR 5688 (esgoto) tabelam a espessura por bitola | dado normativo |
| **INVENÇÃO** (proporção) | tudo o que não é dado nem norma: profundidade de bolsa, sobre-espessura de colar, raio de curva, dimensão de corpo de registro | aproximação, com a regra explícita |

A tabela de proporções inventadas é deliberadamente pequena — poucas regras cobrem a maioria
das formas — e cada regra é uma função do diâmetro externo, não uma constante solta:

```python
PROPORCOES = {
    'bolsa':          lambda de: 0.60 * de + 4.0,   # profundidade do encaixe
    'colar':          lambda de: 3.0,               # sobre-espessura do colar da bolsa
    'braco':          lambda de: 0.60*de + 4.0 + 0.35*de,  # centro do joelho até a face
    'raio_longa':     lambda de: 1.50 * de,          # eixo de uma curva longa
    'raio_curta':     lambda de: 0.75 * de,          # eixo de uma curva curta
    'registro_diam':  lambda de: 1.70 * de,          # corpo do registro de esfera
    'registro_comp':  lambda de: 1.30 * de,
}
```

A espessura de parede consulta primeiro a tabela normativa (`PAREDE_NBR`, por seção e
bitola); fora das bitolas tabeladas, cai numa regra aproximada (`max(1.5, 0.055·DE)` mm) —
essa, sim, é invenção, e diferente da regra normativa em confiança.

Quando o próprio catálogo não dá diâmetro para uma peça (por exemplo, um acessório descrito
só pelo comprimento), o gerador usa uma bitola padrão de norma para aquele tipo de saída — é a
única peça cujo diâmetro é suposto, e isso também precisa ficar marcado, não escondido dentro
de um valor que parece dado.

Trocar `PROPORCOES` e a tabela normativa por cotas reais de um fabricante, quando elas
existirem, é a troca de menor esforço e maior ganho: o gerador já está estruturado para isso —
é questão de substituir os valores, não de reescrever a lógica.

## Os geradores

`biblioteca/bim_pipeline/aq/formas_parametricas.py` traz **21 geradores** (`GERADORES`,
função por forma), cada um devolvendo `[(verts, tris, rgba), …]` — uma lista de malhas por
peça, não uma malha só, o mesmo jeito que uma simbologia real de fabricante guarda (várias
malhas por peça; sem união booleana, sobreposição de sólidos é aceitável).

Duas primitivas cobrem a maior parte do catálogo, porque a maioria das peças de tubulação é
sólido de revolução ou varredura de coroa circular ao longo de um caminho planar:

- **`revolucao(perfil, lados)`** — gira uma seção meridiana `[(r, z)]` em torno do eixo Z.
  Dá tubo, cap, luva, bucha de redução, nípel, anel, corpo de registro — a maioria das formas.
- **`varrer_tubo(caminho, r_ext, r_int, lados)`** — varre uma coroa circular ao longo de um
  caminho planar no plano XZ. Dá joelho, curva, curva de transposição, o U de um sifão. O
  caminho ser planar simplifica a varredura: a seção fica no plano perpendicular à tangente e,
  como a tangente está sempre em XZ, o eixo Y serve de referência fixa — sem precisar de
  transporte paralelo de quadro, que é onde uma varredura genérica costuma torcer.

O ângulo de um joelho, o raio (longa/curta), o número de ramos de um sifão, o número de
entradas de uma caixa de inspeção e a cor de uma peça saem do **título/descrição da família**
— dado do catálogo, não invenção — enquanto a forma em si (bolsa, colar, raio) vem das
proporções.

## Unidades

**Centímetro, Z-up** — a mesma convenção do OQ3D (`docs/conhecimento/oq3d.md`). Os diâmetros
do catálogo, tipicamente em milímetro, são convertidos na entrada de cada gerador.

## Os dois defeitos que passam em bbox + triângulos + roundtrip

Um gerador de geometria precisa de verificação além de round-trip binário e contagem bruta de
triângulos — as duas checagens mais óbvias **não pegam** os dois defeitos mais sérios deste
tipo de forma.

### (a) Perfil de revolução fechado sem soldar a costura

Todo perfil de peça vazada sai pela parede externa e volta pela parede interna, terminando no
mesmo ponto em que começou — um perfil "fechado". Sem tratamento especial, o último anel de
vértices da revolução coincide em posição com o anel inicial mas é um **conjunto de vértices
distinto** (mesma coordenada, índice diferente). O sólido resultante *parece* fechado — mesma
contagem de vértices, mesmo volume, passa em bbox — mas tem uma costura aberta: exatamente
`2 × lados` arestas com um único triângulo em vez de dois.

A checagem que pega isso, e que bbox/round-trip não pegam: **contar as arestas com
exatamente dois triângulos incidentes**. Num sólido fechado de verdade, toda aresta é
compartilhada por exatamente dois triângulos; qualquer aresta com um só triângulo é uma
aresta de borda, e um sólido gerado ou costurado programaticamente deve ter **zero** delas —
ao contrário de uma malha de fabricante real, onde arestas de borda entre um quarto e um terço
do total são normais (ver `CONCEPTS.md`, verbete "Arestas de borda"). O fix é detectar o perfil
fechado antes de gerar a malha e reaproveitar o anel inicial em vez de duplicá-lo.

### (b) Malhas certas, position relativa errada

Cada sólido isolado pode estar perfeito — estanque, com a proporção certa, sobrevivendo ao
round-trip byte a byte — e ainda assim a peça inteira estar errada, porque a **posição
relativa entre as malhas que compõem uma peça** não é algo que topologia, escala ou
round-trip binário enxergam. Dois exemplos que só apareceram abrindo a peça e olhando:

- um colar de conexão calculado a partir do ponto errado do caminho de varredura, deixando um
  vão entre o colar e o corpo da peça — invisível em qualquer checagem numérica, óbvio ao
  olhar a peça de lado;
- um caminho de varredura com a concavidade invertida (um `∩` onde a peça precisa de um `∪`),
  resultando nas partes de uma mesma peça (corpo, curva, saída) montadas em posições que não
  se encontram — todas as partes corretas isoladamente, o conjunto sem sentido.

**A única checagem que pega isso é uma RENDERIZAÇÃO.** Um mosaico com uma peça por forma,
fotografado (por exemplo abrindo a página do viewer num navegador headless e tirando print),
custa pouco e é a única verificação, automática ou não, capaz de flagrar esse defeito — nenhum
invariante numérico o alcança. (Uma tentativa de automatizar a leitura do canvas renderizado
pode dar falso-negativo: um `WebGLRenderer` sem `preserveDrawingBuffer` descarta o framebuffer
depois de compor o frame, e uma leitura de pixels correndo depois enxerga tudo em branco mesmo
com a cena visível — é a imagem exportada/fotografada que decide, não uma leitura de canvas.)

## A ressalva vai DENTRO do arquivo gerado

Ninguém que abre o `.aq` deveria precisar ter lido este documento para saber que a geometria é
aproximada. A ressalva é gravada em pontos que aparecem naturalmente na navegação:

1. **No nome do grupo de simbologia** — algo como "Joelho 90° Soldável (forma
   representativa)". É o que aparece na árvore de classes do Builder.
2. **Numa propriedade personalizada de cada peça** (por exemplo "Geometria 3D") com o texto
   da ressalva por extenso — forma representativa gerada por parâmetro, cotas de encaixe não
   são as do fabricante. É o que aparece na ficha do produto e na página publicada.

A classificação de mais alto nível (a linha de produto) fica **sem** a ressalva, com o nome
real da linha — a ressalva entra um nível abaixo, no grupo, que é onde não interfere na
inferência de título do catálogo a partir do nome da classe.

## Para que serve e para que não serve

Serve para: visualizar o catálogo em 3D, contar peça, detectar interferência grosseira num
layout preliminar, dar volume a um catálogo publicado que de outra forma sairia sem nenhuma
peça em 3D.

Não serve para: conferir encaixe, folga de instalação real ou colisão fina entre peças — para
isso a cota tem que vir do fabricante (tabela técnica, IFC/STEP publicado, ou medição direta
da peça), não de uma proporção inventada. Uma biblioteca com forma representativa é
honesta sobre o que é — forma plausível, cota não conferida — e a ressalva gravada no arquivo
é o que garante que essa honestidade sobrevive fora do contexto de quem gerou o arquivo.

## Onde está no código

- `biblioteca/bim_pipeline/aq/formas_parametricas.py` — `PROPORCOES`, `PAREDE_NBR`,
  `parede_mm`, as primitivas `revolucao`/`varrer_tubo`/`caixa`/`esfera`/`transladar`/
  `rotacionar_y`/`rotacionar_z`, os 21 geradores e o dicionário `GERADORES`, `gerar()`,
  `bbox()`.
- Contagem de arestas de borda: a mesma checagem de `docs/conhecimento/step-iges.md` e
  `docs/conhecimento/oq3d.md`, aplicada aqui à saída da revolução/varredura em vez de a um
  B-rep importado.
- Proveniência (histórico, não normativo):
  `docs/historico/estudos/escrita-aq-de-pdf/estudo/06-formas-parametricas.md`.

## Ver também

- `docs/conhecimento/pdf-catalogo.md` — por que a lacuna de geometria existe: o que um
  catálogo comercial nunca determina.
- `docs/conhecimento/oq3d.md` — o formato binário em que a malha gerada é, por fim, gravada.
- `docs/conhecimento/step-iges.md` — o mesmo tipo de checagem (arestas de borda, volume
  assinado) aplicado a geometria importada de CAD, em vez de gerada por parâmetro.
- `CONCEPTS.md` — verbetes "Forma representativa" e "Arestas de borda".
