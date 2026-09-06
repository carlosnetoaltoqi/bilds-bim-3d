# Plugin de CAD como casca de um catálogo web (`bim_pipeline.catalogo.fontes.plugin_catalogo_web`)

> O padrão, generalizável a qualquer plugin de CAD que siga a mesma forma; fabricante, produto e
> domínios do caso estudado não aparecem aqui (ADR-016).

## O padrão

Um plugin de CAD de fabricante — o botão que aparece na ribbon do AutoCAD, do Revit, do
SolidWorks para "inserir peça do catálogo" — pode ser, inteiro, uma DLL .NET de **dezenas de
KB, sem geometria nenhuma**. A DLL não é a biblioteca; é a casca que abre, numa paleta do CAD,
a página de um catálogo web do fabricante. Toda a geometria, toda a especificação e todo o
download vivem do lado do servidor; o plugin só integra esse site ao CAD (inserir bloco,
listar o que foi inserido, montar cotação).

Isso muda a pergunta de engenharia reversa: não é "como decodificar esta DLL", é "que
catálogo web ela abre, e o que dá para baixar dele programaticamente".

## Detecção — sem descompilar

A DLL é um executável PE32 .NET (assinatura `MZ`, referências a `mscorlib`/`.NET`). As
strings literais de um assembly .NET ficam no heap `#US`, em **UTF-16LE** — `strings -el`
(ou um regex sobre pares `(byte, 0x00)`) as extrai sem descompilar nada. Duas buscas bastam:

- **`https://`** — o(s) host(s) que a DLL conhece. Um deles é o catálogo que a paleta abre.
- **os nomes dos três callbacks JavaScript** que a página web chama de volta no plugin — algo
  como "inserir bloco a partir de uma URL", "pedir download" e "versão do plugin". A presença
  desses três símbolos é a assinatura do padrão: a paleta é, literalmente, um navegador
  embutido, e o contrato entre o site e o plugin é essas três chamadas.

Outras strings do mesmo heap (nome de comandos da ribbon, nome do arquivo temporário que
recebe o bloco inserido, atributo onde o plugin grava o identificador do produto) descrevem o
comportamento do lado CAD, mas não têm geometria — confirmam que não há nada para decodificar
além do host.

### Mais de um host

Uma DLL pode trazer mais de uma URL nas strings: o host que a instalação local abre por
padrão, e outro host (às vezes do mesmo fabricante, com mais categorias ou mais produtos)
achado por outro caminho. A escolha não deve depender do nome do fabricante — isso não
escala para o próximo plugin. O módulo mantém uma lista de **domínios de plataformas de
catálogo web já vistas** (`PLATAFORMAS_CONHECIDAS`, uma constante/dado configurável, não uma
lista de fabricantes) e prefere, entre os hosts encontrados, o que bate nela; sem
correspondência, usa o primeiro. Plataforma ≠ fabricante: é o protocolo que este módulo fala,
e vários fabricantes diferentes podem publicar seu catálogo na mesma plataforma.

## A API do catálogo — papéis, não caminhos de uma plataforma específica

O catálogo observado é uma SPA com uma API REST **pública, sem autenticação**. A forma geral,
que deve se repetir em plataformas parecidas, é uma cadeia de granularidade crescente:

1. **Settings** — título do catálogo e o identificador do formulário de download.
2. **Categorias** — o nível mais alto de navegação.
3. **Grupos** (famílias) dentro de uma categoria — cada grupo é uma família de produto
   (por exemplo, todas as curvas de 90°), com os atributos que variam entre os tamanhos.
4. **Produto** — um tamanho/variante dentro do grupo: código comercial, atributos
   dimensionais, HTML de detalhe (com uma tabela dimensional).
5. **Recursos** de um produto ou de um grupo — a lista de arquivos disponíveis (3D, 2D,
   família paramétrica), cada um com tipo, tamanho declarado em bytes e o identificador que o
   formulário de download precisa.

Uma rota "lista todos os recursos do site" costuma existir e é o jeito mais rápido de saber
quantos arquivos de cada tipo o catálogo tem antes de decidir o que baixar.

## A geometria: 3D em IGES, família em `.rfa`, 2D em DXF

Por produto, o catálogo serve tipicamente:

- **3D em IGES** — export de um CAD paramétrico (SolidWorks, no caso observado), quase sempre
  como **faces soltas** (sem sólido, sem casca): a costura, a orientação por volume assinado
  e o resto do tratamento estão em `docs/conhecimento/step-iges.md` — este documento não
  repete aquele.
- **Família paramétrica do CAD de BIM** (`.rfa` do Revit, no caso observado) — geometria
  proprietária; o que se aproveita dela está descrito abaixo.
- **2D em DXF** — vistas (frontal/lateral/superior), o que o próprio plugin insere no CAD de
  origem. Sem uso para uma biblioteca 3D; fica fora do escopo deste módulo por padrão.

## O download está atrás de um formulário de lead

Não existe link direto para o arquivo. O fluxo observado:

```
POST <endpoint de formulário do CRM do catálogo>
     { form_id, resource_uuid, fields: {nome, e-mail, telefone, empresa, cargo}, page_url, … }
→ { "url": "<URL assinada e temporária do arquivo>" }
GET <url>
```

**Armadilha:** o corpo do formulário tem um campo que o navegador simplesmente omite quando
não tem valor (`binary_file_id`); mandar `null` explícito faz o servidor procurar um registro
inexistente e responder **HTTP 400**. O jeito certo é não enviar o campo.

O **lead nunca é persistido** por este módulo: os dados de quem está importando (nome,
e-mail, telefone, empresa, cargo) ficam num JSON temporário, usados uma vez por arquivo como o
navegador faria, e apagados ao fim da importação — nunca gravados em banco.

## Termos de Uso — autorização de escopo antes do download em lote

Um catálogo assim normalmente publica Termos de Uso que **proíbem redistribuição**,
comercialização dos dados e engenharia reversa do site. Baixar em lote programaticamente é
justamente o tipo de uso que esses termos miram. Por isso a regra é: **antes de baixar mais
que um punhado de arquivos de teste, obter autorização explícita de escopo** — que categoria,
que grupos, com que finalidade — e registrar essa autorização. O código não decide isso
sozinho; o escopo autorizado fica registrado pelo operador em `docs/historico/`, não neste
documento nem no código.

## Download idempotente

O download de uma categoria grava, ao lado dos arquivos, um `manifesto.json` com grupo,
produto, tipo de arquivo, tamanho, SHA-256 e a URL de cada um. Reexecutar a importação pula o
que já está em disco (confere pelo identificador do recurso e pela presença do arquivo) — uma
importação interrompida retoma de onde parou, e uma DLL/categoria já processada não refaz
nenhum download.

## O que se lê de um `.rfa` sem o Revit

O `.rfa` é um documento **OLE2** (a mesma casca binária do `.doc` antigo). Sem o Revit
instalado, três streams são legíveis com uma biblioteca OLE2 genérica:

- **`PartAtom`** — XML no formato Atom da Autodesk: título da família, categoria Revit,
  classificação OmniClass, os parâmetros da família e **uma entrada por tipo/tamanho**
  (DN32, DN40, … ou as combinações de uma redução) com descrição, modelo e fabricante. É a
  tabela de variações da família — a única parte do `.rfa` que vira dado útil.
- **`BasicFileInfo`** — texto UTF-16 com a versão do Revit que gravou o arquivo e o caminho
  original no disco de quem o criou.
- **preview** — um PNG pequeno de pré-visualização, embutido como stream.

O que **não** dá para ler: a geometria em si, num stream de nome numérico (`Partitions/<n>`)
em formato binário proprietário da Autodesk — não há leitor fora do próprio Revit. Por isso a
malha 3D de uma peça vem do IGES, nunca do `.rfa`; o `.rfa` só contribui especificação.

## Specs derivadas: a tabela dimensional e os "Tipos Revit"

O HTML de detalhe de um produto costuma trazer uma tabela dimensional com **cabeçalho de duas
linhas usando `colspan`/`rowspan`** (uma coluna "Diâmetro nominal" cobrindo "Polegada" e "mm",
por exemplo). Extrair essa tabela exige expandir o cabeçalho antes de casar dado com rótulo —
a mesma classe de problema que `pdf-catalogo.md` resolve para tabela em PDF, aqui aplicada a
HTML: célula que atravessa todas as linhas do cabeçalho é uma coluna; as demais cedem lugar às
células `colspan` da linha de baixo.

A lista de tipos lida do `PartAtom` vira a spec **"Tipos Revit"** de cada peça (e o nome da
família, "Família Revit"), ao lado do que vem da API do produto (código, atributos,
material, normas, rosca).

## A saída: o mesmo JSON de catálogo que o `.aq` produz

Este módulo não inventa um formato próprio. A saída de uma importação é **exatamente o
dict que `catalogo_de_aq.py` também devolve** — `{config, catalog, n_geometrias, diag, hints}`,
conforme o contrato `catalogo` (`biblioteca/bim_pipeline/contratos/catalogo.schema.json`) — com
`hints.schema = 'plugin-web'` marcando a origem e `hints.origem` guardando host, categoria,
contagem de arquivos/bytes e tempo de tesselação. É por isso que o serviço de ingestão publica
um plugin de CAD pelo **mesmo caminho** que publica um `.aq` — nenhuma rota nova de publicação,
o mesmo `processarCatalogo`.

Um grupo (família) sem nenhum IGES baixado — porque o fabricante simplesmente não publicou
arquivo 3D para aquela família — **fica fora do catálogo gerado**, e o diagnóstico (`diag.avisos`)
lista quantos e quais grupos foram deixados de fora, para quem importa saber que a família
existe mas não teve peça.

## Onde está no código

- `biblioteca/bim_pipeline/catalogo/fontes/plugin_catalogo_web.py` — `inspecionar_dll`
  (strings UTF-16 → host/plugin/versão), `CatalogoWeb` (settings/categorias/grupos/produto/
  recursos), `planejar`/`baixar_plano` (manifesto idempotente), `secoes_details`/`tabela`
  (HTML → specs, cabeçalho `colspan`/`rowspan`), `catalogo_de_downloads` (IGES → catálogo no
  contrato `catalogo`), `importar`.
- `biblioteca/bim_pipeline/conversores/rfa_partatom.py` — leitura do `.rfa` sem Revit
  (`PartAtom`, `BasicFileInfo`, preview).
- `biblioteca/bim_pipeline/conversores/step_iges.py` — IGES → malha (costura, orientação por
  volume); ver `docs/conhecimento/step-iges.md`.
- `biblioteca/bim_pipeline/contratos/info-plugin.schema.json` — o que `inspecionar` devolve;
  `catalogo.schema.json` — o que `importar` devolve.
- CLI: `python3 -m bim_pipeline.cli.plugin_catalogo_web inspecionar|importar`.
- Serviços: `POST /plugin/inspecionar` (conversores — só a DLL, sem gravar nada, contrato
  `info-plugin`) e `POST /importacoes/plugin-autocad` (criador de catálogos — DLL + categoria
  + dados do formulário → uma importação `plugin` na fila, o lead só existe no processo, nunca
  no banco).
- Testes: `tests/biblioteca/test_plugin_catalogo_web.py`.

## Ver também

- `docs/conhecimento/step-iges.md` — costura de faces soltas e orientação por volume, que
  este documento não repete.
- `docs/conhecimento/pdf-catalogo.md` — a mesma classe de problema (tabela com cabeçalho
  multilinha) resolvido para PDF em vez de HTML.
- `docs/conhecimento/aq-formato.md` — o contrato `catalogo` que este módulo também emite.
- `CONCEPTS.md` — verbetes "Import" e "Forma representativa".
