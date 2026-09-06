// Harness do `executar()` (apps/ingestao/src/pipeline/processo.ts): cada jeito de um processo
// filho morrer vira ProcessoError com motivo, e as linhas de saída chegam na hora.
// Roda com `node --experimental-strip-types` (só builtins). Imprime JSON para tests/test_processo.py.
import { executar, ProcessoError } from '../../pacotes/base/src/processo.ts'

const node = process.execPath
const saida: Record<string, unknown> = {}

async function capturar(p: Promise<unknown>) {
  try {
    return { ok: await p }
  } catch (e: any) {
    if (e instanceof ProcessoError) return { erro: { motivo: e.motivo, code: e.code, signal: e.signal, message: e.message, stderr: e.stderr } }
    return { erro: { message: String(e?.message ?? e) } }
  }
}

// sucesso: stdout e stderr linha a linha, resultado com o stdout inteiro
{
  const linhas: string[] = []
  const r = await capturar(executar(node, ['-e', "console.log('a');console.log('b');console.error('e1');process.stdout.write('sem-newline')"], {
    onStdout: (l) => linhas.push(l), timeoutMs: 10_000,
  }))
  saida.ok = { ...r, linhas }
}
// saída ≠ 0: motivo 'saida', código e as últimas linhas do stderr na mensagem
saida.saida3 = await capturar(executar(node, ['-e', "console.error('x');console.error('motivo real');process.exit(3)"], { nome: 'teste.py', timeoutMs: 10_000 }))
// mesmo código aceito explicitamente resolve
saida.aceita3 = await capturar(executar(node, ['-e', 'process.exit(3)'], { aceitarCodigos: [0, 3], timeoutMs: 10_000 }))
// sinal
saida.sinal = await capturar(executar(node, ['-e', "process.kill(process.pid,'SIGTERM');setTimeout(()=>{},2000)"], { timeoutMs: 10_000 }))
// timeout total: filho falante mas eterno
{
  const t0 = Date.now()
  const r = await capturar(executar(node, ['-e', 'setInterval(()=>console.log("tick"),50)'], { timeoutMs: 400, guardarStdout: false }))
  saida.timeout = { ...r, ms: Date.now() - t0 }
}
// ocioso: uma linha e depois silêncio
{
  const t0 = Date.now()
  const r = await capturar(executar(node, ['-e', 'console.log("one");setTimeout(()=>{},10000)'], { timeoutMs: 10_000, ociosoMs: 300 }))
  saida.ocioso = { ...r, ms: Date.now() - t0 }
}
// comando inexistente
saida.spawn = await capturar(executar('nao-existe-bilds-xyz', [], { timeoutMs: 10_000 }))
// o stdin do filho fica ABERTO enquanto o pai vive: um filho que sai no EOF do stdin não sai antes da hora
saida.stdinAberto = await capturar(executar(node, ['-e', "process.stdin.on('end',()=>process.exit(2));process.stdin.resume();setTimeout(()=>process.exit(0),700)"], { timeoutMs: 10_000 }))

process.stdout.write(JSON.stringify(saida))
