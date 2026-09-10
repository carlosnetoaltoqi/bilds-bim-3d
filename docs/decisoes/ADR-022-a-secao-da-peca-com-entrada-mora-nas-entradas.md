# ADR-022 — peça com ponto de ligação não guarda seção no cadastro

**Status:** Aceita (2026-09-10) · **causa corrigida no mesmo dia por ADR-023**

> **Correção (2026-09-10, mesma sessão):** a regra abaixo está certa e foi reconfirmada numa
> amostra 10× maior (15.321 de 15.321 peças com `ENTRADA_PECA` no catálogo oficial do Builder
> têm as duas colunas nulas). O que estava errado era a **causa atribuída**: anular a seção
> **não** acende "Pontos de ligação 3D" — testado no Builder, a peça seguiu em "Não". Quem
> acende é `PECA.CONEXAO_VOLUMETRICA`, ver ADR-023. Leia a seção "Por quê" abaixo como o
> registro de uma hipótese que caiu, não como explicação do rótulo.

## Decisão

Toda peça que recebe `ENTRADA_PECA` sai com `PECA.SECAO` e `PECA.DIAMETRO_INTERNO` **nulas**. Quem
faz isso é `bim_pipeline.aq.entradas_aq.marcar_pontos_de_ligacao`, chamada de dentro do `gravar` — logo
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
nas entradas (`SECAO_EP`, `DIAMETRO_EP`). Nenhum dos dois escritores nomeava as colunas, então o
*default* 10 do schema entrava sozinho.

~~Que anular as duas **acenda** o "Sim" é hipótese até o próximo teste no Builder.~~ **Caiu:** o
teste no Builder manteve o rótulo em "Não" numa biblioteca de conexões com entrada em todas as
peças. A correlação de 1.441/1.441 era real e continua sendo — mas era correlação entre duas
consequências de uma mesma causa (a peça ligar por pontos), não a causa do rótulo. Lição de
método: correlação perfeita numa amostra grande **não** distingue causa de irmã-de-causa; foi a
documentação do Builder, e não mais medição, que separou as duas.

## Consequências

- Arquivo já entregue se conserta sem repetir importação: `preencher_entradas_aq` agora varre todas
  as peças com entrada, inclusive num `.aq` que **já** tinha entradas (antes ele pulava a simbologia
  já preenchida e não chegava na seção).
- `validar_aq` ganhou a conferência 9 (pontos de ligação): peça com entrada sem seção no cadastro, e
  nenhuma `ENTRADA_PECA` órfã.
- O rótulo continuou em "Não" depois disto, e o caminho não foi o experimento subtrativo previsto
  aqui: foi a ajuda do Builder, que nomeia a propriedade e diz que ela é alternativa à propriedade
  *Entradas* (ADR-023).
- A seção que a peça perde não se perde: `SECAO_EP` = 10 em toda entrada que escrevemos, que é o
  valor das entradas com geometria na nativa de conexões.
