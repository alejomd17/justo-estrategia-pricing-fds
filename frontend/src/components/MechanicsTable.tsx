import type { MechanicRow } from '../types'
import { storeName } from '../storeNames'
import DataTable, { type Column } from './DataTable'

interface Props {
  rows: MechanicRow[]
}

function numero(v: number | null | undefined): string {
  return v == null ? 'N/D' : v.toLocaleString('es-MX', { maximumFractionDigits: 0 })
}

function numeroCeil(v: number | null | undefined): string {
  return v == null ? 'N/D' : Math.ceil(v).toLocaleString('es-MX')
}

function ratio(v: number | null): string {
  return v == null ? 'N/D' : `${v.toFixed(2)}x`
}

const columns: Column<MechanicRow>[] = [
  { key: 'MECANICA_PLANEADA', label: 'Mecanica propuesta', render: (r) => r.MECANICA_PLANEADA ?? 'N/A' },
  { key: 'MECANICA_EJECUTADA', label: 'Mecanica real', render: (r) => r.MECANICA_EJECUTADA ?? 'Sin mecanica' },
  { key: 'ORIGEN_CAMPANA', label: 'Origen' },
  { key: 'STORE_ID', label: 'Bodega', render: (r) => storeName(r.STORE_ID) },
  { key: 'DEPARTAMENTO', label: 'Departamento', render: (r) => r.DEPARTAMENTO ?? 'N/D' },
  { key: 'CATEGORIA', label: 'Categoria', render: (r) => r.CATEGORIA ?? 'N/D' },
  { key: 'SKUS', label: 'SKUs' },
  { key: 'UNIDADES_TOTALES', label: 'Unidades (FDS)', render: (r) => numero(r.UNIDADES_TOTALES) },
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
  { key: 'UNIDADES_DIA', label: 'Unidades/dia', render: (r) => numero(r.UNIDADES_DIA) },
  { key: 'HISTORICO_UNIDADES_DIA', label: 'Historico unidades/dia', render: (r) => numeroCeil(r.HISTORICO_UNIDADES_DIA) },
  { key: 'TRACCION', label: 'Traccion', render: (r) => ratio(r.TRACCION) },
]

export default function MechanicsTable({ rows }: Props) {
  return (
    <div>
      <DataTable columns={columns} rows={rows} pageSize={10} />
      <p style={{ fontSize: '0.85rem', opacity: 0.7, marginTop: '0.5rem' }}>
        Traccion = unidades/dia de esta fila, divididas entre el ritmo normal real de esa
        categoria-bodega (historico, no el TAG_ROTACION estatico). Mayor a 1x = vendio por encima
        de su ritmo habitual.
      </p>
    </div>
  )
}
