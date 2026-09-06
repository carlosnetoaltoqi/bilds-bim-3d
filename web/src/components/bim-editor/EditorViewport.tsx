'use client'

/**
 * EditorViewport — a cena Three.js do editor.
 *
 * Uma Mesh por parte (ver mesh-model.ts), reconciliada a cada mudança de `parts`:
 * geometria só é reconstruída quando os buffers da parte mudam de referência; a
 * matriz é decomposta em posição/rotação/escala para o TransformControls poder
 * mexer nela. Enquanto o usuário arrasta o gizmo nada sobe para o React — a
 * matriz final é reportada uma vez em `onCommitMatrix`, no soltar do mouse.
 * Com várias partes selecionadas, o gizmo fica na principal e o delta é
 * aplicado às demais.
 *
 * Mesma iluminação, fundo e material do viewer público (buildScene), para que o
 * que se vê aqui seja o que o visitante verá.
 */

import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { TransformControls } from 'three/addons/controls/TransformControls.js'
import type { GeoData } from '../bim-catalog/bim-viewer-engine'
import { docBbox, type Part } from './mesh-model'

export type Tool = 'select' | 'translate' | 'rotate' | 'scale'
export type ViewPreset = 'iso' | 'frente' | 'tras' | 'topo' | 'baixo' | 'direita' | 'esquerda'

export interface ViewportProps {
  parts: Part[]
  selected: string[]
  tool: Tool
  wireframe: boolean
  snap: boolean
  showGrid: boolean
  showMarkers: boolean
  ghost: GeoData | null
  clip: { enabled: boolean; frac: number }
  /** incrementar para enquadrar */
  fitRequest: number
  /** incrementar `n` e definir `view` para aplicar uma vista */
  viewRequest: { n: number; view: ViewPreset }
  onSelect: (ids: string[], additive: boolean) => void
  onCommitMatrix: (changes: Array<{ id: string; matrix: number[] }>) => void
  onCamera?: (info: { dist: number }) => void
}

interface MeshRecord {
  mesh: THREE.Mesh
  pos: Float32Array
  col: Float32Array | null
  idx: Uint32Array
}

interface ViewportState {
  renderer: THREE.WebGLRenderer
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  orbit: OrbitControls
  gizmo: TransformControls
  group: THREE.Group
  meshes: Map<string, MeshRecord>
  mats: ReturnType<typeof makeMaterials>
  grid: THREE.GridHelper | null
  axes: THREE.AxesHelper | null
  gridSize: number
  selBox: THREE.Box3Helper
  ghostMesh: THREE.Mesh | null
  clipPlane: THREE.Plane
  raf: number
  dragStart: Map<string, THREE.Matrix4> | null
  dragging: boolean
}

const BG = 0xf3f4f6
const MARKER_OPACITY = 0.55

function makeMaterials() {
  const base = { metalness: 0.25, roughness: 0.55 }
  const colored = new THREE.MeshStandardMaterial({ ...base, vertexColors: true, color: 0xffffff })
  const plain = new THREE.MeshStandardMaterial({ ...base, color: 0x8896aa })
  const coloredSel = new THREE.MeshStandardMaterial({ ...base, vertexColors: true, color: 0xffffff, emissive: 0x2f6bff, emissiveIntensity: 0.45 })
  const plainSel = new THREE.MeshStandardMaterial({ ...base, color: 0x8896aa, emissive: 0x2f6bff, emissiveIntensity: 0.45 })
  const markerMat = new THREE.MeshStandardMaterial({ ...base, vertexColors: true, color: 0xffffff, transparent: true, opacity: MARKER_OPACITY })
  const markerSel = new THREE.MeshStandardMaterial({ ...base, vertexColors: true, color: 0xffffff, transparent: true, opacity: 0.8, emissive: 0x2f6bff, emissiveIntensity: 0.45 })
  const ghost = new THREE.MeshBasicMaterial({ color: 0xff7a00, transparent: true, opacity: 0.22, depthWrite: false, side: THREE.DoubleSide })
  return { colored, plain, coloredSel, plainSel, markerMat, markerSel, ghost }
}

export function EditorViewport(props: ViewportProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const propsRef = useRef(props)
  propsRef.current = props

  const stateRef = useRef<ViewportState | null>(null)

  // ── montagem única ────────────────────────────────────────────────────────
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const W = el.clientWidth || 800
    const H = el.clientHeight || 600

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(W, H, false)
    renderer.setClearColor(BG, 1)
    renderer.localClippingEnabled = true
    renderer.domElement.style.width = '100%'
    renderer.domElement.style.height = '100%'
    renderer.domElement.style.display = 'block'
    el.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    scene.add(new THREE.AmbientLight(0xffffff, 0.7))
    const key = new THREE.DirectionalLight(0xffffff, 0.9)
    key.position.set(2, 3, 2)
    scene.add(key)
    const fill = new THREE.DirectionalLight(0xc8d8f0, 0.35)
    fill.position.set(-2, 1, -1)
    scene.add(fill)

    const camera = new THREE.PerspectiveCamera(34, W / H, 0.001, 500)
    camera.position.set(1, 0.6, 1)

    const orbit = new OrbitControls(camera, renderer.domElement)
    orbit.enableDamping = true
    orbit.dampingFactor = 0.08

    const group = new THREE.Group()
    scene.add(group)

    const gizmo = new TransformControls(camera, renderer.domElement)
    gizmo.setSize(0.9)
    scene.add(gizmo.getHelper())

    const selBox = new THREE.Box3Helper(new THREE.Box3(), 0x2f6bff)
    selBox.visible = false
    scene.add(selBox)

    const clipPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0)
    const mats = makeMaterials()

    const state: ViewportState = {
      renderer, scene, camera, orbit, gizmo, group,
      meshes: new Map<string, MeshRecord>(),
      mats, grid: null, axes: null, gridSize: 0, selBox, ghostMesh: null, clipPlane,
      raf: 0, dragStart: null, dragging: false,
    }
    stateRef.current = state

    // gizmo ↔ orbit
    gizmo.addEventListener('dragging-changed', (e: any) => {
      const dragging = !!e.value
      orbit.enabled = !dragging
      state.dragging = dragging
      const p = propsRef.current
      if (dragging) {
        // guarda a matriz inicial de todas as selecionadas
        const start = new Map<string, THREE.Matrix4>()
        for (const id of p.selected) {
          const rec = state.meshes.get(id)
          if (rec) {
            rec.mesh.updateMatrix()
            start.set(id, rec.mesh.matrix.clone())
          }
        }
        state.dragStart = start
      } else if (state.dragStart) {
        const changes: Array<{ id: string; matrix: number[] }> = []
        for (const id of state.dragStart.keys()) {
          const rec = state.meshes.get(id)
          if (rec) {
            rec.mesh.updateMatrix()
            changes.push({ id, matrix: rec.mesh.matrix.toArray() })
          }
        }
        state.dragStart = null
        if (changes.length) p.onCommitMatrix(changes)
      }
    })
    gizmo.addEventListener('objectChange', () => {
      const p = propsRef.current
      const obj = gizmo.object as THREE.Mesh | undefined
      if (!obj || !state.dragStart || p.selected.length < 2) return
      const primaryId = obj.userData.partId as string
      const m0 = state.dragStart.get(primaryId)
      if (!m0) return
      obj.updateMatrix()
      const delta = obj.matrix.clone().multiply(m0.clone().invert())
      for (const [id, start] of state.dragStart) {
        if (id === primaryId) continue
        const rec = state.meshes.get(id)
        if (!rec) continue
        const m = delta.clone().multiply(start)
        m.decompose(rec.mesh.position, rec.mesh.quaternion, rec.mesh.scale)
      }
    })

    // seleção por clique (sem arrasto)
    const down = { x: 0, y: 0, t: 0 }
    const raycaster = new THREE.Raycaster()
    const onDown = (e: PointerEvent) => {
      down.x = e.clientX
      down.y = e.clientY
      down.t = Date.now()
    }
    const onUp = (e: PointerEvent) => {
      if (state.dragging || gizmo.dragging) return
      if (Math.hypot(e.clientX - down.x, e.clientY - down.y) > 4) return
      if (e.button !== 0) return
      const rect = renderer.domElement.getBoundingClientRect()
      const ndc = new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1,
      )
      raycaster.setFromCamera(ndc, camera)
      const candidates: THREE.Object3D[] = []
      for (const rec of state.meshes.values()) if (rec.mesh.visible) candidates.push(rec.mesh)
      const hits = raycaster.intersectObjects(candidates, false)
      const additive = e.shiftKey || e.ctrlKey || e.metaKey
      if (hits.length) {
        propsRef.current.onSelect([hits[0].object.userData.partId as string], additive)
      } else if (!additive) {
        propsRef.current.onSelect([], false)
      }
    }
    renderer.domElement.addEventListener('pointerdown', onDown)
    renderer.domElement.addEventListener('pointerup', onUp)

    // resize
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth, h = el.clientHeight
      if (!w || !h) return
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    })
    ro.observe(el)

    // loop
    const tmpBox = new THREE.Box3()
    const animate = () => {
      state.raf = requestAnimationFrame(animate)
      orbit.update()
      // bbox da seleção
      const sel = propsRef.current.selected
      if (sel.length) {
        tmpBox.makeEmpty()
        for (const id of sel) {
          const rec = state.meshes.get(id)
          if (rec && rec.mesh.visible) tmpBox.expandByObject(rec.mesh)
        }
        if (!tmpBox.isEmpty()) {
          selBox.box.copy(tmpBox)
          selBox.visible = true
        } else selBox.visible = false
      } else selBox.visible = false
      renderer.render(scene, camera)
    }
    animate()

    return () => {
      cancelAnimationFrame(state.raf)
      ro.disconnect()
      renderer.domElement.removeEventListener('pointerdown', onDown)
      renderer.domElement.removeEventListener('pointerup', onUp)
      gizmo.detach()
      gizmo.dispose()
      orbit.dispose()
      for (const rec of state.meshes.values()) rec.mesh.geometry.dispose()
      Object.values(mats).forEach((m) => m.dispose())
      state.ghostMesh?.geometry.dispose()
      renderer.dispose()
      if (renderer.domElement.parentElement === el) el.removeChild(renderer.domElement)
      stateRef.current = null
    }
  }, [])

  // ── reconciliação das partes ─────────────────────────────────────────────
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    const seen = new Set<string>()
    for (const part of props.parts) {
      seen.add(part.id)
      let rec = s.meshes.get(part.id)
      if (!rec) {
        const geom = buildGeometry(part)
        const mesh = new THREE.Mesh(geom, s.mats.colored)
        mesh.userData.partId = part.id
        s.group.add(mesh)
        rec = { mesh, pos: part.pos, col: part.col, idx: part.idx }
        s.meshes.set(part.id, rec)
      } else if (rec.pos !== part.pos || rec.col !== part.col || rec.idx !== part.idx) {
        rec.mesh.geometry.dispose()
        rec.mesh.geometry = buildGeometry(part)
        rec.pos = part.pos
        rec.col = part.col
        rec.idx = part.idx
      }
      // matriz → TRS (não durante um arrasto: o gizmo é dono da matriz)
      if (!s.dragging) {
        const m = new THREE.Matrix4().fromArray(part.matrix)
        m.decompose(rec.mesh.position, rec.mesh.quaternion, rec.mesh.scale)
      }
      rec.mesh.visible = part.visible && (props.showMarkers || !part.marker)
      rec.mesh.userData.marker = part.marker
      rec.mesh.userData.hasCol = !!part.col
    }
    for (const [id, rec] of s.meshes) {
      if (!seen.has(id)) {
        s.group.remove(rec.mesh)
        rec.mesh.geometry.dispose()
        s.meshes.delete(id)
      }
    }
    // grade proporcional ao modelo
    const box = docBbox(props.parts)
    if (!box.isEmpty()) {
      const size = box.getSize(new THREE.Vector3())
      const maxDim = Math.max(size.x, size.z, 0.05)
      const cell = maxDim > 2 ? 0.5 : maxDim > 0.6 ? 0.1 : maxDim > 0.15 ? 0.05 : 0.01
      const gridSize = Math.ceil((maxDim * 2.2) / cell) * cell
      if (gridSize !== s.gridSize) {
        if (s.grid) { s.scene.remove(s.grid); s.grid.dispose() }
        if (s.axes) { s.scene.remove(s.axes); s.axes.dispose() }
        s.grid = new THREE.GridHelper(gridSize, Math.round(gridSize / cell), 0x9aa4b2, 0xd5dae2)
        s.axes = new THREE.AxesHelper(gridSize / 2)
        s.scene.add(s.grid, s.axes)
        s.gridSize = gridSize
      }
    }
    applyMaterials(s, props)
  }, [props.parts, props.showMarkers]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── seleção, ferramenta, wireframe, snap, grade ──────────────────────────
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    applyMaterials(s, props)
    const primary = props.selected.length ? s.meshes.get(props.selected[props.selected.length - 1]) : undefined
    if (props.tool !== 'select' && primary && primary.mesh.visible) {
      s.gizmo.attach(primary.mesh)
      s.gizmo.setMode(props.tool)
      s.gizmo.enabled = true
      s.gizmo.getHelper().visible = true
    } else {
      s.gizmo.detach()
      s.gizmo.getHelper().visible = false
    }
    s.gizmo.setTranslationSnap(props.snap ? 0.005 : null)
    s.gizmo.setRotationSnap(props.snap ? THREE.MathUtils.degToRad(15) : null)
    s.gizmo.setScaleSnap(props.snap ? 0.1 : null)
    if (s.grid) s.grid.visible = props.showGrid
    if (s.axes) s.axes.visible = props.showGrid
  }, [props.selected, props.tool, props.wireframe, props.snap, props.showGrid, props.parts]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── plano de corte ───────────────────────────────────────────────────────
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    const box = docBbox(props.parts)
    const planes = props.clip.enabled && !box.isEmpty() ? [s.clipPlane] : []
    if (props.clip.enabled && !box.isEmpty()) {
      const y = box.min.y + (box.max.y - box.min.y) * props.clip.frac
      // normal (0,-1,0): mantém o que está ABAIXO de y
      s.clipPlane.set(new THREE.Vector3(0, -1, 0), y)
    }
    // o fantasma do original também é cortado — senão a comparação no corte não faz sentido
    for (const m of Object.values(s.mats)) {
      if (m.clippingPlanes?.length !== planes.length) {
        m.clippingPlanes = planes
        m.needsUpdate = true
      }
    }
  }, [props.clip, props.parts])

  // ── fantasma do original ─────────────────────────────────────────────────
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    if (s.ghostMesh) {
      s.scene.remove(s.ghostMesh)
      s.ghostMesh.geometry.dispose()
      s.ghostMesh = null
    }
    if (props.ghost) {
      const g = new THREE.BufferGeometry()
      g.setAttribute('position', new THREE.Float32BufferAttribute(props.ghost.pos, 3))
      if (props.ghost.idx) g.setIndex(props.ghost.idx)
      const mesh = new THREE.Mesh(g, s.mats.ghost)
      mesh.renderOrder = 2
      s.scene.add(mesh)
      s.ghostMesh = mesh
    }
  }, [props.ghost])

  // ── enquadrar / vistas ───────────────────────────────────────────────────
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    fit(s, props.parts, props.viewRequest.view)
  }, [props.fitRequest]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    fit(s, props.parts, props.viewRequest.view)
  }, [props.viewRequest.n]) // eslint-disable-line react-hooks/exhaustive-deps

  return <div ref={containerRef} className="w-full h-full min-h-[300px]" />
}

function buildGeometry(part: Part): THREE.BufferGeometry {
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(part.pos, 3))
  if (part.col) g.setAttribute('color', new THREE.BufferAttribute(part.col, 3))
  g.setIndex(new THREE.BufferAttribute(part.idx, 1))
  g.computeVertexNormals()
  g.computeBoundingBox()
  g.computeBoundingSphere()
  return g
}

function applyMaterials(s: Pick<ViewportState, 'meshes' | 'mats'>, props: ViewportProps) {
  const sel = new Set(props.selected)
  for (const [id, rec] of s.meshes) {
    const isSel = sel.has(id)
    const hasCol = !!rec.mesh.userData.hasCol
    const marker = !!rec.mesh.userData.marker
    let mat: THREE.MeshStandardMaterial
    if (marker) mat = isSel ? s.mats.markerSel : s.mats.markerMat
    else if (hasCol) mat = isSel ? s.mats.coloredSel : s.mats.colored
    else mat = isSel ? s.mats.plainSel : s.mats.plain
    rec.mesh.material = mat
  }
  for (const m of Object.values(s.mats)) {
    if (m === s.mats.ghost) continue
    if ((m as THREE.MeshStandardMaterial).wireframe !== props.wireframe) (m as THREE.MeshStandardMaterial).wireframe = props.wireframe
  }
}

const VIEW_DIRS: Record<ViewPreset, [number, number, number]> = {
  iso: [1, 0.6, 1],
  frente: [0, 0.0001, 1],
  tras: [0, 0.0001, -1],
  topo: [0, 1, 0.0001],
  baixo: [0, -1, 0.0001],
  direita: [1, 0.0001, 0],
  esquerda: [-1, 0.0001, 0],
}

function fit(
  s: { camera: THREE.PerspectiveCamera; orbit: OrbitControls },
  parts: Part[],
  view: ViewPreset,
) {
  const box = docBbox(parts)
  if (box.isEmpty()) return
  const center = box.getCenter(new THREE.Vector3())
  const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 0.01)
  const dist = (radius / Math.sin(THREE.MathUtils.degToRad(s.camera.fov / 2))) * 1.15
  const dir = new THREE.Vector3(...VIEW_DIRS[view]).normalize()
  s.camera.position.copy(center).addScaledVector(dir, dist)
  s.camera.near = Math.max(dist / 1000, 0.0005)
  s.camera.far = dist * 50
  s.camera.updateProjectionMatrix()
  s.orbit.target.copy(center)
  s.orbit.update()
}
