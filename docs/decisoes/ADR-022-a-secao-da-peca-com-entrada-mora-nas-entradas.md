# ADR-022 — peça com ponto de ligação não guarda seção no cadastro

**Status:** Aceita (2026-09-10)

## Decisão

Toda peça que recebe `ENTRADA_PECA` sai com `PECA.SECAO` e `PECA.DIAMETRO_INTERNO` **nulas**. Quem
faz isso é `bim_pipeline.aq.entradas_aq.secao_para_as_entradas`, chamada de dentro do `gravar` — logo
vale nos dois escritores (`geo_to_aq`, `catalogo_to_aq`) e na ferramenta
`preencher_entradas_aq`, que além de detectar bocal varre o arquivo inteiro e conserta peça que já
tinha entrada. `validar_aq` falha se sobrar peça com entrada e seção no cadastro.

Peça **sem** entrada continua como estava (o *default* 10 do schema): não é o caso que esta decisão
trata, e é o que as nativas fazem.

## Por quê

As bibliotecas de 2026-09-09 passaram no Builder: as peças desenharam a simbologia 3D e, lançadas em
projeto, saíram **em planta** na representação unifiliar — a aceitação de ADR-021. Mas o Cadastro
mostrava **"Pontos de ligação 3D: Não"** em todas elas, enquanto os pontos de ligação apareciam
desenhados no lugar certo (as bolinhas vermelhas). Ou seja: as entradas estavam gravadas e o Builder
as lia; o que não acendia era o rótulo.

Medindo as 14 bibliotecas nativas coluna a coluna, com as peças separadas entre as que têm
`ENTRADA_PECA` e as que não têm, sobram exatamente duas colunas da `PECA` em que toda saída nossa
difere de toda nativa:

| coluna | nativa, peça **com** entrada | nativa, peça **sem** entrada | nossa, peça com entrada |
|---|---|---|---|
| `SECAO` | NULL em 1.441/1.441 | 10 em 80, NULL em 290 | 10 |
| `DIAMETRO_INTERNO` | NULL em 1.441/1.441 | 10 em 80, NULL em 290 | 10 |

O corte não é convenção de fabricante: acontece **dentro da mesma biblioteca** — na de esgoto, as
1.115 peças com entrada estão com as duas nulas e 48 das 53 sem entrada estão com 10; na de
barramento blindado, 220 contra 32. A leitura é que seção e diâmetro de uma peça conectável moram
nas entradas (`SECAO_EP`, `DIAMETRO_EP`), e mantê-los também no cadastro da peça é o que faz o
Builder tratá-la como peça sem ponto de ligação 3D. Nenhum dos dois escritores nomeava as colunas,
então o *default* 10 do schema entrava sozinho.

Que anular as duas **acenda** o "Sim" é hipótese até o próximo teste no Builder. O que está medido é
a correlação (1.441/1.441, dentro da mesma biblioteca), que as entradas já são lidas — porque os
pontos saem desenhados no lugar certo — e que, depois de anular, não sobra diferença sistemática
entre peça nossa com entrada e peça nativa com entrada.

## Consequências

- Arquivo já entregue se conserta sem repetir importação: `preencher_entradas_aq` agora varre todas
  as peças com entrada, inclusive num `.aq` que **já** tinha entradas (antes ele pulava a simbologia
  já preenchida e não chegava na seção).
- `validar_aq` ganhou a conferência 9 (pontos de ligação): peça com entrada sem seção no cadastro, e
  nenhuma `ENTRADA_PECA` órfã.
- Se o rótulo continuar em "Não" depois disto, não há mais diferença sistemática de coluna para
  perseguir — o próximo passo é experimento subtrativo no Builder, transplantando o cadastro de uma
  peça nativa que mostra "Sim".
- A seção que a peça perde não se perde: `SECAO_EP` = 10 em toda entrada que escrevemos, que é o
  valor das entradas com geometria na nativa de conexões.
