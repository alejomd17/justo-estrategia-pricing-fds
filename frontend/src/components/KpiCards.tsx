import type { AdoptionSummary, MechanicRow } from '../types'

interface Props {
  summary: AdoptionSummary
  mechanics: MechanicRow[]
}

function sumaGanancia(rows: MechanicRow[]): number | null {
  const valores = rows.map((r) => r.GANANCIA_POR_ESTRATEGIA).filter((v): v is number => v != null)
  if (valores.length === 0) return null
  return valores.reduce((acc, v) => acc + v, 0)
}

function promedioTraccion(rows: MechanicRow[]): number | null {
  const valores = rows.map((r) => r.TRACCION_SKUS).filter((v): v is number => v != null && Number.isFinite(v))
  if (valores.length === 0) return null
  return valores.reduce((acc, v) => acc + v, 0) / valores.length
}

export default function KpiCards({ summary, mechanics }: Props) {
  const ganancia = sumaGanancia(mechanics)
  const traccion = promedioTraccion(mechanics)
  return (
    <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
      <div className="kpi-card">
        <div className="kpi-label">Planeado</div>
        <div className="kpi-value">{summary.total_planeado}</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-label">Adopcion</div>
        <div className="kpi-value">
          {summary.adopcion_pct === null ? 'N/D' : `${summary.adopcion_pct}%`}
        </div>
      </div>
      <div className="kpi-card">
        <div className="kpi-label">Ganancia por estrategia</div>
        <div className="kpi-value">
          {ganancia == null ? 'N/D' : `$${ganancia.toLocaleString('es-MX', { maximumFractionDigits: 0 })}`}
        </div>
      </div>
      <div className="kpi-card">
        <div className="kpi-label">Traccion promedio</div>
        <div className="kpi-value">{traccion == null ? 'N/D' : `${traccion.toFixed(2)}x`}</div>
      </div>
      {/* "Sin promo" sacada de la vista a proposito - un SKU sin ninguna
          oferta propuesta ni ejecutada no aporta a un post-mortem de
          campana (mismo criterio que performance_por_mecanica/top_skus en
          el backend). No borrada del todo: eventualmente se vuelve a
          mostrar en otro lado (ej. un panorama general aparte). */}
      {summary.por_origen
        .filter((row) => row.ORIGEN_CAMPANA !== 'Sin promo')
        .map((row) => (
          <div className="kpi-card" key={row.ORIGEN_CAMPANA}>
            <div className="kpi-label">{row.ORIGEN_CAMPANA}</div>
            <div className="kpi-value">
              {row.SKU_TIENDAS_CON_PROMO_REAL} / {row.SKU_TIENDAS}
            </div>
          </div>
        ))}
      <p style={{ width: '100%', fontSize: '0.85rem', opacity: 0.7 }}>
        Nota: la adopcion compara contra toda la ventana de la campana, no contra el dia
        especifico planeado para cada SKU (aproximado, no exacto).
      </p>
    </div>
  )
}
