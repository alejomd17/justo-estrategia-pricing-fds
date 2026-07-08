import type { MechanicRow } from '../types'
import { storeName } from '../storeNames'
import HorizontalBarChart, { type BarItem } from './HorizontalBarChart'

interface Props {
  rows: MechanicRow[]
}

const GOOD = '#158158'
const WARN = '#ed561b'
const STORES = [9, 14]

// Categoria sola se repite (misma categoria, distinta mecanica propuesta) -
// se combina con la mecanica para que cada barra sea identificable.
function etiqueta(r: MechanicRow): string {
  const cat = r.CATEGORIA ?? 'N/D'
  const mecanica = r.MECANICA_PLANEADA ?? 'N/A'
  return `${cat} · ${mecanica}`
}

function topPor(rows: MechanicRow[], campo: keyof MechanicRow, n = 10, asc = false): BarItem[] {
  return rows
    .filter((r) => r[campo] != null)
    .sort((a, b) => (asc ? 1 : -1) * ((a[campo] as number) - (b[campo] as number)))
    .slice(0, n)
    .map((r) => ({ label: etiqueta(r), value: r[campo] as number }))
}

const moneda = (v: number) => `$${v.toLocaleString('es-MX', { maximumFractionDigits: 0 })}`
const unidades = (v: number) => v.toLocaleString('es-MX', { maximumFractionDigits: 0 })
const traccion = (v: number) => `${v.toFixed(2)}x`

const METRICAS = [
  { title: 'Top 10 por GMV', campo: 'GMV_TOTAL' as const, asc: false, color: GOOD, formatValue: moneda },
  { title: 'Top 10 por unidades vendidas', campo: 'UNIDADES_TOTALES' as const, asc: false, color: GOOD, formatValue: unidades },
  { title: 'Top 10 por traccion (mejor desempeño)', campo: 'TRACCION_SKUS' as const, asc: false, color: GOOD, formatValue: traccion },
  { title: 'Peores 10 por traccion (no funcionaron)', campo: 'TRACCION_SKUS' as const, asc: true, color: WARN, formatValue: traccion },
]

export default function TopChartsSection({ rows }: Props) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2.5rem' }}>
      {METRICAS.map((m) => (
        <div key={m.title}>
          <h3 style={{ margin: '0 0 0.75rem', color: 'var(--text-h)' }}>{m.title}</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
            {STORES.map((storeId) => (
              <HorizontalBarChart
                key={storeId}
                title={storeName(storeId)}
                items={topPor(
                  rows.filter((r) => r.STORE_ID === storeId),
                  m.campo,
                  10,
                  m.asc,
                )}
                color={m.color}
                formatValue={m.formatValue}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
