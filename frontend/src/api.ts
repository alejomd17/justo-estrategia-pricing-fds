import type {
  AdoptionSummary,
  Campaign,
  CampaignFilters,
  Filters,
  MechanicRow,
  RedemptionRow,
  TopSkuRow,
} from './types'

const BASE_URL = 'http://localhost:8000/api'

async function getJson<T>(path: string, filters?: CampaignFilters): Promise<T> {
  const query = filters ? toQueryString(filters) : ''
  const res = await fetch(`${BASE_URL}${path}${query}`)
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`)
  return res.json()
}

function toQueryString(filters: CampaignFilters): string {
  const params = new URLSearchParams()
  if (filters.departamento) params.set('departamento', filters.departamento)
  if (filters.categoria) params.set('categoria', filters.categoria)
  if (filters.store_id) params.set('store_id', String(filters.store_id))
  if (filters.origen) params.set('origen', filters.origen)
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export function fetchCampaigns(): Promise<Campaign[]> {
  return getJson('/campaigns')
}

export function fetchFilters(): Promise<Filters> {
  return getJson('/filters')
}

export function fetchSummary(start: string, end: string, filters?: CampaignFilters): Promise<AdoptionSummary> {
  return getJson(`/campaigns/${start}/${end}/summary`, filters)
}

export function fetchMechanics(start: string, end: string, filters?: CampaignFilters): Promise<MechanicRow[]> {
  return getJson(`/campaigns/${start}/${end}/mechanics`, filters)
}

export function fetchRedemption(start: string, end: string): Promise<RedemptionRow[]> {
  return getJson(`/campaigns/${start}/${end}/redemption`)
}

export function fetchTopSkus(start: string, end: string, filters?: CampaignFilters): Promise<TopSkuRow[]> {
  return getJson(`/campaigns/${start}/${end}/top-skus`, filters)
}
