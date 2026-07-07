import type { RedemptionRow } from '../types'

interface Props {
  rows: RedemptionRow[]
}

function pct(v: number | null | undefined): string {
  return v == null ? 'N/D' : `${(v * 100).toFixed(1)}%`
}

export default function RedemptionTable({ rows }: Props) {
  return (
    <div>
      <table>
        <thead>
          <tr>
            <th>Estrategia</th>
            <th>Buy/Pay</th>
            <th>Tier</th>
            <th>Unidades</th>
            <th>Redencion real</th>
            <th>Redencion supuesta</th>
            <th>Diferencia</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{r.BULK_STRATEGY ?? 'Sin mecanica'}</td>
              <td>
                {r.BULK_RULE_BUY ?? '-'}/{r.BULK_RULE_PAY ?? '-'}
              </td>
              <td>{r.TIER ?? 'N/D'}</td>
              <td>{r.UNIDADES_TOTALES?.toLocaleString() ?? 'N/D'}</td>
              <td>{pct(r.REDENCION_REAL)}</td>
              <td>{pct(r.REDENCION_SUPUESTA)}</td>
              <td>{pct(r.DIFERENCIA)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ fontSize: '0.85rem', opacity: 0.7 }}>
        Nota: muestras chicas (12-132 unidades) en las mecanicas con umbral real - tratar
        como directional, no como validado.
      </p>
    </div>
  )
}
