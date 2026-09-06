---
title: "feat: S2.1 — Spike da fronteira: Python worker HTTP"
date: 2026-08-29
sequence: 002
type: feat
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
---

# feat: S2.1 — Spike da fronteira: Python worker HTTP

**Goal Capsule:** Provar que o pipeline Python (`read_aq` + `oq3d`) pode rodar como worker HTTP isolado — o equivalente k8s de um Deployment ou Job — recebendo o `.aq` como stream via POST, escrevendo geometrias no GeometryStore em disco, e inserindo documentos no Atlas, sem jamais tocar em `input/` ou `output/`.

**Sessão do plano:** S2.1 · **Linha de trabalho:** `docs/plano-produto-dinamico.md` · **Não avançar para S2.2.**

---

## Problem Frame

O pipeline Python existe hoje como script CLI que lê de `input/` e escreve em `output/`. Para funcionar num pod k8s ele precisa receber a biblioteca por stream (upload ou fila) e escrever via driver de storage (disco na POC, S3 em produção). Esta sessão constrói e prova o contrato mínimo — a fronteira entre Node e Python que o ADR-001 implica.

---

## Requirements

- **R1:** O worker recebe o `.aq` como bytes no corpo de um POST HTTP, nunca acessando `input/` ou `output/`
- **R2:** O worker escreve cada JSON de geometria via `DiskGeometryStore` Python no mesmo `STORAGE_PATH` usado pelo Node (chave `geo/{importId}/{productId}.json`)
- **R3:** O worker insere/atualiza documentos `bim_catalogs` e `bim_products` no Atlas via pymongo, usando `MONGODB_URI` e `MONGODB_DB` do ambiente
- **R4:** O worker mede e reporta pico de memória RSS (nível OS) e alocação Python (tracemalloc) durante o parse
- **R5:** Um script Node de teste invoca o worker end-to-end e verifica geometrias em disco e documentos no Atlas

---

## Scope Boundaries

**In scope:** worker Flask HTTP; Python DiskGeometryStore; pymongo writes; tracemalloc + `resource` RSS; Node test script end-to-end.

**Out of scope:** miniaturas (S2.4); bim_imports state machine (S2.3); fila real (SQS/RabbitMQ/BullMQ); autenticação; port TypeScript (S2.2).

### Deferred to Follow-Up Work

- Integração com `bim_imports` state machine e transições de estado → S2.3
- Miniaturas no servidor → S2.4
- Port TypeScript do mesmo pipeline → S2.2 (comparação de custo)

---

## Key Technical Decisions

**KTD1 — Protocolo: HTTP local (Flask)**
O worker expõe `POST /parse` em `localhost:5001`. O `.aq` vem como body `application/octet-stream`; `X-Import-Id`, `X-Company-Id`, `X-Catalog-Id`, `X-File-Name` chegam em headers HTTP. Simula melhor um Deployment/Job isolado do que stdin/stdout — tem health check (`GET /health`), resposta tipada, e o Node não precisa gerenciar o ciclo de vida do processo além de `spawn`/`kill`. Em k8s real seria um consumer de fila, mas a fronteira de dados é a mesma.

**KTD2 — GeometryStore em Python: implementação direta em disco**
O worker escreve arquivos via classe Python `DiskGeometryStore` (`put(key, data: bytes)`) no mesmo `STORAGE_PATH`. Em k8s com PVC RWX ambos os pods montam o mesmo volume; com S3 o Python usaria `boto3` na mesma interface. Não há callback ao Node para escrita de arquivo — o worker é auto-suficiente, como seria um Job k8s.

**KTD3 — MongoDB: pymongo direto no worker**
O worker lê `MONGODB_URI` e `MONGODB_DB` do ambiente (os mesmos do `www/.env`) e escreve via `pymongo`. Em k8s as mesmas variáveis seriam injetadas como Secrets. Não há callback ao Node para escrita de banco.

**KTD4 — Medição de memória: tracemalloc + resource RSS**
`tracemalloc` mede alocação Python no heap; `resource.getrusage(RUSAGE_SELF).ru_maxrss` mede o RSS do processo (inclui extensões C como numpy). Ambos são reportados. A diferença entre os dois é o overhead das extensões C — informação que S2.2 vai precisar para comparação justa com o port TypeScript.

**KTD5 — STORAGE_PATH: absoluto via test script**
O test script passa `STORAGE_PATH` como caminho absoluto no env do worker subprocess (`path.resolve(__dirname, '../storage/bim')`), eliminando a ambiguidade do caminho relativo que causou o bug da S1.2 no TypeScript. O worker nunca assume CWD.

---

## High-Level Technical Design

```
  Node test script                       Python worker (Flask :5001)
  www/tools/test-worker.ts               www/workers/aq-parser/worker.py

  1. spawn('python3 worker.py')          aguarda na porta 5001
     poll GET /health (retry 500ms×20) ──► 200 OK
     lê .aq de input/Dancor/

  2. POST /parse                         recebe body → tmpfile
     body: bytes .aq          ─────────► read_aq.open_aq(tmp) → produtos
     X-Import-Id: <new uuid>              oq3d.to_buffers(blob) × N
     X-Catalog-Id: <new uuid>             DiskGeometryStore.put(geoKey, json)
                                          │ STORAGE_PATH/geo/<importId>/<id>.json
                                          pymongo: upsert bim_catalogs
                                          pymongo: insert_many bim_products
                                          tracemalloc + resource RSS
                              ◄────────── { status, productCount,
                                            peakMemoryMb, peakTraceMb }

  3. verifica disco: readdir geo/<importId>/ → 13 arquivos
  4. verifica banco: countDocuments({ importId }) → 13
  5. imprime tabela de métricas; SIGTERM worker; exit 0
```

---

## Output Structure

```
www/
├── workers/
│   └── aq-parser/
│       ├── worker.py          ← Flask HTTP server (novo)
│       └── requirements.txt   ← flask, pymongo, numpy, python-dotenv (novo)
└── tools/
    └── test-worker.ts         ← Node integration test (novo)
```

`www/package.json` ganha o script `worker:test`.

---

## Implementation Units

### U1. Python worker HTTP

**Goal:** Implementar `worker.py` — Flask server que recebe `.aq`, processa com `read_aq`+`oq3d`, grava via `DiskGeometryStore` Python, e insere no Atlas.

**Requirements:** R1, R2, R3, R4

**Dependencies:** nenhum

**Files:**
- `www/workers/aq-parser/worker.py` (criar)
- `www/workers/aq-parser/requirements.txt` (criar)

**Approach:**
1. `requirements.txt`: `flask>=3.0`, `pymongo>=4.0`, `numpy>=1.24`, `python-dotenv>=1.0`
2. No topo de `worker.py`: carregar `www/.env` via `load_dotenv(os.path.join(os.path.dirname(__file__), '../..', '.env'))`; adicionar `scripts/` ao `sys.path` com caminho absoluto via `__file__` (3 níveis acima do arquivo → raiz do repo → `scripts/`)
3. Classe `DiskGeometryStore(base_dir)`:
   - `put(key, data: bytes)` — valida `os.path.realpath(os.path.join(base_dir, key)).startswith(os.path.realpath(base_dir))`, cria diretórios, escreve bytes
   - key format: `geo/{importId}/{productId}.json`
4. `GET /health` → `200 OK {"status": "ok"}`
5. `POST /parse`:
   - Lê body para `tempfile.NamedTemporaryFile(delete=False)`; lê headers `X-Import-Id`, `X-Company-Id`, `X-Catalog-Id`, `X-File-Name`
   - `tracemalloc.start()`; snapshot de RSS antes (`resource.getrusage(RUSAGE_SELF).ru_maxrss`)
   - `con, tmp_dir = read_aq.open_aq(tmp_path)` → itera produtos com geometria via `read_aq.extract_products(con)`
   - Para cada produto com geometria: `oq3d.to_buffers(blob)` → `json.dumps(buffers).encode()` → `store.put(geoKey, data)`
   - pymongo: `db.bim_catalogs.update_one({_id: catalogId}, ..., upsert=True)`; `db.bim_products.insert_many(docs)`
   - Snapshot RSS final; `tracemalloc.get_traced_memory()` peak
   - Limpa `tmp_path`; retorna `{ status, productCount, peakMemoryMb, peakTraceMb, error }`
6. `status` é `'ok'` se `productCount > 0`, `'empty'` se 0 produtos com geometria, `'failed'` se exceção — com `error` preenchido

**Patterns to follow:**
- `www/apps/api/src/geometry-store/disk-geometry-store.ts` — contrato e validação de chave
- `www/tools/ingest-library.ts` — mapeamento dos campos `read_aq JSON → bim_product document`
- `scripts/read_aq.py` `open_aq()` — entrada, não modificar

**Test scenarios:**
- POST com Dancor `.aq` → `{ status: 'ok', productCount: 13 }`
- Após POST, `os.listdir(storage/geo/<importId>/)` contém exatamente 13 `.json`
- Body da resposta inclui `peakMemoryMb > 0` e `peakTraceMb > 0`
- POST sem body retorna `400`
- Segunda chamada com mesmo `catalogId` mas `importId` diferente → upsert em `bim_catalogs` sem duplicata; novos 13 documentos em `bim_products`

**Verification:** `GET http://localhost:5001/health` → 200; POST com Dancor `.aq` → `{ status: 'ok', productCount: 13 }`

---

### U2. Node integration test

**Goal:** Script `test-worker.ts` que faz spawn do worker, verifica end-to-end, e imprime tabela de métricas.

**Requirements:** R1, R4, R5

**Dependencies:** U1

**Files:**
- `www/tools/test-worker.ts` (criar)
- `www/package.json` (atualizar — adicionar script `worker:test`)

**Approach:**
1. `spawn('python3', [workerPath], { env: { ...process.env, STORAGE_PATH: absoluteStoragePath } })` onde `workerPath = path.resolve(__dirname, '../workers/aq-parser/worker.py')`; `absoluteStoragePath = path.resolve(__dirname, '../storage/bim')`
2. Poll `GET http://localhost:5001/health` com até 20 tentativas × 500 ms; aborta com erro se não responder
3. Novo `importId = crypto.randomUUID()` e `catalogId = crypto.randomUUID()` — não reutiliza os da S1.2
4. Lê `input/Dancor/pecas_dancor_bombas.aq` como Buffer; monta requisição POST com headers `X-Import-Id`, `X-Company-Id`, `X-Catalog-Id`, `X-File-Name`
5. Verifica resposta: `status === 'ok'` e `productCount === 13`
6. Verifica disco: `fs.readdir(storagePath/geo/<importId>/)` → exactly 13 entries
7. Verifica banco: `MongoClient.db().collection('bim_products').countDocuments({ importId })` → 13
8. Imprime tabela: productCount, peakMemoryMb, peakTraceMb, tempo total (ms)
9. `SIGTERM` no processo worker; `process.exit(0)` se tudo passou, `process.exit(1)` se falhou
10. Script `worker:test` em `www/package.json`: mesmo padrão de NODE_PATH de `pnpm ingest` (filter api, NODE_PATH=$(pwd)/node_modules) para resolver `mongodb`

**Patterns to follow:**
- `www/tools/ingest-library.ts` — NODE_PATH, MongoClient bootstrap, `fmt()` helpers
- Script `ingest` em `www/package.json` — modelo do comando pnpm

**Test scenarios:**
- `pnpm worker:test` encerra com código 0 e imprime `productCount=13`
- Disco: `ls storage/bim/geo/<importId>/ | wc -l` → 13 após o teste
- Banco: `db.bim_products.countDocuments({ importId })` → 13
- `peakMemoryMb` é numérico e > 0 na tabela impressa
- Arquivo `worker.py` não contém string `'input/'` nem `'output/'` (grep verifica)

**Verification:** `cd /home/foltz/bilds-bim-3d/www && pnpm worker:test` → exit 0, tabela com `productCount=13`

---

## Verification Contract

```bash
cd /home/foltz/bilds-bim-3d/www
pnpm worker:test
# → tabela com productCount=13, peakMemoryMb>0, exit 0

# Confirmar isolamento:
grep -r "input/\|output/" www/workers/aq-parser/worker.py
# → nenhuma saída
```

---

## Definition of Done

- [ ] `pnpm worker:test` encerra com código 0 e imprime tabela com `productCount=13`
- [ ] `grep -r "input/\|output/" www/workers/aq-parser/worker.py` não retorna nada
- [ ] `peakMemoryMb` reportado na tabela (registrar o valor no log da sessão)
- [ ] Commit em `main` com todos os arquivos novos
- [ ] Registro `docs/sessoes/S2.1-*.md` criado seguindo `docs/sessoes/TEMPLATE.md`
- [ ] Seção 11 de `docs/plano-produto-dinamico.md` atualizada: S2.1 → `concluída`
- [ ] Prompt da próxima sessão (S2.2) impresso ao encerrar

---

## Open Questions

Nenhuma — todas as decisões técnicas fechadas nos KTDs acima.

---

## Assumptions

- `python3` está no PATH com versão >= 3.10 (verificado: Python 3.12.3 em `which python3`)
- `flask`, `pymongo`, `numpy`, `python-dotenv` instaláveis via `pip install -r requirements.txt` sem sudo
- `resource` módulo disponível (stdlib Unix — presente em Linux/WSL)
- `www/.env` existe com `MONGODB_URI`, `MONGODB_DB=bilds-bim-3d`, `STORAGE_PATH=../../storage/bim` (verificado em S1.2)
- Atlas ainda libera o IP desta máquina (testar com `pnpm smoke:geo` antes de começar)
