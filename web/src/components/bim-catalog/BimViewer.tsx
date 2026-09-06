'use client'

import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { fetchGeo, buildScene } from './bim-viewer-engine'

interface Props {
  geoUrl: string
  mode: 'thumbnail' | 'modal'
}

export function BimViewer({ geoUrl, mode }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const stateRef = useRef<{
    renderer: THREE.WebGLRenderer
    controls: OrbitControls
    raf: number
    geom: THREE.BufferGeometry
    mat: THREE.MeshStandardMaterial
  } | null>(null)
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    setLoadError(false)
    const canvas = canvasRef.current
    if (!canvas) return

    let cancelled = false
    const W =
      canvas.offsetWidth ||
      canvas.parentElement?.offsetWidth ||
      (mode === 'modal' ? 760 : 224)
    const H =
      canvas.offsetHeight ||
      canvas.parentElement?.offsetHeight ||
      (mode === 'modal' ? 300 : 162)
    const antialias = mode === 'modal'
    const pixelRatio = Math.min(
      window.devicePixelRatio,
      mode === 'modal' ? 2 : 1.5
    )

    fetchGeo(geoUrl)
      .then((data) => {
        if (cancelled || !canvas) return

        const renderer = new THREE.WebGLRenderer({
          canvas,
          antialias,
          alpha: false,
        })
        renderer.setPixelRatio(pixelRatio)
        renderer.setSize(W, H, false)
        renderer.setClearColor(0xf3f4f6, 1)

        const { scene, size, geom, mat } = buildScene(data)

        const camera = new THREE.PerspectiveCamera(
          mode === 'modal' ? 34 : 38,
          W / H,
          0.001,
          500
        )
        camera.position.set(size * 0.85, size * 0.32, size * 0.85)
        camera.lookAt(0, 0, 0)

        const controls = new OrbitControls(camera, canvas)
        controls.autoRotate = true
        controls.autoRotateSpeed = mode === 'modal' ? 0.7 : 1.2
        controls.enableDamping = true
        controls.dampingFactor = mode === 'modal' ? 0.06 : 0.07
        controls.enableZoom = mode === 'modal'
        controls.enablePan = false

        let raf = 0
        stateRef.current = { renderer, controls, raf, geom, mat }

        function animate() {
          raf = requestAnimationFrame(animate)
          if (stateRef.current) stateRef.current.raf = raf
          controls.update()
          renderer.render(scene, camera)
        }

        if (mode === 'modal') {
          animate()
        } else {
          controls.autoRotate = false
          renderer.render(scene, camera)

          let rotating = false

          function spin() {
            if (!rotating || cancelled) {
              raf = 0
              if (stateRef.current) stateRef.current.raf = 0
              return
            }
            raf = requestAnimationFrame(spin)
            if (stateRef.current) stateRef.current.raf = raf
            controls.update()
            renderer.render(scene, camera)
          }

          canvas.addEventListener('mouseenter', () => {
            controls.autoRotate = true
            rotating = true
            if (!raf) spin()
          })
          canvas.addEventListener('mouseleave', () => {
            controls.autoRotate = false
            rotating = false
            renderer.render(scene, camera)
          })
        }
      })
      .catch((err) => {
        console.warn('[BimViewer] Failed to load geo:', err)
        if (!cancelled) setLoadError(true)
      })

    return () => {
      cancelled = true
      if (stateRef.current) {
        cancelAnimationFrame(stateRef.current.raf)
        stateRef.current.controls.dispose()
        stateRef.current.geom.dispose()
        stateRef.current.mat.dispose()
        stateRef.current.renderer.dispose()
        stateRef.current = null
      }
    }
  }, [geoUrl, mode])

  if (loadError) {
    return (
      <div
        className={`w-full flex items-center justify-center bg-gray-100 text-gray-400 text-xs ${mode === 'modal' ? 'h-full' : 'h-[162px]'}`}
      >
        Erro ao carregar geometria
      </div>
    )
  }

  return (
    <canvas
      ref={canvasRef}
      className={`w-full block cursor-default ${mode === 'modal' ? 'h-full' : 'h-[162px]'}`}
    />
  )
}
