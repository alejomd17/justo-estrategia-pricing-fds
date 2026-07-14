import type { DescuentoPlataformaSegmentoRow } from '../types'
import DataTable, { type Column } from './DataTable'

interface Props {
  rows: DescuentoPlataformaSegmentoRow[]
}

function numero(v: number | null | undefined): string {
  return v == null ? 'N/D' : v.toLocaleString('es-MX', { maximumFractionDigits: 0 })
}

const columns: Column<DescuentoPlataformaSegmentoRow>[] = [
  { key: 'MECANICA_EJECUTADA', label: 'Mecanica', render: (r) => r.MECANICA_EJECUTADA ?? 'Sin mecanica' },
  { key: 'MARKETPLACE', label: 'Plataforma', render: (r) => r.MARKETPLACE ?? 'N/D' },
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

export default function DescuentoPlataformaSegmentoTable({ rows }: Props) {
  return (
    <div>
      <DataTable columns={columns} rows={rows} pageSize={15} />
      <p style={{ fontSize: '0.85rem', opacity: 0.7, marginTop: '0.5rem' }}>
        Tabla granular a propósito (no gráfica) - ordena por columna para preguntas puntuales tipo
        "¿el 5x4 en Uber le fue mejor a Recurrentes o a Nuevos?".
      </p>
    </div>
  )
}
