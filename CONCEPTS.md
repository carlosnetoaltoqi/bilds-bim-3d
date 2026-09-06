# Concepts

Vocabulário do projeto — entidades, processos com nome e estados que têm significado próprio aqui.
Glossário, não especificação: cada entrada aponta para o documento de `docs/conhecimento/` que a
explica. Nenhum nome de fabricante ou de arquivo da POC (ADR-016).

---

## Arquitetura (docs/arquitetura.md)

### Biblioteca
O pacote Python `bim_pipeline` (`biblioteca/`). Stateless: arquivo entra, arquivo ou JSON sai. Não
conhece Mongo, HTTP nem caminhos do repositório. Todo contexto consome as mesmas funções dela — por
CLI (`python -m bim_pipeline.cli.<nome>`), nunca por import de fora.

### Contexto
Uma responsabilidade de negócio com deployable próprio em `servicos/`: **criador de catálogos**
(importar e publicar), **API de catálogo** (ler), **editor de peças** (editar), **gerador de ZIP**
(`.aq` → ZIP da bilds.com), **conversores** (CAD ↔ geometria ↔ `.aq`). Cada um leva consigo só o que
precisa ao ser portado (docs/arquitetura.md §4).

### Stateless
Um serviço que não lê nem grava Mongo nem storage: `gerador-zip` e `conversores`. Sobem sem
`MONGODB_URI`; upload e resultado são temporários. Regra 3 das fronteiras.

### Contrato
JSON Schema em `biblioteca/bim_pipeline/contratos/` para o que cruza a fronteira biblioteca ↔ serviço
(`catalogo`, `geometria`, `manifesto-catalogo-aq`, `resumo-miniaturas`, `info-plugin`). A biblioteca
prova em teste que emite conforme; `@bim/base` valida o que lê. ADR-015.

### Fixture por papel
Um arquivo real usado por testes, referenciado pelo **papel** (`aq_pequena`, `aq_grande`,
`aq_malha_v3`, `step_peca`, `iges_pasta`, `dll_plugin`, `manifesto_plugin`) em
`tests/fixtures.local.json` (gitignored), nunca pelo nome do fabricante. Sem o arquivo o teste pula.

### Termos efêmeros
Fabricantes, domínios e diretórios da POC que não podem aparecer em código, contratos, conhecimento
ou skills (`tests/arquitetura/termos_efemeros.txt`). Só em `docs/historico/`, `docs/integracoes/` e
fixtures locais. ADR-016.

---

## Formato `.aq` e OQ3D (docs/conhecimento/aq-formato.md, oq3d.md)

### OQ3D
Formato binário proprietário do AltoQi para a malha 3D de uma peça — o BLOB `SIMBOLOGIA_3D.SIMBOLOGIA_3D`
do `.aq`. Árvore serializada estilo Delphi com malhas, cores e transformações, em centímetros Z-up.
É a razão de o projeto não precisar de IFC. Leitor `bim_pipeline.aq.oq3d`, escritor `oq3d_writer`.

### Simbologia 3D
A linha da tabela `SIMBOLOGIA_3D` que carrega um OQ3D. Várias peças podem apontar para a mesma
(`PECA_SIMBOLOGIA_3D`): é a origem da **geometria compartilhada** e do copy-on-write no editor.

### Código de diâmetro
O número em `PECA.DIAMETRO_PECA`, `ENTRADA_PECA.DIAMETRO_EP` e `ENTRADA_3D.DIAMETRO`. **Não é medida**:
é um índice na escala de diâmetros nominais do AltoQi (8 = 40 mm, 9 = 50 mm, 10 = 60 mm, 11 = 75 mm,
12 = 100 mm, 14 = 150 mm, 15 = 200 mm). Chamar de "diâmetro em cm" foi o erro que esta entrada
existe para evitar.

### Sentinela
O valor que o AltoQi grava no lugar de `NULL`: `-2147483647` em coluna inteira, `-1.7976931348623157e+308`
(`-DBL_MAX`) em coluna real. Não é `NULL` para o SQL — `IS NULL` não acha, e aritmética produz lixo.

### cp1252
O encoding real do texto de um `.aq`, embora o SQLite declare UTF-8. Ler como latin-1 só falha em
0x80–0x9F — onde vivem travessão, aspas curvas e reticências — e falha em silêncio. Ler e escrever
sempre em cp1252, estrito.

---

## Geometria (docs/conhecimento/geometria.md)

### `{pos, col, idx}`
O contrato de geometria do viewer: posições em metros, Y-up, 3 floats por vértice; cor RGB 0–1 por
vértice (ou vazia); índices de triângulo. Tudo o que a biblioteca produz e todo viewer consome.

### Dedup
Quantização float32 de posição **e cor** como chave de vértice. Reduz ~80 % dos vértices e, como a
cor está na chave, triângulos de cores diferentes nunca compartilham vértice — o que permite ao
editor re-segmentar uma malha em **Partes**. Não solda costuras de malha de fabricante.

### Bocal
Marcador de ponto de conexão do AltoQi dentro da geometria (cores fixas verde e azuis). Não é
produto: fica fora do bbox e vira `marker` no editor.

### Forma representativa
Malha gerada por parâmetro quando o fabricante não publica cota: diâmetro nominal (dado), espessura
de parede (norma), o resto inventado com a regra explícita. Serve para visualizar e contar, não para
conferir encaixe. A ressalva vai gravada dentro do arquivo. (`docs/conhecimento/formas-representativas.md`)

### Arestas de borda
Arestas com um só triângulo. Em malha de fabricante são normais (um quarto a um terço das arestas);
só são alarme em sólidos gerados ou costurados, que devem dar zero.

---

## Catálogo e edição (docs/conhecimento/catalogo-modelo.md)

### Import
Uma execução do criador de catálogos que transforma um `.aq`, uma peça CAD ou um plugin web num
catálogo publicado. Máquina de estados `recebido → parseando → gravando → publicado | vazio | falhou`.
`falhou` obriga a limpar o que gravou; `vazio` é resultado válido (biblioteca só de tubos/kits).

### Ponteiro de geometria
`geoKey` e `thumbKey` no documento do produto — o **único** acoplamento entre Mongo e arquivos
(`geo/<importId>/<stem>.json`, `thumbs/<importId>/<stem>.webp`). Ninguém resolve caminho fora do
`IGeometryStore`.

### GeometryStore
A interface (`put/get/stat/delete/deleteByPrefix`) por onde toda geometria, miniatura e logo entra
e sai do storage. Disco na POC; é a costura para S3.

### Copy-on-write
Primeira edição da geometria de um produto que **compartilha** simbologia: o produto ganha um arquivo
só dele (`geo/<importId>/<productId>.json`) e guarda a chave compartilhada em `geoKeyCompartilhada`;
os irmãos não mudam. Geometria exclusiva ganha `.orig.json`. Restaurar desfaz os dois casos.

### Original preservado
`<id>.orig.json` da geometria exclusiva na primeira escrita, e `infoOriginal` para as informações:
"voltar" é copiar de volta.

### Parte
Unidade de edição no editor 3D: `{pos, col, idx, matrix, visible, marker}`, nascida da re-segmentação
da malha em componentes conexos (funciona porque o dedup separa cores). Parte oculta não é salva.

### Bake
Aplicar as matrizes das partes visíveis, concatenar, arredondar a 1 µm e deduplicar com a mesma
quantização do import. É o que salvar, exportar IFC e exportar `.aq` fazem antes de escrever.

---

## Processos e serviços (docs/conhecimento/processos-filhos.md, servicos-web.md)

### Filho que morre com o pai
Toda CLI da biblioteca e o `thumbs.mjs` recebem o `stdin` em pipe e saem com código 2 no EOF
(`--sair-com-stdin`). Um `kill -9` no serviço não deixa Python nem Chromium órfãos.

### Fila
Uma importação por vez (concorrência configurável) numa fila em memória; as demais esperam em
`recebido` com a posição no `note`. A vaga só libera depois das miniaturas. Pressupõe uma instância;
a **recuperação no boot** marca `falhou` o que ficou aberto e apaga uploads temporários.

### Harness
`harness.html` + `thumbs.mjs`: a mesma cena do viewer aberta num Chromium headless para renderizar
uma miniatura por geometria. Servido por `http://` local porque módulos ES não vivem em `file://`.

### SwiftShader
O rasterizador em software do Chromium: sem ele o WebGL não inicializa em headless sem GPU.

### customUrl
O identificador legível de uma empresa (`/<customUrl>/<slug>`). Empresa é agrupador de catálogos,
não controle de acesso (ADR-007).

### Layouts
`series-rows` (famílias com variantes e curva Q-H) e `catalog-grid` (itens heterogêneos com filtros).
Inferidos do `.aq` (`docs/conhecimento/inferencia.md`).

### Curva Q-H
Vazão × altura manométrica de uma bomba, lida do `.aq` (`ITEM_CURVA_BOMBA`) e desenhada em SVG na
página; sua presença decide o layout.
