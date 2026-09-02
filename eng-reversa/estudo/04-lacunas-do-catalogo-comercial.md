# O que um catálogo comercial dá, e o que falta para uma biblioteca BIM

Um `.aq` de fabricante e um catálogo comercial em PDF servem a públicos
diferentes. O PDF serve ao comprador: código, descrição dimensional,
embalagem. O `.aq` serve ao projetista: forma, pontos de conexão, perda de
carga.

**A engenharia reversa do formato foi resolvida. A lacuna que sobra é de dado,
não de formato** — e é onde está o trabalho de verdade para uma biblioteca de
produção.

---

## 1. O que o PDF da Akato dá

Tudo isto entrou no `.aq` gerado, direto do catálogo:

| Dado | Onde foi | Cobertura |
|---|---|---|
| Código comercial | `ITEM.CODIGO_ITEM` e a propriedade `Código Akato` | 269 / 269 |
| Descrição dimensional | `PECA.NOME_PECA`, `PECA.DESCRICAO_DADOS` | 269 / 269 |
| Família de produto | `GRUPO_PECA.NOME_GP` | 87 famílias |
| Linha de produto | `CLASSE_PECA.NOME_CP` | 5 linhas |
| Unidades por embalagem | propriedade `Embalagem` | 262 / 262 peças |
| Unidades por caixa master | propriedade `Caixa master` | 247 / 262 |
| Norma técnica | propriedade `Norma` (NBR 5648 / NBR 5688) | 198 |
| Pressão de serviço | propriedade `Pressão de serviço` | 129 |
| Cor | propriedade `Cor` (marrom / azul / branca) | 198 |
| Tipo de junta | propriedade `Tipo de junta` (soldável / roscável) | 129 |
| Temperatura máxima | propriedade `Temperatura máxima de operação` | 69 |
| Conversão polegada × mm | `dados/akato-catalogo.json` | 12 linhas |

As quatro últimas não estão nas tabelas de produto: vêm do texto de abertura de
cada linha. A NBR 5648 e os 7,5 kgf/cm² estão na página 5; a NBR 5688 e os
45 °C em regime não contínuo, na 12. A regra de cor sai da frase "utiliza a cor
marrom nos produtos tradicionais e a cor azul nas conexões com bucha de latão",
cruzada com os títulos que dizem `COM BUCHA DE LATÃO (SBL)`.

Também deu para inferir, das próprias famílias, a classificação IFC de cada
grupo: `IfcPipeFitting` com subtipo de curva, luva, cap, tê ou redução;
`IfcPipeSegment` para tubo; válvula para registro; terminal de descarte para
ralo e caixa sifonada. São 10 combinações de entidade e subtipo nos 83 grupos.

---

## 2. O que o PDF não dá

### Geometria — a lacuna principal

**O catálogo não traz uma única cota de forma.** `JOELHO 90° SOLDÁVEL 25mm` diz
o diâmetro nominal e nada sobre o raio da curva, o comprimento da bolsa, a
profundidade do encaixe ou a espessura do colar. Sem isso não há malha.

Inventar as cotas produziria um sólido que **não é** o produto da Akato — e ele
iria para dentro de projetos de instalação, onde a colisão com uma laje ou uma
viga se decide em centímetros.

Não ter geometria não é um defeito do arquivo. **312 das 1.168 peças da Amanco
(27%) também não têm linha em `PECA_SIMBOLOGIA_3D`**: são as peças sem forma
fixa, que o AltoQi gera parametricamente. E a única categoria cuja forma o
catálogo determina — o tubo, um cilindro vazado de diâmetro nominal e 6 m — é
justamente uma das que a Amanco deixa sem geometria, porque o AltoQi gera o
cilindro a partir de `DIAMETRO_PECA` e `COMPRIMENTO_PECA`.

Por isso o arquivo padrão sai **sem geometria nenhuma**. Há duas variantes com
geometria, e as duas são rotuladas dentro do arquivo:

- **`--geometria-demo`** — malha só para as 12 peças de tubo, com espessura de
  parede da NBR 5648 e da NBR 5688. É a única forma que o catálogo mais a
  norma determinam por completo.
- **`--geometria-parametrica`** — malha para todas as 262 peças, com as
  proporções que faltam vindas de uma tabela de invenção explícita. Ver
  `06-formas-parametricas.md`: serve para visualizar e para interferência
  grosseira, não para conferir encaixe.

### Pontos de conexão — a lacuna funcional

`ENTRADA_PECA` e `ENTRADA_3D` guardam onde a peça encaixa na rede: posição,
diâmetro, tipo de seção e o **comprimento equivalente** de perda de carga.

A Amanco preenche 2.627 linhas de `ENTRADA_PECA`, com `COMPRIMENTO_EP` peça por
peça (2,19 m, 2,39 m…) — valores da tabela técnica do fabricante, não do
catálogo comercial. O catálogo da Akato não os traz.

Uma `ENTRADA_PECA` com `COMPRIMENTO_EP = 0` seria pior que nenhuma: o AltoQi
calcularia **perda de carga zero** naquela conexão, silenciosamente otimista,
e o dimensionamento hidráulico de quem usasse a biblioteca sairia errado sem
nenhum aviso. Por isso as duas tabelas ficam vazias.

> Esta é provavelmente a limitação mais séria do arquivo gerado: sem pontos de
> conexão, o Builder não deve conseguir encaixar a peça numa rede
> automaticamente. Ela vem do catálogo, não do formato.

### Simbologia 2D

As cinco tabelas de `CONTEUDO_SIMBOLOGIA` guardam o símbolo de planta e de
corte, num formato binário próprio que este estudo não decifrou (a Amanco tem
469 blobs de ~8,2 KB cada). O catálogo comercial também não teria essa
informação. A peça aparece em 3D e em lista; a representação em planta cai no
símbolo genérico do AltoQi.

### `WIREFRAME`

As arestas para planta e corte, 69–71% do tamanho de um `.aq` real. Formato não
decifrado, e não vem do catálogo.

### Códigos de diâmetro abaixo de 40 mm

A escala de `CODIGO_DIAMETRO` do AltoQi só é observável em parte nas 12
bibliotecas disponíveis. As bitolas de água fria de 20, 25 e 32 mm não
aparecem em nenhuma, então essas peças ficam com a sentinela em vez de um
código adivinhado — ver `01-escrever-um-aq.md`, seção 4.

---

## 3. Onde os dados que faltam existem

Em ordem de esforço:

1. **Tabela técnica da Akato.** Comprimentos equivalentes, espessuras de
   parede e cotas de encaixe são publicados em folha técnica separada do
   catálogo comercial, ou fornecidos sob demanda. Preenche `ENTRADA_PECA` e
   viabiliza geometria paramétrica de verdade.
2. **IFC ou STEP da Akato.** Se o fabricante já publica família BIM (Revit,
   ArchiCAD) ou modelo em STEP, a malha sai direto. O caminho de leitura de IFC
   já existe no projeto (`scripts/parse_ifc.py`) e o escritor OQ3D fecha o
   outro lado: IFC → malha → `.aq`.
3. **Geometria paramétrica por norma.** A NBR 5648 e a NBR 5688 normalizam
   diâmetro externo, espessura e comprimento de bolsa. Dá para gerar joelhos,
   luvas, tês e caps com forma **conforme a norma** — e é uma peça normalizada,
   não a peça da Akato. Aceitável para visualização e interferência
   aproximada; a rotular como tal.
4. **Medição das peças.** Escaneamento ou paquímetro. É o que o próprio AltoQi
   faz ao montar uma biblioteca de fabricante.

O `tools/oq3d_writer.py` já traz as primitivas para os caminhos 2 e 3:
`cilindro()`, `tubo()`, `transladar()` e `concatenar()`, todas em centímetro e
Z-up, e o `escrever()` aceita transform por malha — o suficiente para montar um
joelho de dois trechos rotacionados.

---

## 4. O que o arquivo gerado já serve para

Mesmo sem geometria e sem pontos de conexão, as 262 peças e 269 insumos são
úteis:

- **Orçamento.** `ITEM` com fabricante, categoria e código comercial, e
  `ITEM_ASSOCIADO` ligando insumo a peça. É o caminho de quantitativo do
  AltoQi, e está completo.
- **Especificação.** Norma, pressão, cor, tipo de junta, temperatura,
  embalagem e caixa master por peça — 1.494 valores de propriedade.
- **Classificação IFC.** Os 83 grupos saem com entidade e subtipo IFC4 e
  IFC2×3 corretos, o que faz a peça exportar como `IfcPipeFitting` ou
  `IfcPipeSegment` do tipo certo.
- **Estrutura de catálogo.** 5 linhas de produto, 87 famílias, hierarquia
  pronta para receber geometria quando ela existir — bastam
  `SIMBOLOGIA_3D` e `PECA_SIMBOLOGIA_3D`, e o vínculo é chave estrangeira, não
  casamento por nome.
