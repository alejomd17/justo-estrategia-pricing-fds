export interface Campaign {
  CAMPAIGN_START: string
  CAMPAIGN_END: string
}

export interface OrigenRow {
  ORIGEN_CAMPANA: string
  SKU_TIENDAS: number
  SKU_TIENDAS_CON_PROMO_REAL: number
}

export interface AdoptionSummary {
  por_origen: OrigenRow[]
  total_planeado: number
  adopcion_pct: number | null
}

export interface MechanicRow {
  MECANICA_PLANEADA: string | null
  MECANICA_EJECUTADA: string | null
  ORIGEN_CAMPANA: string
  DEPARTAMENTO: string | null
  CATEGORIA: string | null
  STORE_ID: number
  SKUS: number
  UNIDADES_TOTALES: number | null
  GMV_TOTAL: number | null
  MARGEN_PROMEDIO: number | null
  UNIDADES_DIA: number | null
  HISTORICO_UNIDADES_DIA_SKUS: number | null
  HISTORICO_UNIDADES_DIA_CATEGORIA: number | null
  TRACCION_SKUS: number | null
  TRACCION_CATEGORIA: number | null
  INGRESO_SUPUESTO_SIN_PROMO: number | null
  GANANCIA_POR_ESTRATEGIA: number | null
}

export interface MarketplaceRow {
  MARKETPLACE: string | null
  SKUS: number
  UNIDADES_TOTALES: number | null
  GMV_TOTAL: number | null
  MARGEN_PROMEDIO: number | null
  TICKET_POR_UNIDAD: number | null
}

export interface SegmentoUsuarioRow {
  SEGMENTO_USUARIO: string | null
  SKUS: number
  UNIDADES_TOTALES: number | null
  GMV_TOTAL: number | null
  MARGEN_PROMEDIO: number | null
  TICKET_POR_UNIDAD: number | null
}

export interface CategoriaPlataformaRow {
  CATEGORIA: string | null
  MARKETPLACE: string | null
  SKUS: number
  UNIDADES_TOTALES: number | null
  GMV_TOTAL: number | null
  MARGEN_PROMEDIO: number | null
  TICKET_POR_UNIDAD: number | null
}

export interface DepartamentoPlataformaRow {
  DEPARTAMENTO: string | null
  MARKETPLACE: string | null
  SKUS: number
  UNIDADES_TOTALES: number | null
  GMV_TOTAL: number | null
  MARGEN_PROMEDIO: number | null
  TICKET_POR_UNIDAD: number | null
}

export interface CategoriaSegmentoRow {
  CATEGORIA: string | null
  SEGMENTO_USUARIO: string | null
  SKUS: number
  UNIDADES_TOTALES: number | null
  GMV_TOTAL: number | null
  MARGEN_PROMEDIO: number | null
  TICKET_POR_UNIDAD: number | null
}

export interface DepartamentoSegmentoRow {
  DEPARTAMENTO: string | null
  SEGMENTO_USUARIO: string | null
  SKUS: number
  UNIDADES_TOTALES: number | null
  GMV_TOTAL: number | null
  MARGEN_PROMEDIO: number | null
  TICKET_POR_UNIDAD: number | null
}

export interface CategoriaRow {
  CATEGORIA: string | null
  SKUS: number
  UNIDADES_TOTALES: number | null
  GMV_TOTAL: number | null
  MARGEN_PROMEDIO: number | null
  TICKET_POR_UNIDAD: number | null
}

export interface DepartamentoRow {
  DEPARTAMENTO: string | null
  SKUS: number
  UNIDADES_TOTALES: number | null
  GMV_TOTAL: number | null
  MARGEN_PROMEDIO: number | null
  TICKET_POR_UNIDAD: number | null
}

export interface PlataformaSegmentoRow {
  MARKETPLACE: string | null
  SEGMENTO_USUARIO: string | null
  SKUS: number
  UNIDADES_TOTALES: number | null
  GMV_TOTAL: number | null
  MARGEN_PROMEDIO: number | null
}

export interface UsuariosSegmentoRow {
  SEGMENTO_USUARIO: string | null
  USUARIOS_DISTINTOS: number
  GMV_TOTAL: number | null
  TICKET_PROMEDIO_USUARIO: number | null
}

export interface DescuentoPlataformaSegmentoRow {
  MECANICA_EJECUTADA: string | null
  MARKETPLACE: string | null
  SEGMENTO_USUARIO: string | null
  SKUS: number
  UNIDADES_TOTALES: number | null
  GMV_TOTAL: number | null
  MARGEN_PROMEDIO: number | null
}

export interface EngancheSegmentoRow {
  SEGMENTO_USUARIO: string | null
  GRUPO: string
  USUARIOS: number
  GMV_TOTAL: number | null
  GMV_CAMPANA: number | null
  TICKET_TOTAL_PROMEDIO: number | null
  GASTO_CAMPANA_PROMEDIO: number | null
  GASTO_RESTO_PROMEDIO: number | null
  PCT_CAMPANA_EN_TICKET: number | null
}

export interface EngancheOrdenRow {
  GRUPO: string
  ORDENES: number
  GMV_TOTAL: number | null
  GMV_CAMPANA: number | null
  TICKET_PROMEDIO_ORDEN: number | null
  GASTO_CAMPANA_PROMEDIO: number | null
  GASTO_RESTO_PROMEDIO: number | null
  PCT_CAMPANA_EN_TICKET: number | null
}

export interface EngancheRow {
  GRUPO: string
  USUARIOS: number
  GMV_TOTAL: number | null
  GMV_CAMPANA: number | null
  TICKET_TOTAL_PROMEDIO: number | null
  GASTO_CAMPANA_PROMEDIO: number | null
  GASTO_RESTO_PROMEDIO: number | null
  PCT_CAMPANA_EN_TICKET: number | null
}

export interface TopSkuRow {
  SKU: number
  STORE_ID: number
  DEPARTAMENTO: string | null
  CATEGORIA: string | null
  MECANICA_EJECUTADA: string | null
  ORIGEN_CAMPANA: string
  UNIDADES_TOTALES: number | null
  GMV_TOTAL: number | null
}

export interface StoreOption {
  id: number
  nombre: string
}

export interface Filters {
  departamentos: string[]
  categorias: string[]
  stores: StoreOption[]
  origenes: string[]
  adopciones: string[]
  marketplaces: string[]
  segmentos_usuario: string[]
  mecanicas: string[]
}

export interface CampaignFilters {
  departamento?: string
  categoria?: string
  store_id?: number
  origen?: string
  adopcion?: string
  marketplace?: string
  segmento_usuario?: string
  mecanica?: string
}
