export interface GroupedBarSeries {
  seriesLabel: string
  value: number
  color: string
}

export interface GroupedBarGroup {
  label: string
  bars: GroupedBarSeries[]
}

interface Props {
  title: string
  groups: GroupedBarGroup[]
  formatValue?: (v: number) => string
}

const CHART_H = 220
const N_TICKS = 4 // 4 intervalos -> 5 lineas de eje

// Paso "bonito" para el eje Y: redondea max/N_TICKS hacia arriba al multiplo
// 1/1.25/1.5/2/2.5/3/4/5/6/8 x 10^k mas cercano, para que los ticks salgan
// redondos ($1,250 / $2,500...) en vez de fracciones crudas del maximo
// ($4,783 / $3,587...).
function pasoBonito(max: number): number {
  const bruto = max / N_TICKS
  const pot = Math.pow(10, Math.floor(Math.log10(bruto)))
  for (const m of [1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8]) {
    if (m * pot >= bruto) return m * pot
  }
  return 10 * pot
}

// Barras verticales agrupadas (una serie por plataforma/tipo de cliente,
// un grupo por categoria/departamento) - sin libreria de graficas, mismo
// criterio que HorizontalBarChart.tsx/PieChart.tsx. Eje Y con lineas guia +
// valores (sin esto, una barra sola no dice nada - solo comparacion
// relativa sin escala). Scroll horizontal si hay muchos grupos (ej. ~24
// categorias).
export default function GroupedBarChart({ title, groups, formatValue }: Props) {
  const fmt = formatValue ?? ((v: number) => v.toLocaleString('es-MX', { maximumFractionDigits: 0 }))
  const max = Math.max(...groups.flatMap((g) => g.bars.map((b) => Math.abs(b.value))), 1)
  const series = Array.from(
    new Map(groups.flatMap((g) => g.bars.map((b) => [b.seriesLabel, b.color] as const))).entries(),
  )
  const paso = pasoBonito(max)
  const topEscala = paso * N_TICKS
  const ticks = Array.from({ length: N_TICKS + 1 }, (_, i) => paso * (N_TICKS - i))

  return (
    <figure style={{ margin: 0 }}>
      <figcaption style={{ fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-h)' }}>{title}</figcaption>
      <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', marginBottom: '0.75rem', fontSize: '0.8rem' }}>
        {series.map(([label, color]) => (
          <span key={label} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <span style={{ width: '10px', height: '10px', borderRadius: '2px', background: color, display: 'inline-block' }} />
            <span style={{ color: 'var(--text)' }}>{label}</span>
          </span>
        ))}
      </div>
      <div style={{ display: 'flex' }}>
        {/* Eje Y - fuera del contenedor con scroll, siempre visible */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            height: `${CHART_H}px`,
            marginRight: '0.5rem',
            fontSize: '0.7rem',
            color: 'var(--text)',
            textAlign: 'right',
            flexShrink: 0,
          }}
        >
          {ticks.map((v, i) => (
            <span key={i}>{fmt(v)}</span>
          ))}
        </div>

        <div style={{ overflowX: 'auto', flex: 1 }}>
          <div style={{ position: 'relative', minWidth: 'fit-content' }}>
            {/* Lineas guia horizontales a la misma altura que las etiquetas del eje Y */}
            <div
              style={{
                position: 'absolute',
                inset: 0,
                height: `${CHART_H}px`,
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                pointerEvents: 'none',
              }}
            >
              {ticks.map((_, i) => (
                <div key={i} style={{ borderTop: '1px solid var(--border)' }} />
              ))}
            </div>

            <div style={{ display: 'flex', alignItems: 'flex-end', gap: '1.25rem', height: `${CHART_H}px`, position: 'relative' }}>
              {groups.map((g) => (
                <div key={g.label} style={{ display: 'flex', alignItems: 'flex-end', gap: '2px', height: `${CHART_H}px` }}>
                  {g.bars.map((b) => (
                    <div
                      key={b.seriesLabel}
                      title={`${g.label} · ${b.seriesLabel}: ${fmt(b.value)}`}
                      style={{
                        width: '14px',
                        height: `${(Math.abs(b.value) / topEscala) * 100}%`,
                        background: b.color,
                        borderRadius: '2px 2px 0 0',
                      }}
                    />
                  ))}
                </div>
              ))}
            </div>

            {/* Etiquetas de grupo (categoria/departamento), alineadas con sus barras */}
            <div style={{ display: 'flex', gap: '1.25rem', marginTop: '0.4rem' }}>
              {groups.map((g) => (
                <div
                  key={g.label}
                  title={g.label}
                  style={{
                    width: `${g.bars.length * 16 - 2}px`,
                    fontSize: '0.7rem',
                    color: 'var(--text)',
                    writingMode: 'vertical-rl',
                    transform: 'rotate(180deg)',
                    maxHeight: '130px',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {g.label}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </figure>
  )
}
