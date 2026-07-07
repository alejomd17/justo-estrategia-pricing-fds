import type { MechanicRow } from '../types'

interface Props {
  rows: MechanicRow[]
}

export default function MechanicsTable({ rows }: Props) {
  return (
    <table>
      <thead>
        <tr>
          <th>Mecanica</th>
          <th>Origen</th>
          <th>SKUs</th>
          <th>Unidades</th>
          <th>GMV</th>
          <th>Margen prom.</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td>{r.MECANICA_EJECUTADA ?? 'Sin mecanica'}</td>
            <td>{r.ORIGEN_CAMPANA}</td>
            <td>{r.SKUS}</td>
            <td>{r.UNIDADES_TOTALES?.toLocaleString() ?? 'N/D'}</td>
            <td>{r.GMV_TOTAL != null ? `$${r.GMV_TOTAL.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : 'N/D'}</td>
            <td>{r.MARGEN_PROMEDIO != null ? `${r.MARGEN_PROMEDIO.toFixed(1)}%` : 'N/D'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
