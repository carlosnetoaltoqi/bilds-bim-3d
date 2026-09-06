/**
 * roundtrip-ifc-export.mts — prova o exportador IFC4 (ifc-export.ts) contra o
 * parser IFC do próprio projeto (biblioteca/bim_pipeline/parse_ifc.py) e, se instalado, o ifcopenshell.
 *
 * Pega um JSON de geometria real, segmenta, EDITA (gira+desloca uma parte — vira
 * IFCLOCALPLACEMENT; escala outra — vira vértices assados; acrescenta um tubo), exporta
 * o IFC e grava o `bake()` esperado. O `testes-editor.sh` roda depois a conferência em
 * Python: mesma contagem de triângulos, todo vértice com par a ≤ 2 µm (nos dois sentidos), cores, psets,
 * `ifcopenshell.validate`.
 *
 * Rode pelo `web/tools/testes-editor.sh`.
 */
import { readFileSync, writeFileSync } from 'node:fs'
import * as THREE from 'three'
import { segment, bake, withMatrix, makeTube, recolor } from './mesh-model.ts'
import { exportIfc, real, str, ifcGuid } from './ifc-export.ts'

const [file, outIfc, outEsperado] = process.argv.slice(2)
if (!file || !outIfc || !outEsperado) throw new Error('uso: roundtrip-ifc-export.mts <geo.json> <saida.ifc> <esperado.json>')
const geo = JSON.parse(readFileSync(file, 'utf8'))
const parts = segment(geo)
if (parts.length >= 3) {
  parts[1] = withMatrix(parts[1], new THREE.Matrix4().makeRotationY(Math.PI / 6).setPosition(0.05, 0.02, -0.01).toArray())
  parts[2] = withMatrix(parts[2], new THREE.Matrix4().makeScale(1.5, 1.5, 1.5).toArray())
}
parts.push(recolor(makeTube(0.05, 0.04, 0.1, [0.2, 0.4, 0.8]), [0.1, 0.6, 0.2]))
const r = exportIfc(parts, {
  nome: 'Peça de teste — "Incêndio"', id: 'teste-roundtrip', serie: 'Teste', fabricante: 'bilds', catalogo: 'Round-trip IFC',
  specs: { 'Tensão': 'Trifásico - 220/380V', 'Sucção x Recalque': '2.1/2" x 2.1/2"' }, potencia: 2, conexoes: null, produtoId: 'x',
})
writeFileSync(outIfc, r.ifc)
const esperado = bake(parts)
if (process.env.ROUNDTRIP_SABOTAR_IFC) {
  // autoteste da conferência em Python (testes-editor.sh / tests/test_editor_roundtrips.py):
  // um vértice do esperado 1 mm fora, DEPOIS de exportar o IFC, tem de virar FALHA e exit 1
  esperado.pos[0] += 1e-3
}
writeFileSync(outEsperado, JSON.stringify(esperado))
console.log(`ifc: ${r.partes} partes, ${r.triangulos} △, ${r.vertices} v, ${(r.bytes / 1024).toFixed(0)} KB → ${outIfc}`)
console.log('formatação STEP:', [real(1), real(0.000001), real(-0.0000001), real(1234.5678901)].join(' '), '|', str("Incêndio 'x'"), '|', ifcGuid('00000000-0000-0000-0000-000000000000'))
