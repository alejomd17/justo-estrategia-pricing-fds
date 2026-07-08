import type { TopSkuRow } from '../types'
import { storeName } from '../storeNames'
import DataTable, { type Column } from './DataTable'

interface Props {
  rows: TopSkuRow[]
}

function numero(v: number | null | undefined): string {
  return v == null ? 'N/D' : v.toLocaleString('es-MX', { maximumFractionDigits: 0 })
}

const columns: Column<TopSkuRow>[] = [
  { key: 'SKU', label: 'SKU' },
  { key: 'STORE_ID', label: 'Bodega', render: (r) => storeName(r.STORE_ID) },
  { key: 'DEPARTAMENTO', label: 'Departamento', render: (r) => r.DEPARTAMENTO ?? 'N/D' },
  { key: 'CATEGORIA', label: 'Categoria', render: (r) => r.CATEGORIA ?? 'N/D' },
  { key: 'MECANICA_EJECUTADA', label: 'Mecanica', render: (r) => r.MECANICA_EJECUTADA ?? 'Sin mecanica' },
  { key: 'ORIGEN_CAMPANA', label: 'Origen' },
  { key: 'UNIDADES_TOTALES', label: 'Unidades', render: (r) => numero(r.UNIDADES_TOTALES) },
  {
    key: 'GMV_TOTAL',
    label: 'GMV',
    render: (r) => (r.GMV_TOTAL != null ? `$${numero(r.GMV_TOTAL)}` : 'N/D'),
  },
]

export default function TopSkusTable({ rows }: Props) {
  return <DataTable columns={columns} rows={rows} pageSize={10} />
}
