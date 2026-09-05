// Harness do teste do worker-ipc (I15): exercita `aguardarResultado` e `aguardarMiniaturas`
// com um filho falso (EventEmitter com `kill`) em cada cenário de morte do processo, e
// também com o thumb-worker REAL (fork via ts-node) recebendo um geoKey inexistente.
// Imprime um JSON {cenario: resultado} para o pytest conferir (tests/test_worker_ipc.py).
//
//   node --no-warnings --experimental-strip-types tests/paridade/worker_ipc.mts
import { EventEmitter } from 'node:events'
import { fork } from 'node:child_process'
import { existsSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { aguardarResultado, aguardarMiniaturas, descreveResumo } from '../../www/apps/api/src/importacoes/worker-ipc.ts'

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const API = path.join(REPO, 'www', 'apps', 'api')

class FilhoFalso extends EventEmitter {
  mortos: string[] = []
  kill(sinal?: string) { this.mortos.push(String(sinal)); return true }
}

const tick = (ms = 5) => new Promise((r) => setTimeout(r, ms))

async function capturar<T>(p: Promise<T>) {
  try {
    return { ok: await p }
  } catch (e: any) {
    return { erro: e.message, resumo: e.resumo ?? null }
  }
}

const saida: Record<string, unknown> = {}

// ── parse-worker: uma pergunta, uma resposta ─────────────────────────────────
{
  const c = new FilhoFalso()
  const p = capturar(aguardarResultado(c, 'parse-worker', 1000))
  c.emit('message', { status: 'ok', productCount: 3 })
  c.emit('exit', 0, null)
  saida.parse_ok = { ...(await p), mortos: c.mortos }
}
{
  const c = new FilhoFalso()
  const p = capturar(aguardarResultado(c, 'parse-worker', 1000))
  c.emit('exit', 0, null)
  saida.parse_exit0_sem_mensagem = await p
}
{
  const c = new FilhoFalso()
  const p = capturar(aguardarResultado(c, 'parse-worker', 1000))
  c.emit('exit', 1, null)
  saida.parse_exit1 = await p
}
{
  const c = new FilhoFalso()
  const p = capturar(aguardarResultado(c, 'parse-worker', 1000))
  c.emit('exit', null, 'SIGKILL')
  saida.parse_sinal = await p
}
{
  const c = new FilhoFalso()
  const p = capturar(aguardarResultado(c, 'parse-worker', 30))
  saida.parse_timeout = { ...(await p), mortos: c.mortos }
}
{
  const c = new FilhoFalso()
  const p = capturar(aguardarResultado(c, 'parse-worker', 1000))
  c.emit('error', new Error('spawn ENOENT'))
  saida.parse_erro_processo = await p
}
{
  // resolve uma vez; o exit ≠ 0 depois da mensagem não vira rejeição não tratada
  const c = new FilhoFalso()
  const p = capturar(aguardarResultado(c, 'parse-worker', 1000))
  c.emit('message', { status: 'vazio' })
  c.emit('exit', 1, null)
  c.emit('error', new Error('tarde demais'))
  saida.parse_settle_uma_vez = await p
}

// ── thumb-worker: fluxo de mensagens até o done ──────────────────────────────
{
  const c = new FilhoFalso()
  const miniaturas: string[] = []
  const falhas: string[] = []
  const p = capturar(aguardarMiniaturas(c, 3, {
    onMiniatura: (id, key) => { miniaturas.push(`${id}=${key}`) },
    onFalha: (id, msg) => { falhas.push(`${id}: ${msg}`) },
  }, 1000))
  c.emit('message', { type: 'thumb', productId: 'a', thumbKey: 'thumbs/i/a.webp' })
  c.emit('message', { type: 'error', productId: 'b', message: 'ENOENT: geo/b.json' })
  c.emit('message', { type: 'thumb', productId: 'c', thumbKey: 'thumbs/i/c.webp' })
  c.emit('message', { type: 'done', count: 2 })
  const r = await p
  saida.thumb_ok_com_falhas = { ...r, ganchos: { miniaturas, falhas }, descricao: r.ok ? descreveResumo(r.ok as any) : null, mortos: c.mortos }
}
{
  // o gancho (update do thumbKey no Mongo) rejeita: a imagem existe mas o produto não aponta — é falha
  const c = new FilhoFalso()
  const p = capturar(aguardarMiniaturas(c, 1, {
    onMiniatura: async () => { throw new Error('Mongo fora') },
  }, 1000))
  c.emit('message', { type: 'thumb', productId: 'a', thumbKey: 'thumbs/i/a.webp' })
  c.emit('message', { type: 'done', count: 1 })
  saida.thumb_gancho_rejeita = await p
}
{
  // o done espera os ganchos pendentes terminarem
  const c = new FilhoFalso()
  let ganchoTerminou = false
  const p = capturar(aguardarMiniaturas(c, 1, {
    onMiniatura: async () => { await tick(30); ganchoTerminou = true },
  }, 1000))
  c.emit('message', { type: 'thumb', productId: 'a', thumbKey: 'k' })
  c.emit('message', { type: 'done', count: 1 })
  const r = await p
  saida.thumb_done_espera_ganchos = { ...r, ganchoTerminou }
}
{
  const c = new FilhoFalso()
  const p = capturar(aguardarMiniaturas(c, 2, {}, 1000))
  c.emit('message', { type: 'thumb', productId: 'a', thumbKey: 'k' })
  c.emit('exit', 0, null)
  saida.thumb_exit0_sem_done = await p
}
{
  const c = new FilhoFalso()
  const p = capturar(aguardarMiniaturas(c, 2, {}, 1000))
  c.emit('exit', null, 'SIGKILL')
  saida.thumb_sinal = await p
}
{
  const c = new FilhoFalso()
  const p = capturar(aguardarMiniaturas(c, 2, {}, 30))
  c.emit('message', { type: 'thumb', productId: 'a', thumbKey: 'k' })
  saida.thumb_ocioso = { ...(await p), mortos: c.mortos }
}
{
  const c = new FilhoFalso()
  const p = capturar(aguardarMiniaturas(c, 2, {}, 1000))
  c.emit('error', new Error('spawn EACCES'))
  saida.thumb_erro_processo = await p
}
saida.descreve_sem_falhas = descreveResumo({ total: 4, geradas: 4, falhas: [] })
saida.descreve_com_falhas = descreveResumo({ total: 4, geradas: 2, falhas: [{ productId: 'x', message: 'ENOENT' }, { productId: 'y', message: 'z' }] })

// ── thumb-worker REAL com geoKey inexistente: tem de reportar a falha e mandar done ──
{
  const tsNode = path.join(API, 'node_modules', 'ts-node')
  if (!existsSync(tsNode)) {
    saida.real_thumb_worker_geo_inexistente = { skip: 'sem ts-node em www/apps/api/node_modules' }
  } else {
    const storage = mkdtempSync(path.join(tmpdir(), 'worker-ipc-'))
    const child = fork(path.join(API, 'src', 'importacoes', 'thumb-worker.ts'), [], {
      cwd: API,
      execArgv: ['--require', 'ts-node/register/transpile-only'],
      env: { ...process.env },
      silent: true, // stdout do filho não pode misturar com o JSON deste harness
    })
    let stderr = ''
    child.stderr!.on('data', (d) => { stderr += d })
    child.stdout!.on('data', () => {})
    const falhas: string[] = []
    const p = capturar(aguardarMiniaturas(child as any, 1, { onFalha: (id, m) => { falhas.push(`${id}: ${m}`) } }, 60_000))
    child.send({ products: [{ productId: 'inexistente', geoKey: 'geo/nao-existe.json' }], storagePath: storage, importId: 'teste-ipc' })
    const r = await p
    const codigo = await new Promise<number | null>((res) => (child.exitCode !== null ? res(child.exitCode) : child.on('exit', res)))
    rmSync(storage, { recursive: true, force: true })
    saida.real_thumb_worker_geo_inexistente = { ...r, ganchoFalhas: falhas, exitCode: codigo, stderr: stderr.slice(-500) }
  }
}

process.stdout.write(JSON.stringify(saida))
