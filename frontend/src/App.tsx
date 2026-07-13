import { useEffect, useState } from 'react'
import { fetchCampaigns, fetchFilters, fetchMechanics, fetchSummary, fetchTopSkus } from './api'
import type {
  AdoptionSummary,
  Campaign,
  CampaignFilters,
  Filters,
  MechanicRow,
  TopSkuRow,
} from './types'
import CampaignSelector from './components/CampaignSelector'
import FilterBar from './components/FilterBar'
import KpiCards from './components/KpiCards'
import MechanicsTable from './components/MechanicsTable'
import TopSkusTable from './components/TopSkusTable'
import TopChartsSection from './components/TopChartsSection'
import './App.css'

function App() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [selected, setSelected] = useState<Campaign | null>(null)
  const [filters, setFilters] = useState<Filters | null>(null)
  // Por defecto solo lo nuestro (WKND) y lo que si se ejecuto (con_mecanica) -
  // el usuario puede volver a "Todos" desde el FilterBar si quiere ver todo.
  const [campaignFilters, setCampaignFilters] = useState<CampaignFilters>({
    origen: 'WKND',
    adopcion: 'con_mecanica',
  })
  const [summary, setSummary] = useState<AdoptionSummary | null>(null)
  const [mechanics, setMechanics] = useState<MechanicRow[]>([])
  const [topSkus, setTopSkus] = useState<TopSkuRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Fila de "Performance FDS" seleccionada por click, para filtrar la tabla
  // de SKUs mas vendidos por esa misma mecanica/origen/departamento/
  // categoria/bodega - null = sin filtro, se ve todo.
  const [selectedGroup, setSelectedGroup] = useState<MechanicRow | null>(null)

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

  useEffect(() => {
    if (!selected) return
    // `ignore` evita que una respuesta vieja (ej. el fetch inicial sin
    // filtro, si tarda mas que el siguiente) pise el resultado de una
    // corrida mas reciente (ej. despues de elegir un filtro) - sin esto,
    // cambiar el filtro rapido podia mostrar datos sin filtrar.
    let ignore = false
    setLoading(true)
    setError(null)
    setSelectedGroup(null) // la campana/filtro cambio - la fila seleccionada de antes ya no aplica
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

  // TopSkuRow no trae MECANICA_PLANEADA, asi que el match es por las 5
  // dimensiones que si comparte con MechanicRow (mismo grano que agrupa
  // performance_por_mecanica, menos la mecanica propuesta).
  function coincideConGrupo(sku: TopSkuRow, grupo: MechanicRow): boolean {
    return (
      sku.STORE_ID === grupo.STORE_ID &&
      sku.DEPARTAMENTO === grupo.DEPARTAMENTO &&
      sku.CATEGORIA === grupo.CATEGORIA &&
      sku.MECANICA_EJECUTADA === grupo.MECANICA_EJECUTADA &&
      sku.ORIGEN_CAMPANA === grupo.ORIGEN_CAMPANA
    )
  }

  const topSkusFiltrados = selectedGroup ? topSkus.filter((s) => coincideConGrupo(s, selectedGroup)) : topSkus

  return (
    <div style={{ padding: '2rem', maxWidth: '1800px', margin: '0 auto' }}>
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
            <KpiCards summary={summary} mechanics={mechanics} />
          </section>
        )}

        {mechanics.length > 0 && (
          <section style={{ marginTop: '1.5rem' }}>
            <h2>Performance FDS</h2>
            <MechanicsTable
              rows={mechanics}
              onRowClick={(row) => setSelectedGroup((prev) => (prev === row ? null : row))}
              isRowSelected={(row) => row === selectedGroup}
            />
          </section>
        )}

        {mechanics.length > 0 && (
          <section style={{ marginTop: '1.5rem' }}>
            <h2>Tops de la campana</h2>
            <TopChartsSection rows={mechanics} />
          </section>
        )}

        {topSkus.length > 0 && (
          <section style={{ marginTop: '1.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <h2 style={{ margin: 0 }}>SKUs mas vendidos FDS</h2>
              {selectedGroup && (
                <>
                  <span style={{ fontSize: '0.85rem', opacity: 0.8 }}>
                    Filtrado por: {selectedGroup.CATEGORIA ?? 'N/D'} · {selectedGroup.MECANICA_EJECUTADA ?? 'Sin mecanica'} ·{' '}
                    {selectedGroup.ORIGEN_CAMPANA}
                  </span>
                  <button onClick={() => setSelectedGroup(null)}>Quitar filtro</button>
                </>
              )}
            </div>
            <TopSkusTable rows={topSkusFiltrados} />
          </section>
        )}
      </div>
    </div>
  )
}

export default App
