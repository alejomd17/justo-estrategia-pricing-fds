import { useEffect, useState } from 'react'
import { fetchCampaigns, fetchMechanics, fetchRedemption, fetchSummary } from './api'
import type { AdoptionSummary, Campaign, MechanicRow, RedemptionRow } from './types'
import CampaignSelector from './components/CampaignSelector'
import KpiCards from './components/KpiCards'
import MechanicsTable from './components/MechanicsTable'
import RedemptionTable from './components/RedemptionTable'
import './App.css'

function App() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [selected, setSelected] = useState<Campaign | null>(null)
  const [summary, setSummary] = useState<AdoptionSummary | null>(null)
  const [mechanics, setMechanics] = useState<MechanicRow[]>([])
  const [redemption, setRedemption] = useState<RedemptionRow[]>([])
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
  }, [])

  useEffect(() => {
    if (!selected) return
    setLoading(true)
    setError(null)
    Promise.all([
      fetchSummary(selected.CAMPAIGN_START, selected.CAMPAIGN_END),
      fetchMechanics(selected.CAMPAIGN_START, selected.CAMPAIGN_END),
      fetchRedemption(selected.CAMPAIGN_START, selected.CAMPAIGN_END),
    ])
      .then(([s, m, r]) => {
        setSummary(s)
        setMechanics(m)
        setRedemption(r)
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [selected])

  return (
    <div style={{ padding: '2rem', maxWidth: '1000px', margin: '0 auto' }}>
      <h1>Post-mortem de campanas FDS</h1>

      {campaigns.length === 0 && !error && <p>Cargando campanas...</p>}
      {campaigns.length > 0 && (
        <CampaignSelector campaigns={campaigns} selected={selected} onChange={setSelected} />
      )}

      {error && <p style={{ color: 'red' }}>Error: {error}</p>}
      {loading && <p>Cargando datos de la campana...</p>}

      {summary && (
        <section style={{ marginTop: '1.5rem' }}>
          <h2>Resumen</h2>
          <KpiCards summary={summary} />
        </section>
      )}

      {mechanics.length > 0 && (
        <section style={{ marginTop: '1.5rem' }}>
          <h2>Performance por mecanica</h2>
          <MechanicsTable rows={mechanics} />
        </section>
      )}

      {redemption.length > 0 && (
        <section style={{ marginTop: '1.5rem' }}>
          <h2>Validacion de redencion</h2>
          <RedemptionTable rows={redemption} />
        </section>
      )}
    </div>
  )
}

export default App
