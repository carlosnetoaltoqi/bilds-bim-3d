# Extrair tabelas de um catálogo comercial em PDF

> Método derivado de um catálogo comercial real (~270 produtos, gerado no Adobe Illustrator), que virou
> um `.aq` aceito pelo Builder: 10 tabelas, ~270 linhas, zero linhas incompletas, zero códigos repetidos,
> conferido linha a linha contra o PDF.

## Por que `extract_text()` falha

Um catálogo comercial em PDF, no formato mais comum de distribuição de fabricante, foi
diagramado no Illustrator (e às vezes reprocessado por uma ferramenta de otimização de PDF por
cima). Cada célula de uma tabela é um **operador de texto independente, posicionado em
coordenada absoluta** — a ordem em que os operadores foram desenhados não é a ordem de
leitura da tabela.

`extract_text()` (pypdf e equivalentes) agrupa fragmentos de texto vizinhos por heurística de
proximidade. Em tabelas de colunas estreitas isso cola células de colunas diferentes:

```
células reais:  '21055' (x=87)   '400' (x=278)   '50mm' (x=154)   '10' (x=221)
extract_text:   '21055 40050mm 10'
```

O número da embalagem se funde ao da caixa master, a descrição gruda no código seguinte — e
isso não acontece em todas as linhas, só numa fração delas por página. É sutil o bastante
para passar despercebido numa conferência superficial e sistemático o bastante para inutilizar
a extração linha a linha.

**A camada de operadores de texto não tem esse problema.** Interceptando os operadores
`Tj`/`TJ` (e as variantes `'`/`"`) com um *visitor* antes da montagem heurística, cada célula
chega isolada, com a sua posição em coordenada de página.

### Três detalhes que erram silenciosamente

- **A posição é `tm × cm`, não só `tm`.** `tm` é a matriz de texto corrente; `cm` é a matriz
  gráfica corrente, e a posição de dispositivo aplica uma sobre a outra. Usar só `tm` põe fora
  do lugar todo texto dentro de um grupo/bloco transformado.
- **O encoding costuma ser cp1252**, não UTF-8 nem latin-1 puro — a mesma armadilha de
  encoding do `.aq` (ver `docs/conhecimento/aq-formato.md`). Latin-1 decodifica sem lançar erro
  e erra silenciosamente a faixa 0x80–0x9F (acentos e cedilha em maiúscula, por exemplo).
- **Arrays `TJ` trazem kerning intra-palavra**: um array como `[b'CUR', 18, b'T', 92, b'A']`
  é a palavra `CURVA` com ajuste de espaçamento entre glifos, não três células diferentes.
  Concatenar as partes de texto e ignorar os números do array é o correto — desde que se
  confirme, no catálogo em mãos, que um salto de coluna nunca acontece dentro de um único
  `TJ` (cada coluna tem seu próprio operador).

## O problema de verdade: a coordenada Y está corrompida

Com as células já separadas, o passo óbvio é agrupar por linha de base (`y`). **Isso não
funciona** neste tipo de arquivo.

O Illustrator desenha cada tabela **por bloco de coluna**, não por linha: primeiro todo o
bloco de códigos, depois todo o bloco de quantidades, depois o cabeçalho, depois as
descrições. Cada bloco de texto tem seu próprio entrelinhamento — e em vários blocos esse
entrelinhamento sai corrompido no PDF final, de forma que o `y` reportado por uma célula pode
cair dezenas de pontos longe de onde a linha visual está, ou até fora da página.

**O que se preserva é a ordem.** Dentro de um mesmo bloco de coluna, a ordem de desenho dos
operadores espelha exatamente a ordem visual das linhas da tabela — é o único invariante
confiável do arquivo. O casamento entre colunas, então, não é por coordenada: é por
**ordinal** — o i-ésimo código da coluna CÓDIGO com a i-ésima quantidade da coluna
correspondente, e assim por diante.

## O algoritmo, em sete passos

```
para cada página:
  1. juntar células partidas             (mesma linha de base, x adiantado até poucos pontos)
  2. separar em regiões                  (o catálogo tem colunas de painel de produto na página)
  3. dentro de cada região, fatiar em tabelas pelo cabeçalho que abre cada uma
  4. atribuir cada célula a uma coluna    (pela FRONTEIRA entre âncoras de cabeçalho, não por banda fixa)
  5. confirmar pelo tipo do conteúdo      (regex de código / quantidade / descrição / título)
  6. casar as colunas por ordinal
  7. casar o título pelo POSTO na ordem de desenho (não pela coordenada)
```

1. **Juntar células partidas.** O motor de PDF costuma partir uma célula em mais de um
   operador de texto: glifos consecutivos sem avanço acumulado no mesmo `x`/`y`, ou um segundo
   operador com reposicionamento explícito poucos pontos à frente do primeiro. Um limiar de
   poucos pontos (bem menor que a distância entre colunas) junta ambos os casos com segurança.
   O segundo caso é o mais traiçoeiro: sem juntar, um fragmento como `1` seguido de `"` vira
   duas células, a primeira classificada como quantidade e a segunda como o resto de uma
   descrição truncada.

2. **Separar em regiões.** Quando o layout intercala mais de uma tabela lado a lado na mesma
   página, tratar a página como uma sequência única mistura os dados de tabelas diferentes.

3. **Fatiar em tabelas** pelo cabeçalho de código: uma tabela vai do seu cabeçalho até o
   cabeçalho seguinte **da mesma região** — com a exceção de células desenhadas **antes** do
   próprio cabeçalho da sua tabela (uma corrida inteira de produtos, ou a tabela inteira, pode
   preceder o cabeçalho na ordem de desenho). Por isso a primeira tabela de cada região também
   recolhe o que veio antes do seu cabeçalho; nada além de título ou texto de abertura costuma
   estar ali, e nenhum dos dois sobrevive ao passo 5.

4. **Coluna por fronteira entre âncoras, não por banda de largura fixa.** Um valor
   centralizado numa coluna estreita se afasta do texto do cabeçalho por uma distância que
   varia muito de linha para linha — banda fixa perde valores legítimos e ganha valores de
   outra coluna (o número de página, por exemplo, pode cair dentro de uma banda mal calibrada
   e entrar como se fosse um dado da última coluna). A fronteira entre uma âncora de cabeçalho
   e a próxima resolve isso sem ambiguidade.

5. **O tipo do conteúdo confirma a coluna**, com regex simples: código numérico de poucos
   dígitos; quantidade inteira (com separador de milhar quando é a caixa master); descrição
   (contém unidade de medida, aspas de polegada, ou o padrão de um diâmetro nominal); título
   (caixa alta, corpo de fonte numa faixa distinta do corpo dos dados). Duas armadilhas
   próprias de regex:
   - a regex de descrição precisa ser **sensível a maiúscula/minúscula** — com
     `IGNORECASE`, um fragmento de título como "6M" (de "tubo de 6 metros") casa com a unidade
     "m" e é lido como descrição, desalinhando a tabela inteira a partir dali;
   - o indicador ordinal (`º`, como em "90º") **não é uma letra minúscula** para a checagem
     certa: `str.islower()` devolve `True` para ele porque é alfanumérico-símbolo, mas a
     categoria Unicode correta é `Lo` (letter, other), não `Ll` (letter, lowercase); testar com
     `unicodedata.category(c) == 'Ll'` evita classificar um título inteiro como texto corrido.

6. **Casar colunas por ordinal**, com uma verificação de sanidade que o próprio catálogo
   oferece de graça quando existe uma relação de ordem conhecida entre duas colunas (por
   exemplo, a caixa master nunca é menor que a unidade de embalagem) — quando duas colunas
   chegam trocadas, essa relação corrige e o extrator registra o aviso.

7. **Título por posto na ordem de desenho, não por coordenada.** O bloco de título (nome da
   família de produto, em caixa alta, ao lado da foto) tem o `y` tão corrompido quanto o resto
   — a ponto de **inverter a ordem** de dois títulos consecutivos numa mesma página. A ordem
   de desenho dos blocos de título, ao contrário, acompanha a ordem visual dos painéis de
   produto ao longo do documento inteiro, mesmo quando o bloco de título é desenhado depois da
   sua própria tabela. Dois filtros isolam o que é título de família: recuo (títulos ficam numa
   faixa de indentação própria, diferente de legenda de margem ou título de seção) e corpo de
   fonte (numa faixa distinta tanto de título de seção quanto de rótulo de infográfico); e dois
   blocos só se fundem em um título quando são vizinhos na ordem de desenho — sem isso, dois
   títulos de famílias diferentes que compartilham a mesma coordenada X viram um título só.

O que torna a depuração possível: o extrator deve emitir um **aviso sempre que o número de
valores de uma coluna não bate com o número de códigos** da tabela. Sem essa checagem, uma
tabela montada errado ainda sai plausível — cada correção de bug, nesse tipo de extrator, veio
de um aviso próprio, não de uma inspeção manual do resultado.

## O que um catálogo comercial NUNCA determina

Um PDF de catálogo comercial serve ao comprador: código, descrição dimensional, embalagem. Ele
**não é**, e não pretende ser, um desenho técnico. Por mais completa que a extração seja, ela
nunca produz:

- **Forma ou cota de forma.** O catálogo diz o diâmetro nominal e nada sobre raio de curva,
  profundidade de bolsa, espessura de colar ou qualquer outra cota que defina a geometria da
  peça. Não há malha possível só com esse dado — inventar as cotas produziria um sólido que
  **não é** o produto do fabricante, e ele iria para dentro de projetos de instalação, onde a
  interferência com outro elemento se decide em centímetros.
- **Pontos de conexão.** Onde a peça encaixa na rede, e sobretudo o comprimento equivalente de
  perda de carga de cada conexão — um dado técnico, publicado (quando publicado) em folha
  separada da comercial, nunca no catálogo de venda.
- **Simbologia 2D** — o símbolo de planta e de corte que uma biblioteca BIM completa carrega,
  num formato binário próprio do software de destino.
- **Códigos de diâmetro abaixo de determinada bitola** — faixas de diâmetro nominal comuns
  (água fria de pequeno calibre, por exemplo) simplesmente não aparecem nas bibliotecas de
  referência disponíveis para inferir o código; a peça fica com a sentinela em vez de um
  código adivinhado.

**Consequência direta para quem escreve um `.aq` a partir só de um PDF:** o arquivo fiel ao
catálogo sai **sem geometria nenhuma** — o que é o comportamento correto, não uma lacuna do
extrator (312 de 1.168 peças de uma biblioteca real de fabricante também não têm simbologia
3D: são as peças cuja forma o software gera parametricamente, não uma exceção). Se o objetivo
inclui visualização e contagem de peça, a geometria precisa vir de uma fonte adicional — e,
sem cota de fabricante, essa fonte é a forma REPRESENTATIVA (`formas-representativas.md`), não
uma invenção de cota de encaixe fingindo ser dado.

Em ordem de esforço, o que fecha essa lacuna de verdade: uma tabela técnica do fabricante
(comprimentos equivalentes, espessuras, cotas de encaixe — geralmente publicada à parte da
comercial); um IFC ou STEP que o fabricante já tenha; geometria paramétrica por norma técnica
(aceitável para visualização, não para conferir encaixe); ou medição direta da peça.

## Onde está no código

- Este documento descreve o **método**; a implementação de referência e os dados
  intermediários do catálogo estudado estão arquivados em `docs/historico/estudos/` (não normativo;
  consulta pontual).
- `docs/conhecimento/aq-formato.md` — a mesma armadilha de encoding (cp1252) do lado da
  escrita do `.aq`.
- `biblioteca/bim_pipeline/aq/formas_parametricas.py` — o gerador de forma representativa que
  fecha a lacuna de geometria quando não há cota de fabricante.

## Ver também

- `docs/conhecimento/formas-representativas.md` — o que fazer com a lacuna de geometria que
  todo catálogo comercial deixa.
- `docs/conhecimento/plugin-cad-catalogo-web.md` — a mesma classe de problema (tabela com
  cabeçalho de duas linhas, `colspan`/`rowspan`) resolvida em HTML em vez de PDF.
- `docs/conhecimento/aq-formato.md` — o schema e as armadilhas de encoding de quem recebe estes
  dados no `.aq`.
- `CONCEPTS.md` — verbete "Forma representativa".
