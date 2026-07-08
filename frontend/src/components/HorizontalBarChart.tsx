export interface BarItem {
  label: string
  value: number
}

interface Props {
  title: string
  items: BarItem[]
  color: string
  formatValue?: (v: number) => string
}

export default function HorizontalBarChart({ title, items, color, formatValue }: Props) {
  const fmt = formatValue ?? ((v: number) => v.toLocaleString('es-MX', { maximumFractionDigits: 1 }))
  const max = Math.max(...items.map((i) => Math.abs(i.value)), 1)

  return (
    <figure style={{ margin: 0 }}>
      <figcaption style={{ fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-h)' }}>{title}</figcaption>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
        {items.map((item, i) => {
          const pct = (Math.abs(item.value) / max) * 100
          return (
            <div key={i} title={`${item.label}: ${fmt(item.value)}`} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <div
                style={{
                  width: '220px',
                  flexShrink: 0,
                  fontSize: '0.8rem',
                  color: 'var(--text)',
                  textAlign: 'right',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {item.label}
              </div>
              <div style={{ flex: 1, background: 'var(--border)', borderRadius: '4px', height: '20px' }}>
                <div
                  className="bar-fill"
                  style={{
                    width: `${pct}%`,
                    height: '100%',
                    background: color,
                    borderRadius: '4px',
                    transition: 'filter 0.1s',
                  }}
                />
              </div>
              <div style={{ width: '100px', flexShrink: 0, fontSize: '0.8rem', color: 'var(--text-h)', fontWeight: 600 }}>
                {fmt(item.value)}
              </div>
            </div>
          )
        })}
      </div>
    </figure>
  )
}
