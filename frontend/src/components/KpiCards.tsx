import type { AdoptionSummary } from '../types'

interface Props {
  summary: AdoptionSummary
}

export default function KpiCards({ summary }: Props) {
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
      {summary.por_origen.map((row) => (
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
