/**
 * roundtrip-mesh-model.mts — prova o modelo de edição (mesh-model.ts) fora do browser.
 *
 * Sobre um JSON de geometria real do storage:
 *   - segment() → bake() devolve o MESMO conjunto de triângulos (vértices casados
 *     por agrupamento espacial a ≤ 2 µm, sentido preservado);
 *   - espelhar duas vezes devolve a mesma parte;
 *   - recentrar na base põe min.y = 0 e o centro XZ na origem;
 *   - o tubo paramétrico é estanque (0 arestas de borda);
 *   - fundir preserva a soma de triângulos;
 *   - e mede a fração de arestas de borda em todas as geometrias do mesmo import
 *     (malha de fabricante NÃO é estanque — ver CLAUDE.md, "POC de edição").
 *
 * Rode pelo `web/tools/testes-editor.sh`, que resolve os imports `.ts` para o Node.
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

// Round-trip por agrupamento espacial, não por string (I13 da auditoria, 2026-09-04).
// O bake arredonda a 1 µm e o original carrega ruído float32: comparar `toFixed(5)`
// dos dois lados dava 28–32% de triângulos "fora" em malhas idênticas (0,0123455
// vira "0.01235" de um lado e "0.01234" do outro). Aqui os vértices do original e
// do bake entram juntos num union-find por grade de TOL: dois vértices a ≤ TOL caem
// no mesmo grupo, transitivamente. Isso resolve dois casos que "vizinho mais
// próximo" não resolve: (a) o dedup do bake chaveia por posição+cor, então partes
// de cores diferentes que se tocam têm vértices coincidentes duplicados; (b) dois
// vértices originais a 1,5 µm podem virar dois vértices do bake a 1 µm, e cada lado
// escolheria o "mais próximo" diferente. Malha de fabricante não tem aresta menor
// que dezenas de µm, então TOL = 2 µm não funde nada que não fosse o mesmo ponto.
const TOL = 2e-6
function agrupar(pos: ArrayLike<number>, tol: number): Int32Array {
  const n = pos.length / 3
  const pai = new Int32Array(n)
  for (let i = 0; i < n; i++) pai[i] = i
  const raiz = (i: number) => { while (pai[i] !== i) { pai[i] = pai[pai[i]]; i = pai[i] } return i }
  const unir = (a: number, b: number) => { a = raiz(a); b = raiz(b); if (a !== b) pai[Math.max(a, b)] = Math.min(a, b) }
  const grade = new Map<string, number[]>()
  const cel = (v: number) => Math.floor(v / tol)
  for (let i = 0; i < n; i++) {
    const k = `${cel(pos[i * 3])},${cel(pos[i * 3 + 1])},${cel(pos[i * 3 + 2])}`
    const lista = grade.get(k)
    if (lista) lista.push(i)
    else grade.set(k, [i])
  }
  const tol2 = tol * tol
  for (let i = 0; i < n; i++) {
    const x = pos[i * 3], y = pos[i * 3 + 1], z = pos[i * 3 + 2]
    const cx = cel(x), cy = cel(y), cz = cel(z)
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (let dz = -1; dz <= 1; dz++) {
      for (const j of grade.get(`${cx + dx},${cy + dy},${cz + dz}`) ?? []) {
        if (j <= i) continue
        const d = (pos[j * 3] - x) ** 2 + (pos[j * 3 + 1] - y) ** 2 + (pos[j * 3 + 2] - z) ** 2
        if (d <= tol2) unir(i, j)
      }
    }
  }
  const grupo = new Int32Array(n)
  for (let i = 0; i < n; i++) grupo[i] = raiz(i)
  return grupo
}
// chave canônica de um triângulo: gira até o menor grupo vir primeiro (mantém o sentido)
function chaveTri(a: number, b: number, c: number) {
  if (b < a && b <= c) return `${b}|${c}|${a}`
  if (c < a && c < b) return `${c}|${a}|${b}`
  return `${a}|${b}|${c}`
}
const baked = bake(parts)
if (process.env.ROUNDTRIP_SABOTAR) {
  // autoteste da métrica (tests/test_editor_roundtrips.py): um triângulo com o sentido
  // invertido e um vértice 1 mm fora têm de aparecer como FALHA — senão o teste não prova nada
  ;[baked.idx[1], baked.idx[2]] = [baked.idx[2], baked.idx[1]]
  baked.pos[baked.pos.length - 3] += 1e-3
}
check(baked.idx.length === geo.idx.length, `bake preserva a contagem de triângulos (${baked.idx.length / 3})`)
const nBake = baked.pos.length / 3, nOrig = geo.pos.length / 3
const grupo = agrupar([...baked.pos, ...geo.pos], TOL)   // bake primeiro, original depois (offset nBake)
const gruposDoBake = new Set<number>()
for (let i = 0; i < nBake; i++) gruposDoBake.add(grupo[i])
let semPar = 0
for (let i = 0; i < nOrig; i++) if (!gruposDoBake.has(grupo[nBake + i])) semPar++
const trisBake = new Set<string>()
for (let t = 0; t < baked.idx.length; t += 3) trisBake.add(chaveTri(grupo[baked.idx[t]], grupo[baked.idx[t + 1]], grupo[baked.idx[t + 2]]))
let triFora = 0
for (let t = 0; t < geo.idx.length; t += 3) {
  const a = grupo[nBake + geo.idx[t]], b = grupo[nBake + geo.idx[t + 1]], c = grupo[nBake + geo.idx[t + 2]]
  if (!trisBake.has(chaveTri(a, b, c))) triFora++
}
check(semPar === 0, `todo vértice original tem par no bake a ≤ ${TOL * 1e6} µm (${semPar} de ${nOrig} sem par)`)
check(triFora === 0, `todo triângulo original existe no bake com o mesmo sentido (${triFora} de ${geo.idx.length / 3} fora)`)
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
