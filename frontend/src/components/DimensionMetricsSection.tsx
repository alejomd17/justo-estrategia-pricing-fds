import HorizontalBarChart from './HorizontalBarChart'

interface DimensionMetrics {
  GMV_TOTAL: number | null
  TICKET_POR_UNIDAD: number | null
  UNIDADES_TOTALES: number | null
  MARGEN_PROMEDIO: number | null
}

type MetricKey = 'GMV_TOTAL' | 'TICKET_POR_UNIDAD' | 'UNIDADES_TOTALES' | 'MARGEN_PROMEDIO'

interface Props<T> {
  rows: T[]
  labelKey: keyof T
  // Subconjunto de metricas a mostrar - ej. las secciones de plataforma/
  // tipo de cliente ya muestran GMV/Unidades como pastel, ahi solo se piden
  // las 2 tasas (ticket/margen) para no duplicar. Default: las 4.
  metricKeys?: MetricKey[]
}

const GOOD = '#158158'
const moneda = (v: number) => `$${v.toLocaleString('es-MX', { maximumFractionDigits: 0 })}`
const unidades = (v: number) => v.toLocaleString('es-MX', { maximumFractionDigits: 0 })
const porcentaje = (v: number) => `${v.toFixed(1)}%`

const METRICAS: { title: string; campo: MetricKey; formatValue: (v: number) => string }[] = [
  { title: 'GMV', campo: 'GMV_TOTAL', formatValue: moneda },
  { title: 'Ticket por unidad', campo: 'TICKET_POR_UNIDAD', formatValue: moneda },
  { title: 'Unidades', campo: 'UNIDADES_TOTALES', formatValue: unidades },
  { title: 'Margen', campo: 'MARGEN_PROMEDIO', formatValue: porcentaje },
]

// Grid de HorizontalBarChart (GMV/ticket por unidad/unidades/margen) para
// una dimension (Categoria, Departamento, plataforma o tipo de cliente) -
// mismo componente generico, solo cambia `labelKey`.
export default function DimensionMetricsSection<T extends DimensionMetrics>({ rows, labelKey, metricKeys }: Props<T>) {
  const visibles = metricKeys ? METRICAS.filter((m) => metricKeys.includes(m.campo)) : METRICAS
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
      {visibles.map((m) => (
        <HorizontalBarChart
          key={m.title}
          title={m.title}
          items={rows
            .filter((r) => r[m.campo] != null)
            .sort((a, b) => (b[m.campo] as number) - (a[m.campo] as number))
            .map((r) => ({ label: String(r[labelKey] ?? 'N/D'), value: r[m.campo] as number }))}
          color={GOOD}
          formatValue={m.formatValue}
        />
      ))}
    </div>
  )
}
