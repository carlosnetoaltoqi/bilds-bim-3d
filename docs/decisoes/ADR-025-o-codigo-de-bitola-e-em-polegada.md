# ADR-025 — o código de bitola do AltoQi é uma escala **em polegada**

**Status:** Aceita (2026-09-10)

## Decisão

`ENTRADA_PECA.DIAMETRO_EP`, `ENTRADA_3D.DIAMETRO` e `PECA.DIAMETRO_PECA` guardam o **índice de uma
escala de bitolas nominais em polegada**, não uma medida nem uma escala em milímetro:

| cód | 0 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pol | 1/4" | 3/8" | 1/2" | 5/8" | 3/4" | 1" | 1.1/4" | 1.1/2" | 2" | 2.1/2" | 3" | 4" | 5" | 6" | 8" | 10" | 12" |

O escritor passa a decidir o código assim, nesta ordem:

1. **a polegada declarada no nome** (`cadastro.codigo_de_polegada`) — sem ambiguidade nenhuma;
2. **a bitola em milímetro**, quando ela cai num único código no catálogo inteiro
   (`cadastro.MM_INEQUIVOCO`, 28 valores);
3. **a série da biblioteca**, nas três bitolas em milímetro que colidem — 40, 50 e 75 mm;
4. **sentinela e aviso**, quando nada disso resolve.


> **Escopo medido em 2026-09-11 (auditoria cruzada):** a escala vale para as disciplinas
> hidráulicas. Nas entradas de máscara **64 (elétrico)**, 10.097 de 13.665 trazem o código **2**
> independentemente da bitola nominal (20 a 150 mm caem todas nele) — é o valor por omissão do
> cadastro elétrico, não 3/8". Os 17 códigos da escala foram reconferidos um a um contra o nome da
> peça e **16 batem**; o 4 (5/8") só destoa porque seus nomes são adaptadores "20 mm × 3/4"".

## Por quê

A tabela que existia (`aq_writer.CODIGO_DIAMETRO = {40: 8, 50: 9, 60: 10, 75: 11, 100: 12, 150: 14,
200: 15}`) foi montada a partir de poucos pares vistos em bibliotecas nativas, e a leitura de que
era uma escala "nominal em milímetro" estava errada de duas maneiras:

- **60 → 10 não existe em série nenhuma.** No catálogo oficial (`Catalog.db`, 33.041 linhas de
  `ENTRADA_PECA`), 60 mm aparece **só** no código 9, e o 10 é 2.1/2". O par foi inferido por
  interpolação numa amostra pequena, e é invenção.
- **A mesma bitola em milímetro é dois códigos diferentes, dependendo da série.** 40 mm aparece no
  código 7 (80 peças) e no 8 (117); 50 mm no 8 (85) e no 9 (136); 75 mm no 10 (60) e no 11 (152).
  Não é ruído: é a equivalência mm ↔ polegada mudando de material. Em PVC soldável de água fria
  40 mm é 1.1/4"; em PVC esgoto, 1.1/2". A tabela antiga era a do esgoto, e errava **toda** bitola
  de PVC soldável por um degrau.

O que fecha a escala é o **nome em polegada**, que é como o catálogo oficial nomeia a maioria das
peças: 1/2"→3 em 584 peças, 3/4"→5 em 533, 1"→6 em 542, 1.1/4"→7 em 364, 1.1/2"→8 em 363, 2"→9 em
391, 2.1/2"→10 em 187, 3"→11 em 223, 4"→12 em 186, 5"→13, 6"→14, 8"→15, 10"→16, 12"→17. As séries em
milímetro batem em cima disso: cobre (15, 22, 28, 35, 42, 54, 66, 79, 104 mm) preenche os códigos 3
a 12 sem colidir com nada.

## Consequências

- **O detector de bocais precisa da série** para as três bitolas que colidem. Ela sai do título da
  biblioteca (`cadastro.serie_do_titulo`: "soldável"/"água fria" × "esgoto"/"série normal") e, **sem
  ela, o bocal fica sem código** — a sentinela `-2147483647`, que é o que as conexões nativas fazem.
  Gravar o palpite poria a peça uma bitola inteira fora, calado.
- O código **1** fica de fora da tabela: nenhuma peça do catálogo oficial o usa com nome em
  polegada. Pela posição seria 5/16", e escrever isso seria repetir o erro do 60 → 10.
- As bitolas de água fria abaixo de 40 mm (20, 25, 32), que "não apareciam em nativa nenhuma",
  aparecem sim — 20 mm → 3, 25 mm → 5, 32 mm → 6 — e agora saem com código.
- A pergunta à engenharia do Builder sobre "a lista de diâmetros na ordem" deixa de ser bloqueio e
  vira **confirmação**: a escala saiu por medição.

## Como se mediu

Uma consulta agregada no catálogo oficial, cruzando `ENTRADA_PECA.DIAMETRO_EP` com `PECA.NOME_PECA`
e contando os nomes por código — descrita em `docs/conhecimento/aq-formato.md`. O primeiro cruzamento
tentado (código × `PECA.DIAMETRO_PECA`) não deu nada, porque `DIAMETRO_PECA` guarda ora uma medida
real, ora o próprio código; foi o **nome** que separou uma coisa da outra.
