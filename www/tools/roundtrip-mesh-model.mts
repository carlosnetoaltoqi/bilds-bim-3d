/**
 * roundtrip-mesh-model.mts — prova o modelo de edição (mesh-model.ts) fora do browser.
 *
 * Sobre um JSON de geometria real do storage:
 *   - segment() → bake() devolve o MESMO conjunto de triângulos (a 1 µm);
 *   - espelhar duas vezes devolve a mesma parte;
 *   - recentrar na base põe min.y = 0 e o centro XZ na origem;
 *   - o tubo paramétrico é estanque (0 arestas de borda);
 *   - fundir preserva a soma de triângulos;
 *   - e mede a fração de arestas de borda em todas as geometrias do mesmo import
 *     (malha de fabricante NÃO é estanque — ver CLAUDE.md, "POC de edição").
 *
 * Rode pelo `www/tools/testes-editor.sh`, que resolve os imports `.ts` para o Node.
 */
import { readFileSync, readdirSync } from 'node:fs'
import * as THREE from 'three'
import { segment, bake, partStats, mirror, recenter, mergeParts, makeTube, docBbox } from './mesh-model.ts'

const file = process.argv[2]
if (!file) throw new Error('uso: roundtrip-mesh-model.mts <geo.json>')
const geo = JSON.parse(readFileSync(file, 'utf8'))
let falhas = 0
const check = (ok: boolean, msg: string) => { console.log(`  [${ok ? 'ok  ' : 'FALHA'}] ${msg}`); if (!ok) falhas++ }

const t0 = performance.now()
const parts = segment(geo)
console.log(`segment: ${parts.length} partes em ${(performance.now() - t0).toFixed(0)} ms — ${parts.filter((p) => p.marker).length} bocais`)

function triSet(g: { pos: number[]; idx: number[] }) {
  const set = new Set<string>()
  const v = (i: number) => `${g.pos[i * 3].toFixed(5)},${g.pos[i * 3 + 1].toFixed(5)},${g.pos[i * 3 + 2].toFixed(5)}`
  for (let t = 0; t < g.idx.length; t += 3) {
    const a = v(g.idx[t]), b = v(g.idx[t + 1]), c = v(g.idx[t + 2])
    set.add([[a, b, c], [b, c, a], [c, a, b]].map((x) => x.join('|')).sort()[0])
  }
  return set
}
const baked = bake(parts)
check(baked.idx.length === geo.idx.length, `bake preserva a contagem de triângulos (${baked.idx.length / 3})`)
const A = triSet(geo), B = triSet(baked)
let faltam = 0
for (const t of A) if (!B.has(t)) faltam++
check(faltam / A.size < 0.02, `round-trip a 10 µm: ${faltam} de ${A.size} triângulos fora (arredondamento a 1 µm funde vizinhos)`)
console.log(`  bytes: original ${(readFileSync(file).length / 1024).toFixed(0)} KB → salvo ${(JSON.stringify(baked).length / 1024).toFixed(0)} KB`)

const p0 = parts[0]
const m2 = mirror(mirror(p0, 'x', 'propria'), 'x', 'propria')
const s0 = partStats(p0), s2 = partStats(m2)
check(s0.triangulos === s2.triangulos && s0.bbox.min.distanceTo(s2.bbox.min) < 1e-6, 'espelho duplo devolve a mesma parte')

const bb = docBbox(recenter(parts, 'base'))
check(Math.abs(bb.min.y) < 1e-9 && Math.abs(bb.min.x + bb.max.x) < 1e-9 && Math.abs(bb.min.z + bb.max.z) < 1e-9, 'recentrar (base): min.y = 0, centro XZ na origem')

const tube = partStats(makeTube(0.05, 0.04, 0.1, [0.2, 0.4, 0.8]))
const tam = tube.bbox.getSize(new THREE.Vector3())
check(tube.arestasBorda === 0 && Math.abs(tam.x - 0.05) < 1e-6 && Math.abs(tam.y - 0.1) < 1e-6, `tubo 50/40×100 mm: ${tube.triangulos} △, ${tube.arestasBorda} arestas de borda, ${(tam.x * 100).toFixed(2)}×${(tam.y * 100).toFixed(2)} cm`)

const fused = mergeParts(parts.slice(0, 3))
check(partStats(fused).triangulos === parts.slice(0, 3).reduce((a, p) => a + p.idx.length / 3, 0), 'fundir preserva a soma de triângulos')

console.log('arestas de borda por geometria do import (malha de fabricante não é estanque):')
const dir = file.slice(0, file.lastIndexOf('/'))
for (const f of readdirSync(dir).filter((f) => f.endsWith('.json') && !f.endsWith('.orig.json')).slice(0, 20)) {
  const g = JSON.parse(readFileSync(`${dir}/${f}`, 'utf8'))
  const ps = segment(g)
  let borda = 0, arestas = 0
  for (const p of ps) { const s = partStats(p); borda += s.arestasBorda; arestas += s.triangulos * 1.5 }
  console.log(`  ${f.padEnd(44)} ${String(ps.length).padStart(4)} partes ${String(g.idx.length / 3).padStart(7)} △  borda ${(100 * borda / arestas).toFixed(0)}%`)
}
console.log(falhas ? `${falhas} FALHA(S)` : 'tudo ok')
process.exit(falhas ? 1 : 0)
