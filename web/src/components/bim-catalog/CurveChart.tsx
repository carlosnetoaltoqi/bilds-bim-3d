'use client'

import { PocProduct } from './types'

interface Props {
  curva: PocProduct['curva']
  width?: number
  height?: number
}

export function CurveChart({ curva, width = 300, height = 180 }: Props) {
  if (!curva || curva.length === 0) {
    return <p className="text-xs text-gray-500">Curva indisponível</p>
  }

  const pl = 40, pr = 12, pt = 14, pb = 36
  const cW = width - pl - pr
  const cH = height - pt - pb
  const qMax = Math.max(...curva.map((p) => p[0]!)) * 1.1
  const hMax = Math.max(...curva.map((p) => p[1]!)) * 1.18

  const tx = (q: number) => pl + (q / qMax) * cW
  const ty = (h: number) => height - pb - (h / hMax) * cH

  const gridLines = [0.25, 0.5, 0.75, 1].map((f) => {
    const yy = ty(hMax * f)
    return (
      <g key={f}>
        <line x1={pl} y1={yy} x2={width - pr} y2={yy} stroke="#E5E7EB" strokeWidth={1} />
        <text x={pl - 5} y={yy + 3} textAnchor="end" fill="#6B7280" fontSize={9}>
          {Math.round(hMax * f)}
        </text>
      </g>
    )
  })

  const pathD =
    'M' + curva.map((p) => `${tx(p[0]!).toFixed(1)},${ty(p[1]!).toFixed(1)}`).join('L')
  const last = curva[curva.length - 1]!
  const first = curva[0]!
  const areaD =
    pathD +
    `L${tx(last[0]!).toFixed(1)},${height - pb}L${tx(first[0]!).toFixed(1)},${height - pb}Z`

  const hasEff = first[3] != null
  const effMax = hasEff
    ? Math.max(Math.max(...curva.map((p) => p[3]!)) * 1.15, 1e-9)
    : 65
  const tyEff = (e: number) => height - pb - (e / effMax) * cH
  const effD = hasEff
    ? 'M' + curva.map((p) => `${tx(p[0]!).toFixed(1)},${tyEff(p[3]!).toFixed(1)}`).join('L')
    : ''

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" xmlns="http://www.w3.org/2000/svg">
      <rect x={pl} y={pt} width={cW} height={cH} fill="#FAFBFB" rx={2} />
      {gridLines}
      <path d={areaD} fill="rgba(30,64,175,0.1)" />
      <path d={pathD} fill="none" stroke="#1E40AF" strokeWidth={2} strokeLinejoin="round" />
      {hasEff && (
        <path d={effD} fill="none" stroke="#9CA3AF" strokeWidth={1.5} strokeDasharray="4,3" />
      )}
      <text x={pl + cW / 2} y={height - 2} textAnchor="middle" fill="#9CA3AF" fontSize={9}>
        Q (m³/h)
      </text>
      <text
        x={8}
        y={pt + cH / 2}
        textAnchor="middle"
        fill="#9CA3AF"
        fontSize={9}
        transform={`rotate(-90,8,${pt + cH / 2})`}
      >
        H (mca)
      </text>
    </svg>
  )
}
