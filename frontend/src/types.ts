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
}

export interface CampaignFilters {
  departamento?: string
  categoria?: string
  store_id?: number
  origen?: string
  adopcion?: string
}
