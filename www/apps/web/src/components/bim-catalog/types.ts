/** Produto retornado por GET /catalogos/:empresa/:slug com URLs absolutas */
export interface PocProduct {
  _id: string
  id: string
  nome: string
  serie: string
  specs: Record<string, string>
  curva: number[][] | null
  potencia: number
  conexoes: string
  /** URL absoluta: http://localhost:4000/geometrias/:id */
  geoUrl: string
  /** URL absoluta: http://localhost:4000/thumbs/:id  ou null se ainda não gerada */
  thumbUrl: string | null
}

export interface PocCatalog {
  id: string
  slug: string
  title: string
  manufacturer: string
  layout: string
  filters: string[]
  productCount: number
}
