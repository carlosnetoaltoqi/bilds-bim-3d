# Roteiro de aceitação — os serviços de pé

O que a suíte automatizada não cobre (ela não sobe Mongo nem os serviços): o sistema inteiro
funcionando pela fronteira HTTP, cada contexto no seu papel. Roda em poucos minutos com `curl` e
Python; o operador confere o que cada passo imprime. Pré-requisitos: `.env` na raiz com Mongo e
`STORAGE_PATH`; `pnpm install && pnpm build:pacotes`; uma biblioteca `.aq` real (papel `aq_pequena`
de `tests/fixtures.local.json`) e um `.stp` (papel `step_peca`).

```bash
pnpm dev                                   # cinco serviços + web
for p in 4000 4100 4200 4300 4400; do curl -s localhost:$p/health; echo; done
```
Esperado: cinco `{"status":"ok",…}`. Os com dados dizem `mongo`/`conexao: conectado`; os stateless
(`gerador-zip`, `conversores`) só dizem onde está a `biblioteca`.

## 1. Criador de catálogos — importar e publicar

```bash
AQ="<caminho do aq_pequena>"; EMP=<customUrl de uma empresa existente, ou crie: curl -F name=Teste -F customUrl=teste localhost:4000/empresas>
R=$(curl -s -F "file=@$AQ" -F "empresa=$EMP" localhost:4100/importacoes); echo $R      # 202 {importId, tipo:'aq', status:'recebido'}
ID=$(echo $R | python3 -c 'import json,sys;print(json.load(sys.stdin)["importId"])')
watch -n 3 "curl -s localhost:4100/importacoes/$ID | python3 -m json.tool | grep -E 'status|note|productCount|thumbCount'"
```
Esperado: `recebido → parseando → gravando → publicado`; `productCount` igual ao número de peças com
geometria; `thumbCount` preenchido depois (as miniaturas rodam ainda na vaga da fila); `note` sem `AVISO`
para a fixture pequena. Falha esperada: um arquivo que não é `.aq` → `400`; extensão errada é recusada
antes de entrar na fila.

## 2. API de catálogo — a página lê

```bash
curl -s localhost:4000/empresas/$EMP/catalogos | python3 -m json.tool | head -20
SLUG=<slug do catálogo acima>
curl -s localhost:4000/catalogos/$EMP/$SLUG | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["title"], len(d["products"]), d["products"][0])'
PID=<_id de um produto>
curl -s -o /dev/null -w "%{http_code} %{size_download} bytes\n" localhost:4000/geometrias/$PID
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" localhost:4000/thumbs/$PID
```
Esperado: 200 e o JSON `{pos,col,idx}`; miniatura `image/webp`. No browser, `http://localhost:3000/$EMP/$SLUG`
mostra os cards com miniatura e o modal com o viewer 3D.

## 3. Editor de peças — copy-on-write e miniatura regerada pelo criador

Escolha dois produtos que compartilham geometria (mesmo `geoKey` em `GET /produtos/:id`) — numa biblioteca
de conexões há muitos. `A` será editado; `B` é o irmão.

```bash
curl -s localhost:4000/geometrias/$A > a.json
python3 -c 'import json;g=json.load(open("a.json"));g["pos"]=[x*1.5 for x in g["pos"]];json.dump(g,open("a2.json","w"))'
curl -s -X PUT -H 'content-type: application/json' --data-binary @a2.json localhost:4400/geometrias/$A | python3 -m json.tool
```
Esperado: `copiaFeita: true`, `geoKey` novo (`geo/<importId>/<A>.json`), `geoKeyCompartilhada` com a chave
antiga, `miniatura: "regerando"`. Confira: `GET /geometrias/$B` **não mudou**; `GET localhost:4400/geometrias/$A/original`
é igual ao irmão; alguns segundos depois `GET /produtos/$A` tem `thumbAtualizadaEm` preenchido e `thumbErro: null`.

```bash
curl -s -X PATCH -H 'content-type: application/json' -d '{"nome":"Peça editada"}' localhost:4400/produtos/$A | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["nome"], d["infoOriginal"])'
curl -s -X POST localhost:4400/geometrias/$A/restaurar | python3 -m json.tool
```
Esperado: `infoOriginal` guardado na primeira edição; `restaurado: true` e o `geoKey` volta ao compartilhado.
Com o criador **parado**, o `PUT` ainda grava, mas responde `miniatura: "nao-solicitada"` e o produto ganha `thumbErro`.

## 4. Exportar o catálogo salvo como `.aq`

```bash
CAT=<id do catálogo>
curl -s -D h.txt -o exportado.aq localhost:4100/exportar/catalogo/$CAT; grep -i "x-aq-resumo\|content-disposition" h.txt
python3 -m bim_pipeline.cli.ferramentas.validar_aq exportado.aq
```
Esperado: 200, `pecas_<Fabricante>_<Titulo>.aq`, resumo no header; o validador lê o arquivo sem `FALHA`.
Aceitação final é abrir o `.aq` no AltoQi Builder (passo manual).

## 5. Gerador de ZIP — stateless

```bash
env -u MONGODB_URI -u MONGODB_DB pnpm dev:zip &          # sobe sem banco
curl -s -D h.txt -o saida.zip -F "file=@$AQ" localhost:4200/zip; grep -i "HTTP/1.1 200\|content-disposition" h.txt
python3 -c 'import zipfile,json;z=zipfile.ZipFile("saida.zip");m=json.loads(z.read("manifest.json"));print(m["productCount"], m["thumbCount"], sorted({n.split("/")[0] for n in z.namelist()}))'
ls /tmp/zip-* 2>/dev/null || echo "tmp limpo"
```
Esperado: 200, `<nome>-bilds.zip`, `manifest.json` + `catalog.json` + `geo/` + `thumbs/`, `thumbCount ==`
geometrias; nada fica em `/tmp`. Este é o mesmo ZIP que se sobe no dashboard da bilds.com
(`docs/integracoes/bilds-com.md`).

## 6. Conversores — stateless

```bash
curl -s -F "file=@<step_peca>" -F deflexao=0.5 localhost:4300/tesselar | python3 -c 'import json,sys;g=json.load(sys.stdin);print(g["formato"], g["unidade"], g["bbox_mm"], len(g["idx"])//3, "triângulos")'
curl -s -D h.txt -o peca.aq -H 'content-type: application/json' -d '{"info":{"fabricante":"Fabricante","nome":"Peça"},"pos":[0,0,0,0.1,0,0,0,0.1,0],"col":[1,0,0,1,0,0,1,0,0],"idx":[0,1,2]}' localhost:4300/aq; grep -i "HTTP/1.1\|x-aq-resumo" h.txt
```
Esperado: bbox igual ao do CAD em mm, triângulos > 0; `.aq` com `X-Aq-Resumo`. Com a DLL de um plugin de CAD
(papel `dll_plugin`): `curl -F file=@<dll> localhost:4300/plugin/inspecionar` → `host`, `plugin`, `versao`,
`categorias[]`. Sem OpenCASCADE instalado, `/tesselar` responde 500 com o `ModuleNotFoundError` da biblioteca —
não um erro genérico.

## 7. Apagar em cada nível

```bash
curl -s -X DELETE localhost:4000/produtos/$B | head -c 200        # produto que compartilha geometria: a geometria fica
curl -s -X DELETE localhost:4100/importacoes/$ID | head -c 200     # importação terminada: produtos, storage, documento
curl -s -X DELETE localhost:4000/catalogos/$CAT | head -c 200      # catálogo: tudo dele
```
Esperado: cada resposta lista o que saiu (`produtos`, `arquivos`, `avisos`); apagar uma importação em
andamento → `409`.

## 8. Do `dist/`, não só do `dev`

```bash
pnpm -r build
CATALOGO_PORT=4099 pnpm start:catalogo & EDITOR_PORT=4499 pnpm start:editor & ZIP_PORT=4299 pnpm start:zip &
curl -s localhost:4099/health; curl -s localhost:4499/health; curl -s localhost:4299/health
```
Esperado: os três respondem `ok` — os pacotes `@bim/base` e `@bim/dominio` foram emitidos em `dist/` e resolvidos.

## 9. Recuperação no boot

Com um import em `parseando`, `kill -9` no criador (`ss -ltnp | grep ':4100 '`): o Python e o Chromium
filhos param sozinhos (stdin fechou). Ao subir de novo, o log diz `boot: N import(s) órfão(s) marcado(s) como falhou`
e `geo/<importId>` foi removido.

---

O que divergir do esperado é defeito ou documentação errada: corrigir no código ou no documento de origem.
