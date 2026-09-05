# Diagnóstico rápido — sintoma → causa provável

> Movido do `CLAUDE.md` em 2026-09-04 (S7.8, item I22 da auditoria). O conteúdo é o que estava lá,
> com as afirmações desatualizadas de I23 corrigidas no lugar; onde diz "este arquivo", "acima" ou
> "no histórico", leia-se o `CLAUDE.md` antigo — o histórico está em `docs/sessoes/`. **Manter aqui**
> a partir de agora: o `CLAUDE.md` só aponta para este arquivo.

| Sintoma | Causa provável |
|---|---|
| Uma peça isolada, "solta no ar", sem mudar a contagem de triângulos | Rotação do OQ3D lida como row-major — ela é column-major |
| Parafusos/detalhes faltando, ~30% menos triângulos que o IFC | Instâncias `TQi3DReusedObject` por referência não resolvidas |
| Peças separadas por metros | resolve_lp() não acumula hierarquia recursivamente |
| Fragmentos a 5–16m do corpo | LP aberrante no IFC exportado — filtrar outliers |
| Modelo ~1000× maior | Conversão mm→m desnecessária — verificar magnitude das coordenadas brutas |
| Modelo cinza (tem cores no IFC) | build_face_color_map() não chamado, ou IFCINDEXEDCOLOURMAP não encontrado |
| 0 cores do IFCCOLOURRGBLIST | Regex espera inteiros mas floats têm casas decimais |
| `col[]` presente mas Three.js ignora | Material sem `vertexColors: true` ou `color` não é 0xffffff |
| `import * as THREE from 'three'` falha | importmap ausente ou fora de ordem no HTML |
| Canvas não encontrado no init | Módulo rodou antes de 'cards-rendered' — verificar handshake |
| GPU trava | Loop de animação em todos os cards — thumbnail estática + loop só no click |
| ZIP vazio de geo files | IFCs não foram parseados — verificar output/geo/ após o build |
| .aq não abre como SQLite | Tentar abrir como ZIP; se falhar: arquivo corrompido. Caminho inexistente é `FileNotFoundError` explícito desde S7.4 |
| Chip de filtro não filtra e o console só erra ao clicar ("Invalid or unexpected token") | Nome de série com `"` (Komeco `1" x 1"`, Maxbar `"T" Horizontal`) em `data-filter`/`onclick` sem escape — **corrigido em S7.4**: `autoescape=True` e handler lê `this.dataset.filter`. Se voltar, alguém desligou o autoescape |
| `build.py` falhou mas o shell viu exit 0 | Até S7.4 `run_all` e `main` nunca chamavam `sys.exit(1)`. Hoje: catálogo sem produto e qualquer falha no `--all` saem com 1 e "gerados" conta builds, não ZIPs |
| Texto com lixo (`5U \x96 19\x94`) | Texto lido como `latin-1` ou UTF-8 — o `.aq` é **cp1252** (ver "Encoding é cp1252, não latin-1") |
| Peça existe como `.IFC` na pasta mas não sai no catálogo | Desde 2026-09-05 (I6) o build lê só o `.aq`: a peça precisa estar cadastrada nele, ou entra pela POC (`ifc_to_geo.py`). As linhas antigas sobre `file_map`/`scan_input` saíram com o modo `--ifc` |
| Nome do produto é só dimensão ("100mm") | Esperado para catálogos flat no .aq — build.py prefixa com GRUPO_PECA automaticamente |
| Fabricante/título stale do catálogo anterior | aq_stale não estava resetando titulo/slug — fix em commit 5e38b65; deletar config.json corrompido se necessário |
| `Fabricante []` sem sugestão | BIBLIOTECA vazia no .aq e pasta avô é genérica — peek_aq tenta pasta avô, depois filename |
| Título sugerido ruim (ex: `"Esgoto Sn Sr"`) | Pasta pai do .aq é genérica (`input/`, `.`) — organizar como `input/Fabricante/Nome da Linha/pecas.aq` |
| Slug com acento (`inc-ndio`) | slugify não normalizava unicode — corrigido com NFD + strip combining marks (commit 8b4272a) |
| Slug mostra valor antigo do config.json | ec.get('slug') tomava precedência sobre titulo atual — removido; slug sempre = slugify(titulo) (commit fbbf292) |
| **Fabricante vazio na página publicada** | `PECA.BIBLIOTECA` está vazia em todas as bibliotecas reais vistas (12+) — usar o prefixo de `CLASSE_SIMBOLOGIA_3D.NOME_CLASSE` |
| **Título vira o nome do fabricante** | Pasta pai é o fabricante (`input/Intelbras/pecas_Intelbras_*.aq`) — comparar o slug da pasta com o 1º token do arquivo antes de usá-la como título |
| **Título em forma de slug** na página | Derivado do filename sem limpeza — remover ruído (`pecas`, anos, versões), preservar siglas (CFTV, PPCI) e separar CamelCase |
| **Título colado** (`"Barramentoblindado"`) | Filename com palavra composta toda-minúscula (ex: `pecas_maxbar_barramentoblindado.aq`) — CamelCase split não actua, token fica capitalizado só na 1ª letra. Fix (commit ec42af2): token único todo-minúsculo > 10 chars é ignorado; a cascata cai para `linhas` do banco, que devolve `'Barramento Blindado'`. Organizar o filename como `barramento_blindado.aq` ou `BarramentoBlindado.aq` evita o problema. |
| Nome do produto redundante (`Pontos de comando Interruptor…`) | Prefixo do grupo aplicado sem necessidade — prefixar só quando o nome é ambíguo, decidindo **por grupo** |
| **Preview 404 em `data/*.json`, erro `Unexpected token 'T'`** | Template usava `./data/`; com `cleanUrls` a página é servida em `/<slug>` sem barra final e o relativo vai para a raiz. Usar caminho absoluto `'/' + CATALOG.slug + '/data/'`. O `'T'` é a página 404 da Vercel ("The page…") caindo no `JSON.parse` |
| **Thumbs 404 na Vercel** | Mesmo root cause de `data/`: `./thumbs/` resolvia para `/thumbs/` (raiz). Corrigido em 2026-09-02 — `THUMB_BASE = '/' + CATALOG.slug + '/thumbs/'` nos dois layouts |
| Preview gigante (centenas de MB) | Faltou `dedup()` no caminho `.aq` — reduz ~79% dos vértices |
| ZIPs entrando no commit | `output/*.zip` não cobre subpastas; a saída é aninhada — usar `output/**/*.zip` |
| Joelhos e curvas retos no viewer | Transforms do OQ3D ignorados — usar o parser de árvore de `oq3d.py` |
| Peças 100× maiores/menores | OQ3D é **centímetros**; multiplicar por 0.01 |
| Menos produtos que peças no banco | Peças sem `PECA_SIMBOLOGIA_3D` são tubos e kits — sem forma fixa, pular é o correto |
| Parafusos faltando / um solto no ar | Instâncias `TQi3DReusedObject` por referência — **resolvido em 2026-08-30 (S5.1)**; se voltar, ver `oq3d.md`, "Instâncias repetidas" |
| Miniatura chapada, sem relevo, diferente do viewer | Está saindo do rasterizador software — o caminho de produção é `www/tools/thumb-rasterizer.ts` (Playwright). Confira com `grep chromium.launch www/tools/thumb-rasterizer.ts` |
| Thumb leva ~2 s cada e o import estoura o tempo | Geometria passada como **objeto** para `page.evaluate` — passar como string JSON e dar `JSON.parse` dentro da página (6×) |
| Worker de thumbs não sai / Chromium órfão | Faltou `await closeThumbRenderer()` antes do `process.exit()` — o handle do servidor HTTP prende o event loop |
| Thumb regenerada não aparece no browser | ETag de `/thumbs/:productId` deriva só do `thumbKey` e o `Cache-Control` é `immutable` — hard reload |
| `pnpm thumb:regen <id>` ignora o importId | `sh -c 'cmd' arg` faz `arg` virar `$0` — o script precisa de `"$@"` e um `--` de placeholder (corrigido em 2026-08-30) |
| WebGL não inicializa em headless | Faltam os flags SwiftShader — obrigatórios em WSL/CI/container; sem eles **todas** as geometrias falham de uma vez |
| Query com `WHERE NOME_x = 'algo acentuado'` volta vazia, sem erro | O texto no `.aq` é cp1252 e o `sqlite3` vincula `str` como UTF-8 — usar `CAST(? AS TEXT)` com `.encode('cp1252')` |
| Diâmetro do mapa vale ~2× o esperado, ou vem `-1.8e308` | `PECA.DIAMETRO_PECA` é um **código**, não centímetro, e `-DBL_MAX` é sentinela. A chave é `diametro_codigo` desde 2026-09-02 e já filtra a sentinela |
| `no such column: DIAMETRO` em `ENTRADA_3D` | Coluna só existe no schema 607; as bibliotecas 552–582 não a têm |
| `.aq` gerado abre e valida, mas os nomes saem como `SoldÃ¡vel` | Texto gravado em UTF-8 — o AltoQi grava **cp1252**; usar `CAST(? AS TEXT)` com bytes cp1252 |
| `.aq` gerado publica com o título errado (ex.: "Saida") | O título vem da pasta pai do `.aq`, e `saida`/`output` não estão em `_GENERIC_DIRS` (`build.py:922`) — pôr o `.aq` numa pasta com nome descritivo |
| `.aq` sem geometria publica com fabricante vindo do nome da pasta | Sem `CLASSE_SIMBOLOGIA_3D` o passo 1 da cascata não existe e `PECA.BIBLIOTECA` está vazio nas 12 bibliotecas reais — preencher `PECA.BIBLIOTECA` ao gerar |
| Sólido gerado mostra o interior por uma emenda | Perfil de revolução que fecha em si mesmo sem soldar o último anel no primeiro: `2 × lados` arestas de borda |
| Peça gerada com partes soltas ou flutuando | Malhas corretas em posição relativa errada — não aparece em bbox, contagem nem round-trip; conferir abrindo o preview |
| Sobrou um `.aq` de 0 byte onde não havia arquivo | `sqlite3.connect()` **cria** o arquivo num caminho inexistente. **Corrigido em S7.4**: `open_aq` checa `isfile` e abre em `mode=ro` (URI com `pathname2url`); `peek_metadata` deixa `FileNotFoundError` subir. Esta linha existiu desde 2026-09-02 sem o código ser corrigido — a tabela não substitui o fix |
| API em `Retrying (n)...` eterno, sem responder request nenhum | Não conecta no Mongo. A mensagem do Mongoose culpa o whitelist, mas é texto fixo — meça DNS, TCP, TLS e auth separadamente (ver "A API não sobe e o Mongoose culpa o whitelist") |
| `tlsv1 alert internal error` / `SSL alert number 80` nos 3 nós, com o TCP abrindo | **IP não liberado no Atlas** (ou cluster M0 pausado). O handshake morre antes da autenticação, então não é credencial. Liberar em *Network Access*; a API reconecta sozinha no próximo retry |
| Página pública `404` e `/empresas/minha` `404` com a API saudável | A base está **vazia** (foi assim entre 2026-09-02 e 03). Ver "Estado" no topo e a receita de re-importar pela API |
| `PUT /geometrias/:id` devolve `413 Payload Too Large` | Limite do body JSON — o padrão do express é 100 KB. `main.ts` sobe para `JSON_BODY_LIMIT` (300 MB) com `bodyParser: false` + `useBodyParser` |
| Editor mostra centenas de partes numa peça de conexão | Normal: cada malha do OQ3D vira ≥1 componente; use **fundir** ou **re-segmentar** depois de mover. Na Dancor são 11–58 por bomba |
| Parte com milhares de "arestas de borda" na Dancor | Não é defeito do editor: a malha do fabricante é sopa de triângulos (25–32% das arestas). O alarme vale para malha gerada/importada, que deve dar 0 |
| `tests/test_editor_roundtrips.py` passou a falhar sem ninguém mexer no código | O teste usa a **primeira** geometria de `www/storage/bim/geo/` em ordem alfabética — importar uma biblioteca nova na POC muda a fixture. Se a falha é na conferência do IFC com "sem par", é erro real (desde S7.9 a métrica pareia a ≤ 2 µm; antes acusava fronteira de arredondamento a 10 µm) |
| Depois de salvar geometria, a miniatura do card não muda | Esperado na POC de edição — thumb não é regenerada (pendência). O viewer 3D já mostra o novo, porque a ETag deriva de tamanho+mtime |
| Mensagem "salvo" some no mesmo instante | `useEffect` que reseta o formulário dependia de `editadoEm` e rodava logo após o save — a dependência tem de ser só o `_id` do produto |
| IFC exportado abre com a geometria em dobro | A montagem recebeu Representation — o `parse_ifc.py` processa `IFCELEMENTASSEMBLY` e `IFCBUILDINGELEMENTPROXY`; só as proxies podem ter malha |
| IFC exportado: `parse_ifc.py` ignora um face set | Entidade quebrada em várias linhas — `build_entity_index` casa `#id=TIPO(args);` **por linha** |
| IFC exportado: parte rotacionada fora do lugar | Axis/RefDirection do `IFCAXIS2PLACEMENT3D` montados sem converter os eixos — é `Axis = C·coluna_Y`, `RefDirection = C·coluna_X`, com `C: (x,y,z)→(x,−z,y)` |
| `step_to_geo.py` morre com `Segmentation fault` | Referência morta da binding OCP: documento XCAF liberado com rótulos em uso, ou `ex.Current()` guardado após `Next()`. Manter `doc`/`reader`/sequência vivos; copiar com `TopoDS.Solid_s()`; `python3 -X faulthandler` mostra a linha |
| `POST /step/importar` → 500 "step_to_geo.py falhou: No module named 'OCP'" | OpenCASCADE não instalado para o Python que a API chama — `pip install --user --break-system-packages cadquery-ocp` (PEP 668 exige a flag no Ubuntu) |
| STEP importado 1000× maior ou deitado | Faltou `×0,001` (o OCC entrega mm) ou a troca `(x, z, −y)` — o script já faz os dois; conferir se a geometria veio de outro caminho |
| `.aq` exportado publica com título estranho (ex.: "scratchpad") | `peek_aq` infere o título da pasta pai — pôr o arquivo em `input/<Fabricante>/<Linha>/` antes do `build.py` |
| `validar_aq.py` falha só em "barras de tubo com 600 cm" | Regra específica do catálogo da Akato; um `.aq` de peça única gerado pelo `geo_to_aq.py` não tem tubo — as outras 19 checagens é que valem |
| IFC importado no editor 1000× maior ou 1000× menor | `ifc_to_geo.py` escala ×0,001 só com `.MILLI.` declarado **e** bbox bruta > 50. Um IFC em mm de peça pequena (< 50 mm) não dispara — importar e aplicar ×0,001 no editor ("escala global") |
| `/cad/importar` de um IFC devolve "não extraiu geometria" | Arquivo B-rep (`IFCADVANCEDBREP`) sem `ifcopenshell` no Python da API, ou IFC só com curvas — `python3 -c "import ifcopenshell"` |
| **"Failed to fetch" / "fetch error" ao importar CAD grande, e nada no log da API** | A requisição nunca terminou: conversão de minutos contra timeout de 300 s. Desde `eb60843` a importação é assíncrona (202 + `GET /cad/importacoes/:id`); se voltar a acontecer, a API está fora ou o `requestTimeout` foi reduzido |
| IFC grande importado sai todo cinza | Caminho `ifcopenshell`: `style.diffuse.r()` é método no 0.8 — `_rgb_do_material` trata os dois casos; se ainda assim cinza, o arquivo não tem `IfcSurfaceStyle` (Revit exporta material só com a opção de cores) |
| Importação fica em `parseando` por minutos | Normal para B-rep facetado grande: 124 MB → 221 s e 3,6 GB de RAM. Acompanhe em `/importar-step` ou `GET /cad/importacoes/:id`; `falhou` traz o erro do Python |
