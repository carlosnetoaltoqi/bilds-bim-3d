# Histórico das skills

Trilha de versões e correções das skills de `docs/skills/`, arquivada em 2026-09-06. A skill leva só a versão
atual e o how-to; o que cada versão corrigiu está aqui, para consulta pontual.

## leitor-biblioteca-aq (versão atual 2.10.0)

**2.10.0** — 2026-09-06 — reescrita como how-to; o conhecimento técnico foi para `docs/conhecimento/aq-formato.md`, `aq-escrita.md`, `oq3d.md`, `geometria.md` e `inferencia.md`; removidas as seções obsoletas `build_product_map` e "Como o find_aq_product cruza IFC → .aq" (o modo `--ifc` do build foi removido em 2026-09-05); sem nomes de fabricantes (ADR-016).

**2.9.1** — O `.aq` de 854 peças gerado pela receita "catálogo inteiro" (uma biblioteca de conexões real exportada) foi aberto no AltoQi Builder pelo usuário e funcionou — primeira prova no Builder de geometria OQ3D reescrita em escala. Ressalvas de "não visto no Builder" ajustadas.

**2.9.0** — Regras que só aparecem ao escrever N peças: uma simbologia por geometria distinta (não por peça), uma propriedade por chave (não por peça), `NOME_PECA` sem o nome do grupo, códigos IFC do grupo inferidos do nome quando faltam os originais, bomba identificada pela curva Q-H, colunas de peça com 3D como o fabricante grava. Conferido com uma biblioteca de conexões real inteira: 854 peças, 448 simbologias, nomes e geometria iguais aos originais.

**2.8.1** — `build_product_map`/`find_aq_product` marcados como históricos: o modo `--ifc` do build foi removido em 2026-09-05; o matcher ficou fora do caminho padrão.

**2.8.0** — Malha OQ3D **versão 3** (uma biblioteca de barramentos): mesmo layout da versão 2, aceita em `MESH_VERSOES`. Corrige a explicação das divergências de contagem de raízes: parte era esse bug — e perdia a geometria inteira —, e uma fração menor era um caractere fora do padrão dentro de um double. Contrato de erro do parser explicitado (truncado → `OQ3DError`; layout desconhecido → pulado + `OQ3DAvisoParse`), e a regra de mostrar o aviso por simbologia no resumo do build. Coberto por teste.

**2.7.0** — Registro de que o `.aq` gerado pela receita "Escrever um `.aq`" **abre no AltoQi Builder**: propriedades personalizadas e acentos corretos, colunas no `DEFAULT` aceitas. Antes a skill só afirmava compatibilidade com o próprio leitor. Fica explícito o que ainda não foi visto no Builder (render OQ3D, lançamento em rede).

**2.6.0** — `open_aq` do exemplo corrigido: `isfile` antes de conectar e abertura em `mode=ro` via URI (com `pathname2url`, porque os caminhos reais têm espaço e acento). O `peek_metadata` deixa `FileNotFoundError` subir. A armadilha já estava na tabela desde a 2.3.0 e o código do projeto continuou com o bug por um tempo — lição para quem lê esta skill: a tabela de armadilhas descreve o sintoma, não garante que o código ao lado já o evite.

**2.5.0** — Nova subseção "Um `.aq` mínimo a partir de qualquer malha": a lista de tabelas que uma peça só exige, uma raiz OQ3D por malha de cor uniforme (dividir por cor antes de escrever), a conversão de unidades do viewer, o enquadramento inofensivo (conexão, sem código de diâmetro), a origem gravada em propriedade, e a armadilha do título vindo da pasta. Verificado com um STEP tesselado relido pelo leitor do projeto.

**2.4.0** — Três aprendizados de quem **edita** a geometria depois de extraída (uma prova de conceito de edição de geometria, em branch própria do projeto): a estrutura de partes perdida no `{pos,col,idx}` se recupera por componentes conexos porque o `dedup` carrega a cor na chave; a tesselação de fabricante não é estanque (25–32% de arestas de borda numa biblioteca real), então esse critério só vale para malha gerada; e arredondar a 1 µm antes do dedup corta o JSON pela metade sem perder triângulo. Seção "Publicar num viewer web: armadilhas".

**2.3.0** — **`DIAMETRO_PECA` é um CÓDIGO de diâmetro, não centímetro** — a 2.2.0 dizia "diâmetro nominal (cm)" e estava errado: numa biblioteca de conexões real `50 mm` → 9 e `100 mm` → 12, e na maioria das peças o valor é a sentinela `-DBL_MAX` — nenhuma conexão traz código. Documentadas também as duas sentinelas de "não definido" (`-2147483647` e `-DBL_MAX`), o mecanismo por trás da armadilha de encoding (o `.aq` **declara** UTF-8 e **guarda** cp1252, e o SQLite não valida) e a consequência para quem consulta: **literal acentuado dentro do SQL também precisa ir em cp1252**, senão a query volta vazia sem erro. Nova seção "Escrever um `.aq`" — `CAST(? AS TEXT)` com bytes cp1252, ordem de inserção das FKs, os enums de `PROJETO_APLICACAO`/`ENTIDADE_IFC`/`SUBTIPO_IFC`/`TIPO_APLICACAO_PECA` com os valores observados, `ITEM.CODIGO_ITEM` como lugar do código comercial, e as armadilhas de escrever OQ3D. Documentado o cabeçalho OQ3D (37 bytes, com o número de objetos-raiz num offset fixo) — esse campo serve de verificação de parse e expôs um defeito do leitor tolerante: numa fração das geometrias de fabricante ele conta raízes a mais. Validado gerando uma biblioteca completa a partir de um catálogo em PDF — 262 peças, lidas de volta por este leitor sem ressalvas.

**2.2.0** — Resolvidas as duas armadilhas que deslocavam geometria. (a) A referência de instância repetida é o **índice de serialização base 1 sobre todos os objetos em ordem de documento**, com discriminador após o GUID — o GUID é único por instância e nunca foi a chave. (b) A rotação é **column-major**, não row-major. Conferido contra o IFC numa biblioteca real: conjunto de pontos idêntico, milhares de triângulos batendo exatamente numa peça de referência. Adicionadas as armadilhas de comparação com IFC (alinhar pelo canto da bbox, comparar por tolerância, bbox não distingue rotação de transposta).

**2.1.0** — **Correção de encoding: o `.aq` é cp1252, não latin-1.** A versão anterior afirmava "latin-1 (Windows-1252)" tratando os dois como sinônimo. Diferem na faixa 0x80–0x9F, onde estão travessão, aspas curvas e reticências — nomes de produto chegavam quebrados em produção sem nunca lançar exceção. Documentado também por que trocar o `text_factory` exige `CAST(col AS BLOB)` nas colunas binárias: o latin-1 era byte-preserving e o round-trip `.encode('latin-1')` do BLOB de geometria não sobrevive à troca. Verificado com hash SHA-256 dos blobs antes e depois, e zero bytes de controle nos nomes de mais de mil peças em nove bibliotecas.

**2.0.0** — Formato OQ3D documentado e validado em nove bibliotecas, seis versões de schema e três domínios: o `.aq` dispensa os IFCs para gerar 3D com forma, cor e miniatura. Adicionados: tabelas de geometria, vínculo determinístico peça → malha, cascata de inferência de fabricante/título, regra de prefixo por grupo, armadilhas do parser binário, análise de cobertura e armadilhas de publicação web.

**1.1.0** — Extração de peças, curvas Q-H e propriedades personalizadas.

## leitor-ifc (versão atual 1.9.0)

**1.9.0** — 2026-09-06 — reescrita como how-to; o conhecimento técnico foi para `docs/conhecimento/ifc.md`, `geometria.md`, `aq-formato.md` e `servicos-web.md`; removida a seção `FILE_MAP` (o script de referência tomava argumentos fixos por dicionário; o CLI atual recebe o arquivo de entrada direto); sem nomes de fabricantes (ADR-016).

**1.8.1** — Correção da armadilha "igualdade de conjunto arredondado": comparar conjuntos a 10 µm e tolerar uma fração na fronteira era o erro, não a solução — numa malha de 44 mil vértices a fração chega a 2,2% com desvio real de 1,4 µm. Agora: par por vizinho mais próximo a ≤ 2 µm (tolerância derivada dos 6 decimais do `REAL`), nos dois sentidos, zero sem par, exit 1 e autoteste sabotado. Os "14 µm" citados na 1.6.0 eram artefato dessa comparação.

**1.8.0** — Subseção "Arquivo grande": quando o parser manual não escala e como usar o `ifcopenshell.geom.iterator` como caminho rápido (cor por material com `r()/g()/b()` como métodos, metros já convertidos, degenerados descartados, dedup em numpy, um produto só não paraleliza, conversão fora da requisição HTTP). Medido num IFC de projeto de 124 MB: 760.038 △ em 221 s, 3,6 GB.

**1.7.0** — Nova seção "O parser como biblioteca — IFC entrando num editor": o que falta ao `parse_ifc_file` para servir de entrada (dedup, unidade decidida pela declaração **e** pela magnitude, nomes via `ifcopenshell`) e a conferência por round-trip com o exportador da 1.6.0.

**1.6.0** — Nova seção "Escrever IFC que este parser lê": as regras para gerar IFC4 a partir de um `{pos,col,idx}` (uma entidade por linha, montagem sem Representation, METRE coerente, eixos `(x,−z,y)`, placement rígido vs escala assada, REAL sem expoente, mapa de cor 1-based + `IFCSTYLEDITEM`, `Closed` honesto, strings `\X2\`, propriedades). Cada uma é uma armadilha deste documento vista pelo lado de quem escreve. Conferido com o próprio `parse_ifc.py` (mesmos triângulos, 14 µm) e `ifcopenshell.validate` (0 erros).

**1.5.0** — Nova seção "O IFC como gabarito": como reconstruir a geometria de um arquivo tessellated direto do STEP (sem tesselador, exato) e usá-la para validar o parser de outro formato. Quatro armadilhas de comparação, todas encontradas na prática: bbox não distingue rotação de transposta, centróide não serve de âncora quando um lado solda vértices e o outro não, igualdade de conjunto arredondado falha na fronteira, e o `ifcopenshell` descarta degenerados (50 triângulos a menos que o STEP numa peça real).

**1.4.0** — Aviso no início: se a origem for uma biblioteca AltoQi, o `.aq` traz a mesma geometria e é muito mais rápido de ler (ver `leitor-biblioteca-aq`). Listados os casos em que o IFC continua sendo a fonte certa.

**1.3.1** — Bug do `IFCMAPPEDITEM`: falta um nível de indireção até o face set.

**1.3.0** — Cinco bugs de parsing STEP documentados com suas correções.

## leitor-step (versão atual 1.2.0)

**1.0.0** — Criada em 2026-09-03 a partir da importação de uma peça CAD real (Autodesk
Inventor, AP214, mm) no editor 3D do projeto: receita XCAF completa, as duas
armadilhas de referência morta (documento e explorer) que deram segfault na primeira
versão, unidade/eixos/sentido, e a conferência por round-trip pelos parsers do projeto.

**1.1.0** — 2026-09-05: IGES. Dez arquivos de um catálogo de conexões real (SolidWorks,
faces soltas) tesselados pelo conversor do projeto: costura, sólido, orientação pelo volume
assinado, cores por face preservadas depois da costura; teste com uma caixa escrita pelo
próprio OCC.

**1.2.0** — 2026-09-06 — reescrita como how-to; o conhecimento técnico foi para
`docs/conhecimento/step-iges.md`, `geometria.md`, `ifc.md`, `aq-escrita.md` e
`servicos-web.md`; removida a rota `POST /step/importar` (não existe mais: a conversão é
`POST /tesselar` de `servicos/conversores`, e uma peça CAD vira produto de catálogo por
`POST /importacoes` do criador de catálogos); sem nomes de fabricantes (ADR-016).

## pagina-biblioteca (versão atual 1.8.0)

**1.8.0** — 2026-09-06 — reescrita como how-to; o conhecimento técnico foi para `docs/conhecimento/miniaturas.md`, `geometria.md`, `catalogo-modelo.md` e `processos-filhos.md`; removida a cor de marca fixa dos exemplos de card — os tokens visuais são do consumidor da skill; sem nomes de fabricantes (ADR-016).

**1.7.0** — Jinja2 passa a ser obrigatório no gerador: o "fallback" sem Jinja2 entregava a página
com `{% for %}` cru e nenhum card, e o chamador ignorava o `False`. Regra nova na seção de chips:
sem o motor de template, falhe alto antes de escrever qualquer arquivo (bilds-bim-3d, I7, 2026-09-04).

**1.6.0** — Nomes de série com aspas (`1" x 1"`, `"T" Horizontal`) quebravam os chips de
filtro em 6 catálogos gerados pelo `bilds-bim-3d`: atributo truncado, `onclick` com erro de
sintaxe, e nenhum aviso no build. Corrigido com `autoescape=True` no Jinja2 e handler que
lê `this.dataset.filter`. Verificado com Playwright clicando o chip nas duas variantes de
layout. Nova subseção em "catalog-grid" e linha na tabela de armadilhas.

**1.5.0** — Duas armadilhas de **verificação** de página gerada, ambas encontradas ao
conferir um catálogo de 262 peças. (a) O `/vendor/` do importmap é root-relative: mover o
diretório do catálogo quebra o import sem erro no console, e o card fica em branco igual a
"geometria não chegou" — quem realoca tem de levar o `vendor/` como irmão e servir esse
nível como raiz. (b) **Não confira o render lendo pixel com `readPixels`**: o renderer da
página não usa `preserveDrawingBuffer`, então a leitura volta zerada mesmo com a peça na
tela — reportou 0 de 263 canvas pintados numa página em que as 262 peças estavam
visíveis. Conferir por screenshot e olhar a imagem.

**1.4.0** — **O mesmo harness serve build e servidor de aplicação.** Extrair a função que
toca WebGL (`renderThumbFromData`, recebe a geometria em memória) e deixar a versão por URL
como wrapper permite que um backend gere as miniaturas com o mesmo código do build.
Documentada a armadilha que dominava o tempo — passar a geometria como **objeto** para
`page.evaluate` custa 6× mais que passar como string JSON (2 200 ms × 370 ms por
miniatura), porque o serializador do Playwright anda o grafo. Também: singleton de browser
com fechamento explícito antes do `process.exit()`, a exigência de `http://` (o importmap
não sobrevive a `file://`), a medição que mostra que r170 × r185 é indiferente (PSNR 71 dB),
e a armadilha de cache ao regenerar miniatura na mesma URL. Números novos para a decisão
"não rasterize em código": 27 dB do rasterizador software × 47 dB do harness.

**1.3.0** — **Pré-renderizar as miniaturas no build.** O shared renderer da 1.2.0 conserta
o estouro de contexto WebGL, não o carregamento: medido em produção, o elemento LCP era a
própria miniatura, com 39,9 s e 7.230 ms de render delay, e a geometria respondia por 57%
do peso da página. Documentado o padrão de dirigir o próprio template num Chromium
headless (Playwright) para obter imagem idêntica ao runtime, os flags de SwiftShader
obrigatórios sem GPU, a regra de uma miniatura por geometria, o `object-fit: contain` que
a proporção fixa exige, e a necessidade de manter o render dinâmico como fallback.

**1.2.0** — Shared renderer + captura JPEG para catálogos grandes (o padrão de um renderer por card estoura o limite de contextos WebGL). Caminho absoluto para a geometria, obrigatório com `cleanUrls`. Checagem de `r.ok` antes do `JSON.parse`. Cache de geometria por URL, já que peças diferentes compartilham malha. Validado em produção com 9 catálogos, o maior com 856 produtos.

**1.1.0** — Padrões de card, modal, curva Q-H em SVG e os dois layouts de catálogo.
