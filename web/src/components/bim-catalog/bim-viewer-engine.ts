import * as THREE from 'three'

export interface GeoData {
  pos: number[]
  col: number[]
  idx?: number[]
}

const GEO_CACHE_MAX = 50
const geoCache = new Map<string, GeoData>()

export async function fetchGeo(url: string): Promise<GeoData> {
  if (geoCache.has(url)) return geoCache.get(url)!
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Failed to fetch geo: ${res.status}`)
  const data = await res.json()
  if (geoCache.size >= GEO_CACHE_MAX) {
    geoCache.delete(geoCache.keys().next().value!)
  }
  geoCache.set(url, data)
  return data
}

/** Remove a geometria do cache em memória — depois de um PUT /geometrias/:id. */
export function invalidateGeo(url: string): void {
  geoCache.delete(url)
}

export function buildScene(data: GeoData) {
  const scene = new THREE.Scene()
  const geom = new THREE.BufferGeometry()
  geom.setAttribute('position', new THREE.Float32BufferAttribute(data.pos, 3))
  const hasCol = data.col && data.col.length > 0
  if (hasCol)
    geom.setAttribute('color', new THREE.Float32BufferAttribute(data.col, 3))
  if (data.idx) geom.setIndex(data.idx)
  geom.computeVertexNormals()
  geom.computeBoundingBox()
  const center = geom.boundingBox!.getCenter(new THREE.Vector3())
  const size = geom.boundingBox!.getSize(new THREE.Vector3()).length()
  const mat = new THREE.MeshStandardMaterial({
    vertexColors: hasCol,
    color: hasCol ? 0xffffff : 0x8896aa,
    metalness: 0.25,
    roughness: 0.55,
  })
  const mesh = new THREE.Mesh(geom, mat)
  mesh.position.copy(center.negate())
  scene.add(mesh)
  scene.add(new THREE.AmbientLight(0xffffff, 0.7))
  const key = new THREE.DirectionalLight(0xffffff, 0.9)
  key.position.set(2, 3, 2)
  scene.add(key)
  const fill = new THREE.DirectionalLight(0xc8d8f0, 0.35)
  fill.position.set(-2, 1, -1)
  scene.add(fill)
  return { scene, size, geom, mat }
}

export function disposeScene(scene: THREE.Scene): void {
  scene.traverse((obj) => {
    if ((obj as THREE.Mesh).isMesh) {
      const mesh = obj as THREE.Mesh
      mesh.geometry.dispose()
      if (Array.isArray(mesh.material)) {
        mesh.material.forEach((m) => m.dispose())
      } else {
        ;(mesh.material as THREE.Material).dispose()
      }
    }
  })
}

let sharedRenderer: THREE.WebGLRenderer | null = null
export const thumbCache = new Map<string, string>()

const renderQueue: Array<() => Promise<void>> = []
const queuedIds = new Set<string>()
let isProcessingQueue = false

export function getSharedRenderer(): THREE.WebGLRenderer {
  if (!sharedRenderer) {
    sharedRenderer = new THREE.WebGLRenderer({
      antialias: false,
      alpha: false,
      preserveDrawingBuffer: true,
    })
  }
  return sharedRenderer
}

export async function renderThumbToDataUrl(
  id: string,
  geoData: GeoData,
  W: number,
  H: number
): Promise<string> {
  const renderer = getSharedRenderer()
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5))
  renderer.setSize(W, H, false)
  renderer.setClearColor(0xf3f4f6, 1)

  const { scene, size } = buildScene(geoData)
  const camera = new THREE.PerspectiveCamera(38, W / H, 0.001, 500)
  camera.position.set(size * 0.85, size * 0.32, size * 0.85)
  camera.lookAt(0, 0, 0)

  renderer.render(scene, camera)
  const dataUrl = renderer.domElement.toDataURL('image/jpeg', 0.88)
  thumbCache.set(id, dataUrl)
  disposeScene(scene)
  return dataUrl
}

export function enqueueRender(id: string, render: () => Promise<void>): void {
  if (thumbCache.has(id) || queuedIds.has(id)) return
  queuedIds.add(id)
  renderQueue.push(async () => {
    try {
      await render()
    } finally {
      queuedIds.delete(id)
    }
  })
  void processQueue()
}

async function processQueue(): Promise<void> {
  if (isProcessingQueue) return
  isProcessingQueue = true
  while (renderQueue.length > 0) {
    const fn = renderQueue.shift()!
    await fn()
  }
  isProcessingQueue = false
}
