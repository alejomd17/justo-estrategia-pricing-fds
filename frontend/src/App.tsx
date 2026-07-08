import { useEffect, useState } from 'react'
import { fetchCampaigns, fetchFilters, fetchMechanics, fetchRedemption, fetchSummary, fetchTopSkus } from './api'
import type {
  AdoptionSummary,
  Campaign,
  CampaignFilters,
  Filters,
  MechanicRow,
  RedemptionRow,
  TopSkuRow,
} from './types'
import CampaignSelector from './components/CampaignSelector'
import FilterBar from './components/FilterBar'
import KpiCards from './components/KpiCards'
import MechanicsTable from './components/MechanicsTable'
import RedemptionTable from './components/RedemptionTable'
import TopSkusTable from './components/TopSkusTable'
import './App.css'

function App() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [selected, setSelected] = useState<Campaign | null>(null)
  const [filters, setFilters] = useState<Filters | null>(null)
  const [campaignFilters, setCampaignFilters] = useState<CampaignFilters>({})
  const [summary, setSummary] = useState<AdoptionSummary | null>(null)
  const [mechanics, setMechanics] = useState<MechanicRow[]>([])
  const [redemption, setRedemption] = useState<RedemptionRow[]>([])
  const [topSkus, setTopSkus] = useState<TopSkuRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchCampaigns()
      .then((cs) => {
        // El backend serializa fechas como ISO datetime completo
        // (2026-07-03T00:00:00.000) - se normaliza a YYYY-MM-DD aqui una
        // sola vez, para que el selector y las URLs de la API usen fechas
        // limpias en toda la app.
        const clean = cs.map((c) => ({
          CAMPAIGN_START: c.CAMPAIGN_START.slice(0, 10),
          CAMPAIGN_END: c.CAMPAIGN_END.slice(0, 10),
        }))
        setCampaigns(clean)
        if (clean.length > 0) setSelected(clean[0])
      })
      .catch((e) => setError(String(e)))
    fetchFilters()
      .then(setFilters)
      .catch((e) => setError(String(e)))
  }, [])

  // Depende solo de la campana elegida, NO de los filtros - redencion viene
  // de FACT_FULFILLMENT_LINE directo, ningun filtro (departamento/categoria/
  // bodega/origen) le aplica. Antes se volvia a pedir en cada cambio de
  // filtro sin necesidad - el mismo query pesado, repetido para nada.
  useEffect(() => {
    if (!selected) return
    let ignore = false
    fetchRedemption(selected.CAMPAIGN_START, selected.CAMPAIGN_END)
      .then((r) => !ignore && setRedemption(r))
      .catch((e) => !ignore && setError(String(e)))
    return () => {
      ignore = true
    }
  }, [selected])

  useEffect(() => {
    if (!selected) return
    // `ignore` evita que una respuesta vieja (ej. el fetch inicial sin
    // filtro, si tarda mas que el siguiente) pise el resultado de una
    // corrida mas reciente (ej. despues de elegir un filtro) - sin esto,
    // cambiar el filtro rapido podia mostrar datos sin filtrar.
    let ignore = false
    setLoading(true)
    setError(null)
    Promise.all([
      fetchSummary(selected.CAMPAIGN_START, selected.CAMPAIGN_END, campaignFilters),
      fetchMechanics(selected.CAMPAIGN_START, selected.CAMPAIGN_END, campaignFilters),
      fetchTopSkus(selected.CAMPAIGN_START, selected.CAMPAIGN_END, campaignFilters),
    ])
      .then(([s, m, t]) => {
        if (ignore) return
        setSummary(s)
        setMechanics(m)
        setTopSkus(t)
      })
      .catch((e) => !ignore && setError(String(e)))
      .finally(() => !ignore && setLoading(false))
    return () => {
      ignore = true
    }
  }, [selected, campaignFilters])

  return (
    <div style={{ padding: '2rem', maxWidth: '1100px', margin: '0 auto' }}>
      <h1>Post-mortem de promos FDS</h1>

      {campaigns.length === 0 && !error && <p>Cargando campanas...</p>}
      {campaigns.length > 0 && (
        <CampaignSelector campaigns={campaigns} selected={selected} onChange={setSelected} />
      )}

      {filters && <FilterBar filters={filters} value={campaignFilters} onChange={setCampaignFilters} />}

      {error && <p className="error-banner">Error: {error}</p>}
      {loading && <p>Actualizando con el filtro nuevo...</p>}

      {/* opacity baja mientras `loading` para que se note que esto es la
          version VIEJA (previa al filtro actual), no que el filtro no hizo nada */}
      <div style={{ opacity: loading ? 0.4 : 1, transition: 'opacity 0.15s' }}>
        {summary && (
          <section style={{ marginTop: '1.5rem' }}>
            <h2>Resumen</h2>
            <KpiCards summary={summary} />
          </section>
        )}

        {mechanics.length > 0 && (
          <section style={{ marginTop: '1.5rem' }}>
            <h2>Performance FDS</h2>
            <MechanicsTable rows={mechanics} />
          </section>
        )}

        {topSkus.length > 0 && (
          <section style={{ marginTop: '1.5rem' }}>
            <h2>SKUs mas vendidos FDS</h2>
            <TopSkusTable rows={topSkus} />
          </section>
        )}

        {redemption.length > 0 && (
          <section style={{ marginTop: '1.5rem' }}>
            <h2>Validacion de redencion</h2>
            <RedemptionTable rows={redemption} />
          </section>
        )}
      </div>
    </div>
  )
}

export default App
