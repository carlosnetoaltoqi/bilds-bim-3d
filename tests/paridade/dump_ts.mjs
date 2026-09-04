// Harness do teste de paridade: roda os ports TypeScript de www/tools direto no
// Node (>= 22.6 remove os tipos sem transpilar) e imprime JSON para o pytest
// comparar com scripts/oq3d.py e scripts/read_aq.py.
//
//   node --no-warnings tests/paridade/dump_ts.mjs blobs <arquivo.bin>...
//   node --no-warnings tests/paridade/dump_ts.mjs aq <biblioteca.aq> [--sem-geometria]
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { toBuffers } from '../../www/tools/oq3d-parser.ts'
import { extract, extractSimboloias } from '../../www/tools/aq-reader.ts'

const [modo, ...resto] = process.argv.slice(2)

function buffersOuErro(blob) {
  try {
    return toBuffers(blob)
  } catch (e) {
    return { error: e.name, message: e.message }
  }
}

const sha1 = (b) => (b ? createHash('sha1').update(b).digest('hex') : null)

let saida
if (modo === 'blobs') {
  saida = {}
  for (const f of resto) saida[f] = buffersOuErro(readFileSync(f))
} else if (modo === 'aq') {
  const [caminho, ...flags] = resto
  const semGeometria = flags.includes('--sem-geometria')
  const dados = extract(caminho)
  const { simbologias, porPeca } = extractSimboloias(caminho)
  saida = {
    ...dados,
    simbologias: [...simbologias].map(([id, s]) => [id, {
      nome: s.nome, grupo: s.grupo, classe: s.classe,
      blobSha1: sha1(s.blob), blobLen: s.blob ? s.blob.length : 0,
      imagemSha1: sha1(s.imagem),
    }]),
    porPeca: [...porPeca],
    buffers: semGeometria ? null
      : Object.fromEntries([...simbologias].map(([id, s]) => [id, buffersOuErro(s.blob)])),
  }
} else {
  console.error('uso: dump_ts.mjs blobs <bin>... | aq <aq> [--sem-geometria]')
  process.exit(2)
}
process.stdout.write(JSON.stringify(saida))
