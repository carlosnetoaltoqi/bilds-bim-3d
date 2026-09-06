# 01 — O plugin TupyCAD para AutoCAD e o catálogo web que ele abre

**Pergunta da missão (S7.17, 2026-09-05):** o plugin de AutoCAD da Tupy (TupyCAD, plataforma
Catallog) pode virar uma biblioteca `.aq` do AltoQi Builder? Onde está a geometria, em que
formato, e o que é preciso para o bilds-bim-3d importá-la como catálogo?

**Resposta curta:** a DLL não tem geometria nenhuma — é uma casca de 35 KB que abre um catálogo
web. A geometria 3D de cada produto é um **IGES** exportado do SolidWorks (faces soltas, sem
sólido), servido pelo catálogo depois de um formulário de captura de lead. O OpenCASCADE que já
tessela STEP no projeto lê IGES; costurando as faces em sólido e orientando pelo volume, o
resultado entra no pipeline como qualquer STEP e sai em `.aq` pelo `catalogo_to_aq.py`. Feito e
validado com 10 peças de 10 famílias TupyGrooved (`saida/Tupy-TupyGrooved.aq`, 8,3 MB).

---

## 1. Onde o plugin foi instalado e o que ele é

```
C:\Program Files\Autodesk\ApplicationPlugins\TupyCAD.bundle\
├── PackageContents.xml        AppVersion 2.0.0, Catallog Software Ltda, SeriesMin R19 SeriesMax R25
├── TupyCAD.dll                35 KB — PE32 .NET (v4.0.30319), "TupyCAD Menu", LoadOnAutoCADStartup
├── Newtonsoft.Json.dll        711 KB — a única dependência
├── TupyCAD - Instalacao do plugin.pdf   NETLOAD manual
└── uninstall.exe / uninstall.log        registra também Software\Catallog\Tupy\Electronic Catalog
```

`.bundle` em `ApplicationPlugins` é o formato padrão de autoload do AutoCAD — nada mais é
configurado. O atalho "Catálogo Eletrônico Tupy" no desktop é um `.URL` para
`https://hidraulica.tupy.com.br/`.

**Strings da DLL** (UTF-16, heap `#US` do .NET — `strings -el`; sem descompilar):

| String | O que revela |
|---|---|
| `https://tupycad.catallog.digital` / `…/pt/home` | `PLUGIN_HOST`: a paleta do AutoCAD é um navegador com este site |
| `InsertBlockFromURL`, `RequestDownload`, `GetPluginVersion` + `JavaScriptCallbackAttribute` | os três callbacks que a página web chama no plugin |
| `\temp.dxf`, `DxfIn`, `blockName`, `blockHandle`, `CATALLOG_COMPONENT_UUID` | inserir bloco = baixar um DXF para `%TEMP%`, `DXFIN`, gravar o uuid do produto num atributo |
| `TUPYCAD_LIST`/`TUPYCAD_QUOTE`, "Listar"/"Quantificar" (pt/en/es) | os dois comandos da ribbon: listar blocos inseridos, montar cotação |
| `Acdbmgd`, `acmgd`, `accoremgd`, `RibbonTab`, `PaletteSet` | API .NET do AutoCAD; nenhuma geometria, nenhum arquivo embutido |

Conclusão: **não há biblioteca dentro da DLL para decodificar.** O que ela "instala" é um atalho
para o catálogo web da Catallog.

## 2. O catálogo web (plataforma Catallog / Collabo)

Next.js estático + API REST **pública, sem autenticação**, em `/api/marketplace/`. O mesmo
catálogo da Tupy vive em dois hosts com conteúdos diferentes: `tupycad.catallog.digital` (o da
DLL; TupyGrooved com 10 grupos) e `conexoes.tupy.com.br` (18 grupos em TupyGrooved, 846 produtos
no total, ~3.700 arquivos). A API foi levantada com `curl` e com o Chromium do projeto
(Playwright) gravando a rede da SPA.

| Endpoint | Devolve |
|---|---|
| `GET /api/marketplace/v1/settings/?_lang=pt` | título, `forms.download` (uuid do formulário), `enableCADIntegration` |
| `GET /api/marketplace/v2/categories/?product_type=group` | categorias (TupyBSP, TupyNPT Alta/Média Pressão, TupyPres, TupyGrooved, TupyForged) |
| `GET /api/marketplace/v2/products/?category_slugs=<cat>&product_type=group&fields=…` | **grupos** (famílias: CURVA 90, TÊ, CRUZETA…; `code` TG90, TG130…) |
| `GET /api/marketplace/v2/products/<slug>/?product_type=group` | detalhe do grupo: `resources` (o `.rfa` Revit da família), `components` (os produtos = tamanhos), `attributes` (Acabamento, Classe de pressão, Diâmetro nominal) |
| `GET /api/marketplace/v1/products/<slug>/resources/` | arquivos do produto: `type_key` `.igs`, `.dxf`, `.rfa`, `.zip`; `size_in_bytes`; `form_uuid` |
| `GET /api/marketplace/v2/products/<slug>/?product_type=product&fields=…` | nome, `code` (9 dígitos), `attributes` (Tamanho imperial/métrico, Cód. Barras, Peso…), `details` (HTML com as seções Aplicações, **Dimensionais** (tabela), Material, Normas, Rosca…) |
| `GET /api/marketplace/v1/resources/?limit=500` | todos os arquivos do site: 4.000 → 2.796 DXF, 928 IGS, 187 ZIP, 89 RFA |

Rotas que **não** existem (404): `/products/<uuid>/`, `/resources/<uuid>/` (é por slug),
`/resources/<slug>/download/`. A lista de rotas do front está nos chunks JS (`grep 'api/marketplace'`).

### 2.1 O download — formulário de lead

Clicar num arquivo abre um modal "Download" com **Nome, E-mail, Telefone, Empresa, Cargo** (todos
obrigatórios; `GET /api/crm/v1/form/<uuid>/` dá a definição). O envio é:

```
POST /api/crm/v1/form/
{ "form_id": "<forms.download>", "resource_uuid": "<resource.id>", "origin": "component-file-download",
  "fields": { "full_name", "email", "mobile", "company", "position" },
  "page_name": "…", "page_url": "https://…/pt/product/<slug>", "component_uuid": "<produto.id>" }
→ { "url": "https://conexoes.tupy.com.br/media/brands/tupy/resources/<uuid>/1/Cruzeta_4.igs" }
```

e então `GET url`. **Armadilha:** o navegador omite `binary_file_id` (é `undefined`); mandar
`null` dá `400 {"message":"BinaryFile matching query does not exist."}`. Usuário logado pula o
formulário (`isLoggedIn`); o site guarda os dados em `localStorage.downloadFormData` e reenvia a
cada arquivo — é o que o `catallog.py` faz, com os dados de quem importa.

No AutoCAD (`isInACAD()`), o item `.dxf` vira um botão que chama `ACADInsertBlockFromURL` com a
mesma `url` — o plugin baixa e insere; os `.igs` seguem o download normal.

### 2.2 Termos de Uso — por que o escopo é 18 grupos e não o catálogo

`/pt/use-terms` (Collabo, 2021-03-01): proíbe "venda, locação ou qualquer outro meio de
comercialização de dados", "formas alternativas de distribuição das informações", "descompilar,
realizar engenharia reversa ou desmontar o software" e "criar obras derivadas". Por isso a sessão
parou antes de qualquer download e perguntou; o usuário autorizou **só a categoria TupyGrooved
(18 grupos)**, com **os dados reais dele** no formulário, como empresa parceira em estudo
([[feedback: escopo autorizado]] — registro em `docs/sessoes/S7.17-plugin-autocad-tupy.md`). O
`catallog.py` deixa isso escrito na docstring; o botão do web pede os dados de quem importa e
os manda só ao catálogo do fabricante. Uso comercial dos dados exige acordo com a Tupy.

## 3. Os arquivos: IGES, RFA, DXF

**22 arquivos, 39 MB**, em `downloads/<código grupo> <nome>/` (gitignored; `manifesto.json` com
SHA-256 e URL de cada um). Dos 18 grupos: 11 têm `.rfa` de família, 10 têm pelo menos um produto
com `.igs`, **7 não expõem arquivo nenhum** (ACOPLAMENTO FLEXÍVEL/REDUÇÃO/RÍGIDO, FLANGE GROOVE
TG321A, NIPLE TRANSIÇÃO, TÊ MECÂNICO GROOVED, TÊ SAÍDA SPK) e TÊ REDUÇÃO só tem `.rfa`.

### 3.1 IGES (SolidWorks 2017) — a geometria 3D

Cabeçalho: `SolidWorks IGES file using analytic representation for surfaces`, unidade `2HMM`,
autor `alan.martins`, 2021-10. **Zero sólidos, zero cascas: N faces soltas** (tipo 144,
superfície aparada), 160 a 639 por peça. Lidas cruas, as normais não têm sentido consistente — o
volume assinado da malha sai **negativo** em 8 dos 10 (o viewer mostraria a peça escura).

O que resolveu, medido nos 10 (`step_to_geo.py`, IGES desde a S7.17):

| Passo | Efeito |
|---|---|
| `IGESCAFControl_Reader` com `SetColorMode` | lê faces e cores (SolidWorks grava cor por face: cinza 0,06, vermelho Tupy (1,0,0), azul-acinzentado (0,59/0,64/0,85)) |
| `BRepBuilderAPI_Sewing(0.01 mm)` sobre todas as faces | 1 casca em 8 peças; 6 cascas nas montagens (acoplamento angular, tê mecânico) |
| `BRepBuilderAPI_MakeSolid` + `ShapeFix_Solid` | sólido por casca; volume B-rep bate com o da malha (±1 %) |
| **volume assinado < 0 → `Reverse()`** | o TAMPÃO fica com 10 arestas livres (casca não fecha) e o `ShapeFix_Solid` não inverte — o volume decide |
| cor por face preservada via `Sewing.Modified(face)` | as faces novas não estão no documento XCAF; sem o mapa a peça cairia no cinza padrão |

Resultado: 10 sólidos com volume positivo (66 a 463 cm³), 6.294 a 65.800 triângulos a 0,2 mm
(a rosca do adaptador e o flange são os pesados), 3 a 22 s cada. Arestas livres residuais: 1
(adaptador), 2 (acoplamento), 4 (tê mecânico), 10 (tampão) — anotadas no catálogo como aviso.
O `test_step_to_geo.py` fixa o contrato com uma caixa escrita pelo próprio OpenCASCADE.

### 3.2 RFA (Revit 2017) — família paramétrica, geometria proprietária

Documento OLE2 (`D0CF11E0`): `BasicFileInfo` (UTF-16: "Autodesk Revit 2017", caminho original
`C:\coisas_do_alan\…\TupyGrooved 2020\…`), **`PartAtom`** (XML Atom, legível: título da família,
categoria Revit "Conexões de tubo", OmniClass 23.60.30.11.14 Pipework Fittings, e um `A:part`
por tipo — DN32…DN200, ou 50X40…100X80 nas reduções), `RevitPreview4.0` (PNG), `Partitions/30`
(a geometria, binário proprietário — **não há leitor fora do Revit**). O que se aproveita, via
`rfa_partatom.py`: a lista de tipos vira a spec "Tipos Revit" da peça e o título "Família Revit".
Curiosidades dos dados: o `.rfa` de ACOPLAMENTO ANGULAR chama-se "Acoplamento Rigido"; o do TÊ
MECÂNICO RF é "TÊ SAÍDA SPK"/"Tê Mecânico NPT"; o TAMPÃO tem bbox 457 mm (dois corpos lado a lado).

### 3.3 DXF — só 2D

`Pacote DXF` = três vistas (frontal, lateral, superior) por produto; é o que o plugin insere no
AutoCAD. Sem uso para o `.aq` (a simbologia 2D do AltoQi ficou fora do escopo).

## 4. Do IGES ao `.aq` — e a validação

`tupy_catalogo.py` → `catallog.catalogo_de_downloads` (IGES → `geo/<código>.json`, specs) →
manifesto → `catalogo_to_aq.py` → **`Tupy-TupyGrooved.aq`: 10 peças, 10 grupos, 10 simbologias,
306.557 triângulos, 18 propriedades, 104 valores, 8,3 MB em 1,7 s.**

Ida e volta pelos leitores do projeto (`catalogo_de_aq.py`): 10 produtos, **as 10 geometrias com
o mesmo número de triângulos**, diag zerado, `peek_metadata` → Tupy / TupyGrooved / 10 grupos,
`PRAGMA foreign_key_check` vazio. Os grupos recebem classificação IFC pelo nome
(`aq_writer.classificar_grupo`: CURVA → curva, TÊ → tê, CRUZETA, REDUÇÃO, TAMPÃO/CAP → cap,
FLANGE, ADAPTADOR/ACOPLAMENTO → luva/conexão). `NOME_PECA` sem o prefixo da série
('CURVA 45 TG120 4 (114) UL/FM' → 'TG120 4 (114) UL/FM'), `ITEM.CODIGO_ITEM` = código Tupy.
Uma peculiaridade: a inferência de título ao reimportar tira o fabricante do nome e o catálogo
aparece como "Grooved" — é o `inferencia.py`, não o `.aq`.

**Não foi aberto no AltoQi Builder nesta sessão** (o usuário não testou ainda) — é o próximo passo
de aceitação, como foi feito com a Amanco na S7.16.

## 5. O que foi para o produto

- `www/apps/ingestao/pipeline/step_to_geo.py` — IGES (`.igs/.iges`), costura, orientação pelo volume, `formato`, `volume_cm3`, `costurado`, `arestas_livres`.
- `www/apps/ingestao/pipeline/catallog.py` — `inspecionar` (DLL → host/plugin/versão/categorias) e `importar` (categoria → downloads + geometrias + catálogo no JSON do `catalogo_de_aq.py`).
- `www/apps/ingestao/pipeline/rfa_partatom.py` — o que se lê de um `.rfa` sem o Revit.
- Serviço: `POST /importacoes/plugin-autocad/inspecionar`, `POST /importacoes/plugin-autocad` (tipo `plugin`, downloads em `storage/catallog/<importId>/`, mesmo `processarCatalogo` da biblioteca `.aq`); web: botão **"Importar plugin do AutoCAD"** → `/importar/plugin`; `.igs` aceito em "Importar peça" e em `/cad`.
- Testes: `tests/test_step_to_geo.py`, `tests/test_catallog.py`, `ImportarPluginDto` no harness de validação.

## 6. Ferramentas deste diretório

| Script | Faz |
|---|---|
| `tools/tupy_baixar.py --lead dados/lead.local.json [--so-listar]` | plano por grupo e download idempotente para `downloads/` (CLI fina sobre `catallog.py`) |
| `tools/tupy_catalogo.py` | `downloads/` → `saida/geo/`, `saida/catalogo.json`, `saida/manifesto-aq.json`, `saida/Tupy-TupyGrooved.aq` |
| `python3 www/apps/ingestao/pipeline/rfa_partatom.py downloads/*/*.rfa` | `.partatom.json` + `.preview.png` ao lado de cada `.rfa` |

`dados/` guarda os JSONs públicos levantados (grupos e produtos de TupyGrooved, settings, o
formulário) e `lead.local.json` (gitignored). `downloads/` e `saida/` são gitignored e regeráveis.
