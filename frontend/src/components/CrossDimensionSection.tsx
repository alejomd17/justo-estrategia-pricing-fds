import GroupedBarChart, { type GroupedBarGroup } from './GroupedBarChart'

interface CrossMetrics {
  GMV_TOTAL: number | null
  TICKET_POR_UNIDAD: number | null
  UNIDADES_TOTALES: number | null
  MARGEN_PROMEDIO: number | null
}

interface Props<T> {
  rows: T[]
  labelKey: keyof T
  seriesKey: keyof T
  colorMap: Record<string, string>
  defaultColor?: string
}

const moneda = (v: number) => `$${v.toLocaleString('es-MX', { maximumFractionDigits: 0 })}`
const unidades = (v: number) => v.toLocaleString('es-MX', { maximumFractionDigits: 0 })
const porcentaje = (v: number) => `${v.toFixed(1)}%`

const METRICAS = [
  { title: 'GMV', campo: 'GMV_TOTAL' as const, formatValue: moneda },
  { title: 'Ticket por unidad', campo: 'TICKET_POR_UNIDAD' as const, formatValue: moneda },
  { title: 'Unidades', campo: 'UNIDADES_TOTALES' as const, formatValue: unidades },
  { title: 'Margen', campo: 'MARGEN_PROMEDIO' as const, formatValue: porcentaje },
]

function buildGroups<T extends CrossMetrics>(
  rows: T[],
  labelKey: keyof T,
  seriesKey: keyof T,
  metricKey: keyof CrossMetrics,
  colorMap: Record<string, string>,
  defaultColor: string,
): GroupedBarGroup[] {
  const labels = Array.from(new Set(rows.map((r) => String(r[labelKey] ?? 'N/D'))))
  return labels
    .map((label) => ({
      label,
      bars: rows
        .filter((r) => String(r[labelKey] ?? 'N/D') === label && r[metricKey] != null)
        .map((r) => ({
          seriesLabel: String(r[seriesKey] ?? 'N/D'),
          value: r[metricKey] as number,
          color: colorMap[String(r[seriesKey] ?? 'N/D')] ?? defaultColor,
        })),
    }))
    .filter((g) => g.bars.length > 0)
}

// Barras verticales agrupadas (una serie por plataforma o tipo de cliente,
// un grupo por categoria/departamento) para las 4 metricas - reusado por
// los 4 cruces (categoria/departamento x plataforma/segmento).
export default function CrossDimensionSection<T extends CrossMetrics>({
  rows,
  labelKey,
  seriesKey,
  colorMap,
  defaultColor = '#888888',
}: Props<T>) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
      {METRICAS.map((m) => (
        <GroupedBarChart
          key={m.title}
          title={m.title}
          groups={buildGroups(rows, labelKey, seriesKey, m.campo, colorMap, defaultColor)}
          formatValue={m.formatValue}
        />
      ))}
    </div>
  )
}
