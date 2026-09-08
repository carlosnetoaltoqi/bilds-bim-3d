# ADR-020 — a `IMAGEM` da simbologia 3D é obrigatória, e o pipeline a rasteriza em software

**Status:** Aceita (2026-09-08)

## Decisão

Todo `.aq` escrito pelo projeto grava `SIMBOLOGIA_3D.IMAGEM`: um BMP 100×100 de 24 bits (30.054
bytes, o layout das bibliotecas nativas), rasterizado da própria malha por
`bim_pipeline.aq.imagem_aq.render(malhas)` — o mesmo argumento que `oq3d_writer.escrever(malhas)`
recebe. Vale para os dois caminhos de escrita: `geo_to_aq` (uma peça) e `catalogo_to_aq` (catálogo
inteiro). O `validar_aq` falha quando alguma simbologia está sem `IMAGEM` ou com um BMP fora desse
formato. Bibliotecas exportadas antes disto se corrigem com
`ferramentas.preencher_imagem_aq`, que rasteriza a partir do OQ3D que já está no arquivo.

O rasterizador é **software puro em numpy**, e não o harness de miniaturas
(`bim_pipeline.miniaturas`, Chromium + Three.js).

## Por quê

Sem a `IMAGEM` o AltoQi Builder **não desenha a peça** — nem no ambiente 3D, nem na planta. A peça
aparece no Cadastro com nome, código, descrição e propriedades, e sem forma nenhuma, com o OQ3D
íntegro ao lado. As quatro bibliotecas exportadas em 2026-09-08 (conexões, dois pacotes de famílias
Revit, um projeto `.rvt`) saíram todas assim, com megabytes de geometria válida invisível.

O campo foi isolado por experimento no Builder, comparando uma nativa que funciona com uma nossa:
apagar só a `IMAGEM` (mantendo o `WIREFRAME`) faz a peça parar de desenhar; apagar só o `WIREFRAME`
(mantendo a `IMAGEM`) não. Transplantar uma geometria nativa para o nosso cadastro desenha, o que
absolve `PECA`/`GRUPO_PECA` e mostrou que `ENTRADA_PECA`/`ENTRADA_3D` também não são necessárias. A
tabela completa está em `docs/conhecimento/aq-formato.md`. Nas 16 bibliotecas nativas medidas a
`IMAGEM` está preenchida em praticamente toda simbologia — era a única diferença sistemática entre
elas e as nossas.

Por que em software e não pelo harness de miniaturas: a `IMAGEM` é requisito do formato do arquivo,
tem de sair no mesmo processo que escreve o `.aq` e no CI, onde não há navegador; e a ~2 s de
Chromium por peça um pacote de 1.399 simbologias não fecha (em numpy são 42 s para as 1.399).

## Consequências

- O `.aq` cresce ~30 KB por simbologia distinta (1.399 simbologias ≈ 42 MB de preview) — o preço de
  o arquivo ser utilizável.
- A imagem do Builder e a do site passam a ter fontes diferentes (rasterizador próprio × harness
  Three.js). São propósitos diferentes: 100×100 num diálogo de cadastro e a miniatura do catálogo
  web. Se algum dia a diferença visual incomodar, o caminho é alimentar `imagem_aq` com o PNG do
  harness quando ele existir — não trocar o rasterizador.
- `WIREFRAME` e `ENTRADA_PECA`/`ENTRADA_3D` seguem fora de escopo, agora com prova de que a peça
  desenha sem eles. Falta prova em planta/corte (o `WIREFRAME` é o que o CAD desenha lá) e da
  conectividade da peça numa rede.
- A aceitação de `.aq` passa a exigir **peça lançada no projeto**, não só a biblioteca aberta: foi
  exatamente o passo que faltava para o defeito ter sido visto antes (`docs/aceitacao.md` §4).
