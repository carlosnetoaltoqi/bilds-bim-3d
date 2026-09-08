# ADR-021 — os pontos de ligação vêm da malha; o `WIREFRAME` é do Builder

**Status:** Aceita (2026-09-09)

## Decisão

Todo `.aq` escrito pelo projeto grava `ENTRADA_3D` e `ENTRADA_PECA`, derivadas da própria malha:
`bim_pipeline.geometria.bocais.bocais(malhas)` acha os bocais (a face anelar na ponta de um tubo) e
`bim_pipeline.aq.entradas_aq` os traduz em linhas das duas tabelas — a `ENTRADA_3D` na simbologia
(posição, em centímetro Z-up no frame da peça), a `ENTRADA_PECA` em cada peça que usa aquela
simbologia (bitola e azimute). Vale para os dois caminhos de escrita, `geo_to_aq` (uma peça) e
`catalogo_to_aq` (catálogo inteiro). Bibliotecas exportadas antes disto se corrigem com
`ferramentas.preencher_entradas_aq`, que detecta a partir do OQ3D que já está no arquivo.

O `WIREFRAME` **continua nulo, de propósito**: o projeto não escreve esse blob e não pretende
revertê-lo.

Simbologia sem bocal reconhecível sai **sem** entrada. O detector não inventa ponto de ligação, e a
contagem de simbologias sem bocal é reportada.

## Por quê

Uma peça nossa, mesmo com a `IMAGEM` de ADR-020, desenha em 3D e sai em **planta** como o símbolo
padrão do Builder — um círculo com um triângulo vermelho, o que ele mostra para peça sem
representação 2D. Isso deixava metade da entrega de fora: quem projeta trabalha na planta.

Planta e corte saem da simbologia 2D **ou** do `WIREFRAME`, e qualquer um dos dois basta — três
experimentos no Builder em nativas de fabricante (aquecedor: só `WIREFRAME`, desenha; conexão de
esgoto: só `WIREFRAME`, desenha; rack: só 2D, desenha). Nas 15 nativas de fabricante, **nenhuma**
das 1.410 peças com geometria 3D está sem os dois; nas nossas, todas as 3.089 estavam.

Entre os dois, o `WIREFRAME` não precisa ser escrito: **o Builder o gera**, desde que a peça tenha
pontos de ligação 3D e a opção "Bifiliar realista" (`PECA.OPCAO_RENDERIZACAO_PLANIFICADA`, domínio
0 = Realista / 1 = Simbologia 2D / 2 = Ambas) não esteja em "Simbologia 2D" — informação da
engenharia que cadastra as bibliotecas, coerente com o que os arquivos mostram (há nativa com
entradas e sem `WIREFRAME`, e nativa com `WIREFRAME` e sem entrada: a presença do blob é resíduo do
fluxo que montou o arquivo, não regra do formato). Reverter o blob custaria caro — ~70 % do arquivo,
0,4 a 2 MB por simbologia, serialização Delphi com classe própria (`T3DWireframeGenerator::TEdge`) —
para produzir o que o Builder já produz.

A posição das entradas tinha de sair da malha porque **nenhuma fonte de geometria marca bocal**: nem
IFC, nem STEP/IGES, nem o PartAtom de uma família Revit. As duas hipóteses alternativas caíram na
medição: o marcador verde/azul do OQ3D não é a fonte (nenhuma nativa com `ENTRADA_3D` tem malha com
cor de marcador) e não há campo no `.aq` que as derive. O que existe é a geometria: aplicado o
*placement* da simbologia, a entrada nativa cai no centro de uma face circular da malha, e o raio
interno dessa face é a bitola. O detector reencontra 21 de 21 entradas numa nativa de aquecedores
(erro mediano 0,00 cm) e 14 de 16 numa de conexões de esgoto (0,06 cm).

## Consequências

- Uma peça exportada daqui passa a ter pontos de ligação: encaixa em tubulação e o Builder gera a
  planta. **Ainda não verificado no Builder** — é a aceitação pendente.
- O detector é hidráulico. Bocal recuado por trás da face (cadastro feito à mão numa nativa de
  bombas) e ponto de ligação que não é abertura de malha (entrada de cabo num rack) ficam fora;
  medidas em `docs/conhecimento/geometria.md`.
- Bitola fora da escala de diâmetros do AltoQi fica sem código (sentinela em `DIAMETRO_EP`, 0 em
  `DIAMETRO`, que é o valor de 608 das 634 linhas nativas). Acontece em sistema que não é PVC.
- `LIGACAO_EP` fica em 0 em toda entrada: o enum (0 a 3) não está determinado, `TIPO_LIGACAO` está
  vazia nas nativas, e 0 é o valor mais comum. É a próxima pergunta para a engenharia.
- Custo de exportação: ~2 s por simbologia de 56 mil triângulos, somados aos 30 ms da `IMAGEM`. Num
  catálogo de 1.399 simbologias é o passo mais caro da escrita.
- Substitui a afirmação de ADR-020 de que as entradas "não são necessárias": não são, para desenhar
  em 3D; são, para planta e corte.
