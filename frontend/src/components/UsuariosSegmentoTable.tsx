import type { UsuariosSegmentoRow } from '../types'
import DataTable, { type Column } from './DataTable'

interface Props {
  rows: UsuariosSegmentoRow[]
}

function numero(v: number | null | undefined): string {
  return v == null ? 'N/D' : v.toLocaleString('es-MX', { maximumFractionDigits: 0 })
}

const columns: Column<UsuariosSegmentoRow>[] = [
  { key: 'SEGMENTO_USUARIO', label: 'Tipo de cliente', render: (r) => r.SEGMENTO_USUARIO ?? 'Sin dato' },
  { key: 'USUARIOS_DISTINTOS', label: 'Usuarios distintos', render: (r) => numero(r.USUARIOS_DISTINTOS) },
  {
    key: 'GMV_TOTAL',
    label: 'GMV',
    render: (r) => (r.GMV_TOTAL != null ? `$${numero(r.GMV_TOTAL)}` : 'N/D'),
  },
  {
    key: 'TICKET_PROMEDIO_USUARIO',
    label: 'Ticket promedio por usuario',
    render: (r) => (r.TICKET_PROMEDIO_USUARIO != null ? `$${numero(r.TICKET_PROMEDIO_USUARIO)}` : 'N/D'),
  },
]

export default function UsuariosSegmentoTable({ rows }: Props) {
  return (
    <div>
      <DataTable columns={columns} rows={rows} pageSize={10} />
      <p style={{ fontSize: '0.85rem', opacity: 0.7, marginTop: '0.5rem' }}>
        Usuarios distintos (no solo GMV/unidades, que pueden estar concentrados en pocas personas) y
        ticket promedio POR USUARIO (GMV / usuarios distintos) - el dato que faltaba para comparar
        segmentos sin el sesgo de tamaño de grupo.
      </p>
    </div>
  )
}
