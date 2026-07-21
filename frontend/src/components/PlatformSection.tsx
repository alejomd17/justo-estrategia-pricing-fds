import type { CategoriaPlataformaRow, DepartamentoPlataformaRow, MarketplaceRow } from '../types'
import { COLORES_PLATAFORMA, COLOR_DEFAULT } from '../colors'
import DataTable, { type Column } from './DataTable'
import PieChart from './PieChart'
import DimensionMetricsSection from './DimensionMetricsSection'
import CrossDimensionSection from './CrossDimensionSection'

interface Props {
  rows: MarketplaceRow[]
  categoriaPlataforma: CategoriaPlataformaRow[]
  departamentoPlataforma: DepartamentoPlataformaRow[]
}

function numero(v: number | null | undefined): string {
  return v == null ? 'N/D' : v.toLocaleString('es-MX', { maximumFractionDigits: 0 })
}

const moneda = (v: number) => `$${v.toLocaleString('es-MX', { maximumFractionDigits: 0 })}`
const unidades = (v: number) => v.toLocaleString('es-MX', { maximumFractionDigits: 0 })

const columns: Column<MarketplaceRow>[] = [
  { key: 'MARKETPLACE', label: 'Plataforma', render: (r) => r.MARKETPLACE ?? 'N/D' },
  { key: 'SKUS', label: 'SKUs' },
  { key: 'UNIDADES_TOTALES', label: 'Unidades', render: (r) => numero(r.UNIDADES_TOTALES) },
  {
    key: 'GMV_TOTAL',
    label: 'GMV',
    render: (r) => (r.GMV_TOTAL != null ? `$${numero(r.GMV_TOTAL)}` : 'N/D'),
  },
  {
    key: 'MARGEN_PROMEDIO',
    label: 'Margen prom.',
    render: (r) => (r.MARGEN_PROMEDIO != null ? `${r.MARGEN_PROMEDIO.toFixed(1)}%` : 'N/D'),
  },
]

// Todo lo de "plataforma" vive aqui - tabla, pasteles (GMV/volumen - los
// unicos 2 que son "parte de un todo", ticket/margen son tasas y no
// suman 100%, se quedan como barras en el grid de abajo), grid de 4
// metricas, y los 2 cruces (categoria/departamento x plataforma) - todo
// junto para no interfolar plataforma y cliente (ver SegmentSection.tsx).
export default function PlatformSection({ rows, categoriaPlataforma, departamentoPlataforma }: Props) {
  const itemsGmv = rows
    .filter((r) => r.GMV_TOTAL != null)
    .sort((a, b) => (b.GMV_TOTAL as number) - (a.GMV_TOTAL as number))
    .map((r) => ({ label: r.MARKETPLACE ?? 'N/D', value: r.GMV_TOTAL as number, color: COLORES_PLATAFORMA[r.MARKETPLACE ?? ''] ?? COLOR_DEFAULT }))

  const itemsVolumen = rows
    .filter((r) => r.UNIDADES_TOTALES != null)
    .sort((a, b) => (b.UNIDADES_TOTALES as number) - (a.UNIDADES_TOTALES as number))
    .map((r) => ({ label: r.MARKETPLACE ?? 'N/D', value: r.UNIDADES_TOTALES as number, color: COLORES_PLATAFORMA[r.MARKETPLACE ?? ''] ?? COLOR_DEFAULT }))

  return (
    <div>
      <DataTable columns={columns} rows={rows} pageSize={10} />
      <p style={{ fontSize: '0.85rem', opacity: 0.7, margin: '0.5rem 0 1.5rem' }}>
        Plataforma = MARKETPLACE de MASTER_ORDERLINE (justo/express/uber/rappi/didi) - responde en cual
        canal vendio mas la campaña. Pastel solo para GMV/Volumen (son "parte de un todo" - suman
        100%); ticket por unidad y margen son tasas/promedios, no tienen lectura de pastel, se
        muestran como barras abajo.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem', marginBottom: '2rem' }}>
        {itemsGmv.length > 0 && <PieChart title="GMV por plataforma" items={itemsGmv} formatValue={moneda} />}
        {itemsVolumen.length > 0 && <PieChart title="Unidades por plataforma" items={itemsVolumen} formatValue={unidades} />}
      </div>

      {rows.length > 0 && (
        <div style={{ marginBottom: '2rem' }}>
          {/* Solo las 2 tasas - GMV/Unidades ya estan arriba como pastel con valor y % */}
          <DimensionMetricsSection rows={rows} labelKey="MARKETPLACE" metricKeys={['TICKET_POR_UNIDAD', 'MARGEN_PROMEDIO']} />
        </div>
      )}

      {categoriaPlataforma.length > 0 && (
        <div style={{ marginBottom: '2rem' }}>
          <h3 style={{ color: 'var(--text-h)', margin: '0 0 1rem' }}>Categoria x plataforma</h3>
          <CrossDimensionSection
            rows={categoriaPlataforma}
            labelKey="CATEGORIA"
            seriesKey="MARKETPLACE"
            colorMap={COLORES_PLATAFORMA}
          />
        </div>
      )}

      {departamentoPlataforma.length > 0 && (
        <div>
          <h3 style={{ color: 'var(--text-h)', margin: '0 0 1rem' }}>Departamento x plataforma</h3>
          <CrossDimensionSection
            rows={departamentoPlataforma}
            labelKey="DEPARTAMENTO"
            seriesKey="MARKETPLACE"
            colorMap={COLORES_PLATAFORMA}
          />
        </div>
      )}
    </div>
  )
}
