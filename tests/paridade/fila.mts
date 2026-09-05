// Harness da fila de importações (I11): `www/apps/api/src/common/fila.ts` é puro, então roda
// direto no Node com strip-types. Imprime JSON {cenario: resultado} para tests/test_www_importacao.py.
//
//   node --no-warnings --experimental-strip-types tests/paridade/fila.mts
import { Fila, concorrenciaDoEnv } from '../../www/apps/api/src/common/fila.ts'

const tick = (ms: number) => new Promise((r) => setTimeout(r, ms))
const saida: Record<string, unknown> = {}

// ── concorrência 1: FIFO, um por vez, posições informadas ─────────────────────
{
  const fila = new Fila(1)
  const eventos: string[] = []
  const posicoes: Record<string, number> = {}
  const tarefa = (nome: string, ms: number) => fila.executar(nome, async () => {
    eventos.push(`${nome}:inicio(ativos=${fila.emExecucao},espera=${fila.tamanho})`)
    await tick(ms)
    eventos.push(`${nome}:fim`)
    return nome.toUpperCase()
  }, (n) => { posicoes[nome] = n })
  const pA = tarefa('a', 30)
  const pB = tarefa('b', 10)
  const pC = tarefa('c', 10)
  const esperandoLogo = fila.esperando.slice()
  const resultados = await Promise.all([pA, pB, pC])
  saida.fifo_um_por_vez = { eventos, posicoes, esperandoLogo, resultados, depois: { ativos: fila.emExecucao, espera: fila.tamanho } }
}

// ── rejeição passa adiante e não trava a fila ────────────────────────────────
{
  const fila = new Fila(1)
  const ordem: string[] = []
  const pErro = fila.executar('erro', async () => { await tick(5); ordem.push('erro'); throw new Error('worker morreu') })
  const pOk = fila.executar('ok', async () => { ordem.push('ok'); return 1 })
  const erro = await pErro.then(() => null, (e: Error) => e.message)
  const ok = await pOk
  saida.rejeicao_nao_trava = { erro, ok, ordem, depois: { ativos: fila.emExecucao, espera: fila.tamanho } }
}

// ── concorrência 2 ────────────────────────────────────────────────────────────
{
  const fila = new Fila(2)
  let pico = 0
  const posicoes: number[] = []
  const t = (ms: number) => fila.executar('t', async () => { pico = Math.max(pico, fila.emExecucao); await tick(ms) }, (n) => posicoes.push(n))
  await Promise.all([t(20), t(20), t(20), t(5)])
  saida.concorrencia_2 = { pico, posicoes }
}

// ── env ───────────────────────────────────────────────────────────────────────
const env = (v?: string) => { try { return concorrenciaDoEnv(v === undefined ? {} : { IMPORTACOES_CONCORRENCIA: v }) } catch (e: any) { return `erro: ${e.message}` } }
saida.env = { ausente: env(), vazio: env(''), tres: env('3'), zero: env('0'), texto: env('x'), nove: env('9') }
saida.construtor_invalido = (() => { try { new Fila(0); return 'aceitou' } catch (e: any) { return e.message } })()

process.stdout.write(JSON.stringify(saida))
