import type {
  AdoptionSummary,
  Campaign,
  CampaignFilters,
  CategoriaPlataformaRow,
  CategoriaSegmentoRow,
  DepartamentoPlataformaRow,
  DepartamentoSegmentoRow,
  DescuentoPlataformaSegmentoRow,
  Filters,
  MarketplaceRow,
  MechanicRow,
  PlataformaSegmentoRow,
  SegmentoUsuarioRow,
  TopSkuRow,
  UsuariosSegmentoRow,
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
  if (filters.adopcion) params.set('adopcion', filters.adopcion)
  if (filters.marketplace) params.set('marketplace', filters.marketplace)
  if (filters.segmento_usuario) params.set('segmento_usuario', filters.segmento_usuario)
  if (filters.mecanica) params.set('mecanica', filters.mecanica)
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

export function fetchTopSkus(start: string, end: string, filters?: CampaignFilters): Promise<TopSkuRow[]> {
  return getJson(`/campaigns/${start}/${end}/top-skus`, filters)
}

export function fetchMarketplace(start: string, end: string, filters?: CampaignFilters): Promise<MarketplaceRow[]> {
  return getJson(`/campaigns/${start}/${end}/marketplace`, filters)
}

export function fetchSegmentoUsuario(start: string, end: string, filters?: CampaignFilters): Promise<SegmentoUsuarioRow[]> {
  return getJson(`/campaigns/${start}/${end}/segmento-usuario`, filters)
}

// Nota: no hay fetchCategoria/fetchDepartamento - esos rollups se calculan
// en el cliente desde /mechanics (ver rollups.ts). Los endpoints /categoria
// y /departamento siguen existiendo en el backend para el notebook/curl.
export function fetchPlataformaSegmento(
  start: string,
  end: string,
  filters?: CampaignFilters,
): Promise<PlataformaSegmentoRow[]> {
  return getJson(`/campaigns/${start}/${end}/plataforma-segmento`, filters)
}

export function fetchUsuariosSegmento(
  start: string,
  end: string,
  filters?: CampaignFilters,
): Promise<UsuariosSegmentoRow[]> {
  return getJson(`/campaigns/${start}/${end}/usuarios-segmento`, filters)
}

export function fetchDescuentoPlataformaSegmento(
  start: string,
  end: string,
  filters?: CampaignFilters,
): Promise<DescuentoPlataformaSegmentoRow[]> {
  return getJson(`/campaigns/${start}/${end}/descuento-plataforma-segmento`, filters)
}

export function fetchCategoriaPlataforma(
  start: string,
  end: string,
  filters?: CampaignFilters,
): Promise<CategoriaPlataformaRow[]> {
  return getJson(`/campaigns/${start}/${end}/categoria-plataforma`, filters)
}

export function fetchDepartamentoPlataforma(
  start: string,
  end: string,
  filters?: CampaignFilters,
): Promise<DepartamentoPlataformaRow[]> {
  return getJson(`/campaigns/${start}/${end}/departamento-plataforma`, filters)
}

export function fetchCategoriaSegmento(
  start: string,
  end: string,
  filters?: CampaignFilters,
): Promise<CategoriaSegmentoRow[]> {
  return getJson(`/campaigns/${start}/${end}/categoria-segmento`, filters)
}

export function fetchDepartamentoSegmento(
  start: string,
  end: string,
  filters?: CampaignFilters,
): Promise<DepartamentoSegmentoRow[]> {
  return getJson(`/campaigns/${start}/${end}/departamento-segmento`, filters)
}
