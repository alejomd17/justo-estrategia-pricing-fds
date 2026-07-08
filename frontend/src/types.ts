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
  HISTORICO_UNIDADES_DIA: number | null
  TRACCION: number | null
}

export interface RedemptionRow {
  BULK_STRATEGY: string | null
  BULK_RULE_BUY: number | null
  BULK_RULE_PAY: number | null
  UNIDADES_TOTALES: number
  UNIDADES_CON_DESCUENTO: number
  TIER: string | null
  REDENCION_REAL: number | null
  REDENCION_SUPUESTA: number | null
  DIFERENCIA: number | null
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
}

export interface CampaignFilters {
  departamento?: string
  categoria?: string
  store_id?: number
  origen?: string
}
