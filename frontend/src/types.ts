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
  MECANICA_EJECUTADA: string | null
  ORIGEN_CAMPANA: string
  SKUS: number
  UNIDADES_TOTALES: number | null
  GMV_TOTAL: number | null
  MARGEN_PROMEDIO: number | null
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
