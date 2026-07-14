import type {
  CategoriaSegmentoRow,
  DepartamentoSegmentoRow,
  PlataformaSegmentoRow,
  SegmentoUsuarioRow,
  UsuariosSegmentoRow,
} from '../types'
import { COLORES_SEGMENTO, COLOR_DEFAULT } from '../colors'
import DataTable, { type Column } from './DataTable'
import PieChart from './PieChart'
import DimensionMetricsSection from './DimensionMetricsSection'
import CrossDimensionSection from './CrossDimensionSection'
import PlataformaSegmentoTable from './PlataformaSegmentoTable'
import UsuariosSegmentoTable from './UsuariosSegmentoTable'

interface Props {
  rows: SegmentoUsuarioRow[]
  categoriaSegmento: CategoriaSegmentoRow[]
  departamentoSegmento: DepartamentoSegmentoRow[]
  usuariosSegmento: UsuariosSegmentoRow[]
  plataformaSegmento: PlataformaSegmentoRow[]
}

function numero(v: number | null | undefined): string {
  return v == null ? 'N/D' : v.toLocaleString('es-MX', { maximumFractionDigits: 0 })
}

const moneda = (v: number) => `$${v.toLocaleString('es-MX', { maximumFractionDigits: 0 })}`
const unidades = (v: number) => v.toLocaleString('es-MX', { maximumFractionDigits: 0 })

const columns: Column<SegmentoUsuarioRow>[] = [
  { key: 'SEGMENTO_USUARIO', label: 'Tipo de cliente', render: (r) => r.SEGMENTO_USUARIO ?? 'Sin dato' },
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

// Todo lo de "tipo de cliente" vive aqui - tabla, pasteles (GMV/volumen),
// grid de 4 metricas, los 2 cruces (categoria/departamento x segmento), y
// las 2 tablas que cruzan con plataforma (usuarios distintos, plataforma x
// segmento) - todo junto para no interfolar con la seccion de plataforma.
export default function SegmentSection({
  rows,
  categoriaSegmento,
  departamentoSegmento,
  usuariosSegmento,
  plataformaSegmento,
}: Props) {
  const itemsGmv = rows
    .filter((r) => r.GMV_TOTAL != null)
    .sort((a, b) => (b.GMV_TOTAL as number) - (a.GMV_TOTAL as number))
    .map((r) => ({
      label: r.SEGMENTO_USUARIO ?? 'Sin dato',
      value: r.GMV_TOTAL as number,
      color: COLORES_SEGMENTO[r.SEGMENTO_USUARIO ?? ''] ?? COLOR_DEFAULT,
    }))

  const itemsVolumen = rows
    .filter((r) => r.UNIDADES_TOTALES != null)
    .sort((a, b) => (b.UNIDADES_TOTALES as number) - (a.UNIDADES_TOTALES as number))
    .map((r) => ({
      label: r.SEGMENTO_USUARIO ?? 'Sin dato',
      value: r.UNIDADES_TOTALES as number,
      color: COLORES_SEGMENTO[r.SEGMENTO_USUARIO ?? ''] ?? COLOR_DEFAULT,
    }))

  return (
    <div>
      <DataTable columns={columns} rows={rows} pageSize={10} />
      <p style={{ fontSize: '0.85rem', opacity: 0.7, margin: '0.5rem 0 1.5rem' }}>
        Tipo de cliente = clasificacion OFICIAL de Justo (USER_STATUS_ORDER_DELIVERED de MASTER_ORDER):
        Nuevo/Recurrente/Reactivado. "Sin dato" es una orden sin esa clasificacion (~37% en muestras
        revisadas, causa aun no confirmada) - no se descarta, se muestra como una fila mas.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem', marginBottom: '2rem' }}>
        {itemsGmv.length > 0 && <PieChart title="GMV por tipo de cliente" items={itemsGmv} formatValue={moneda} />}
        {itemsVolumen.length > 0 && (
          <PieChart title="Unidades por tipo de cliente" items={itemsVolumen} formatValue={unidades} />
        )}
      </div>

      {rows.length > 0 && (
        <div style={{ marginBottom: '2rem' }}>
          {/* Solo las 2 tasas - GMV/Unidades ya estan arriba como pastel con valor y % */}
          <DimensionMetricsSection rows={rows} labelKey="SEGMENTO_USUARIO" metricKeys={['TICKET_POR_UNIDAD', 'MARGEN_PROMEDIO']} />
        </div>
      )}

      {categoriaSegmento.length > 0 && (
        <div style={{ marginBottom: '2rem' }}>
          <h3 style={{ color: 'var(--text-h)', margin: '0 0 1rem' }}>Categoria x tipo de cliente</h3>
          <CrossDimensionSection
            rows={categoriaSegmento}
            labelKey="CATEGORIA"
            seriesKey="SEGMENTO_USUARIO"
            colorMap={COLORES_SEGMENTO}
          />
        </div>
      )}

      {departamentoSegmento.length > 0 && (
        <div style={{ marginBottom: '2rem' }}>
          <h3 style={{ color: 'var(--text-h)', margin: '0 0 1rem' }}>Departamento x tipo de cliente</h3>
          <CrossDimensionSection
            rows={departamentoSegmento}
            labelKey="DEPARTAMENTO"
            seriesKey="SEGMENTO_USUARIO"
            colorMap={COLORES_SEGMENTO}
          />
        </div>
      )}

      {usuariosSegmento.length > 0 && (
        <div style={{ marginBottom: '2rem' }}>
          <h3 style={{ color: 'var(--text-h)', margin: '0 0 1rem' }}>Usuarios distintos y ticket promedio por usuario</h3>
          <UsuariosSegmentoTable rows={usuariosSegmento} />
        </div>
      )}

      {plataformaSegmento.length > 0 && (
        <div>
          <h3 style={{ color: 'var(--text-h)', margin: '0 0 1rem' }}>Cruce plataforma x tipo de cliente</h3>
          <PlataformaSegmentoTable rows={plataformaSegmento} />
        </div>
      )}
    </div>
  )
}
