export interface PieItem {
  label: string
  value: number
  color: string
}

interface Props {
  title: string
  items: PieItem[]
  formatValue?: (v: number) => string
}

// CSS conic-gradient puro (sin libreria de graficas, mismo criterio que
// HorizontalBarChart.tsx) - un div circular con un gradiente conico arma
// un pastel real (relleno, no un anillo/donut).
export default function PieChart({ title, items, formatValue }: Props) {
  const fmt = formatValue ?? ((v: number) => v.toLocaleString('es-MX', { maximumFractionDigits: 0 }))
  const total = items.reduce((acc, i) => acc + i.value, 0) || 1

  let acumulado = 0
  const stops: string[] = []
  for (const item of items) {
    const inicio = (acumulado / total) * 100
    acumulado += item.value
    const fin = (acumulado / total) * 100
    stops.push(`${item.color} ${inicio}% ${fin}%`)
  }

  return (
    <figure style={{ margin: 0, display: 'flex', gap: '1.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
      <div
        role="img"
        aria-label={title}
        style={{
          width: '200px',
          height: '200px',
          borderRadius: '50%',
          flexShrink: 0,
          background: `conic-gradient(${stops.join(', ')})`,
        }}
      />
      <figcaption style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
        <div style={{ fontWeight: 600, color: 'var(--text-h)', marginBottom: '0.2rem' }}>{title}</div>
        {items.map((item) => (
          <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
            <span
              style={{ width: '10px', height: '10px', borderRadius: '2px', background: item.color, flexShrink: 0 }}
            />
            <span style={{ color: 'var(--text)' }}>{item.label}</span>
            <span style={{ color: 'var(--text-h)', fontWeight: 600 }}>
              {fmt(item.value)} ({((item.value / total) * 100).toFixed(1)}%)
            </span>
          </div>
        ))}
      </figcaption>
    </figure>
  )
}
