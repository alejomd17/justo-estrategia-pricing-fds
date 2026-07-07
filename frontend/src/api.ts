import type { AdoptionSummary, Campaign, MechanicRow, RedemptionRow } from './types'

const BASE_URL = 'http://localhost:8000/api'

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`)
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`)
  return res.json()
}

export function fetchCampaigns(): Promise<Campaign[]> {
  return getJson('/campaigns')
}

export function fetchSummary(start: string, end: string): Promise<AdoptionSummary> {
  return getJson(`/campaigns/${start}/${end}/summary`)
}

export function fetchMechanics(start: string, end: string): Promise<MechanicRow[]> {
  return getJson(`/campaigns/${start}/${end}/mechanics`)
}

export function fetchRedemption(start: string, end: string): Promise<RedemptionRow[]> {
  return getJson(`/campaigns/${start}/${end}/redemption`)
}
