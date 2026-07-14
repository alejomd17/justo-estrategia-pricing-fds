import type { PlataformaSegmentoRow } from '../types'

interface Props {
  rows: PlataformaSegmentoRow[]
}

function moneda(v: number | null | undefined): string {
  return v == null ? 'N/D' : `$${v.toLocaleString('es-MX', { maximumFractionDigits: 0 })}`
}

// Tabla pivote (plataforma x segmento) en vez de DataTable generico -
// responde directo la pregunta "¿'Sin dato' es en realidad marketplace
// externo?" sin tener que cruzar filas mentalmente. Filas y columnas
// ordenadas por su GMV total descendente (no alfabetico - didi con $80 no
// debe salir arriba).
export default function PlataformaSegmentoTable({ rows }: Props) {
  const totalPlataforma = new Map<string, number>()
  const totalSegmento = new Map<string, number>()
  const mapa = new Map<string, number | null>()
  rows.forEach((r) => {
    const p = r.MARKETPLACE ?? 'N/D'
    const s = r.SEGMENTO_USUARIO ?? 'Sin dato'
    totalPlataforma.set(p, (totalPlataforma.get(p) ?? 0) + (r.GMV_TOTAL ?? 0))
    totalSegmento.set(s, (totalSegmento.get(s) ?? 0) + (r.GMV_TOTAL ?? 0))
    mapa.set(`${p}|${s}`, r.GMV_TOTAL)
  })
  const plataformas = Array.from(totalPlataforma.keys()).sort(
    (a, b) => (totalPlataforma.get(b) ?? 0) - (totalPlataforma.get(a) ?? 0),
  )
  const segmentos = Array.from(totalSegmento.keys()).sort(
    (a, b) => (totalSegmento.get(b) ?? 0) - (totalSegmento.get(a) ?? 0),
  )

  return (
    <div style={{ overflowX: 'auto' }}>
      <table>
        <thead>
          <tr>
            <th>Plataforma</th>
            {segmentos.map((s) => (
              <th key={s}>{s}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {plataformas.map((p) => (
            <tr key={p}>
              <td>{p}</td>
              {segmentos.map((s) => (
                <td key={s}>{moneda(mapa.get(`${p}|${s}`))}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ fontSize: '0.85rem', opacity: 0.7, marginTop: '0.5rem' }}>
        GMV por plataforma x tipo de cliente. Si "Sin dato" se concentra en uber/rappi/didi (no en
        justo/express), confirma que es marketplace externo sin clasificar, no un problema de datos
        aparte.
      </p>
    </div>
  )
}
