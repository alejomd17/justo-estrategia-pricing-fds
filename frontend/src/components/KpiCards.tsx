import type { AdoptionSummary, MechanicRow, SegmentoUsuarioRow, UsuariosSegmentoRow } from '../types'
import { storeName } from '../storeNames'

interface Props {
  summary: AdoptionSummary
  mechanics: MechanicRow[]
  segmentoUsuario: SegmentoUsuarioRow[]
  usuariosSegmento: UsuariosSegmentoRow[]
}

function sumaGanancia(rows: MechanicRow[]): number | null {
  const valores = rows.map((r) => r.GANANCIA_POR_ESTRATEGIA).filter((v): v is number => v != null)
  if (valores.length === 0) return null
  return valores.reduce((acc, v) => acc + v, 0)
}

function promedioTraccion(rows: MechanicRow[]): number | null {
  const valores = rows.map((r) => r.TRACCION_SKUS).filter((v): v is number => v != null && Number.isFinite(v))
  if (valores.length === 0) return null
  return valores.reduce((acc, v) => acc + v, 0) / valores.length
}

const moneda = (v: number) => `$${v.toLocaleString('es-MX', { maximumFractionDigits: 0 })}`

// Resumen ejecutivo de la campana - "el resultado como tal, ya no
// granulado": GMV, venta incremental, lift, clientes reactivados y margen
// en reactivados, mas los KPIs de adopcion. Mismos 5 numeros y orden que
// el reporte HTML.
export default function KpiCards({ summary, mechanics, segmentoUsuario, usuariosSegmento }: Props) {
  const gmvTotal = mechanics.reduce((acc, r) => acc + (r.GMV_TOTAL ?? 0), 0)
  const ganancia = sumaGanancia(mechanics)
  const pctIncremental = ganancia != null && gmvTotal > 0 ? (ganancia / gmvTotal) * 100 : null
  const traccion = promedioTraccion(mechanics)
  const reactivadosUsuarios = usuariosSegmento.find((r) => r.SEGMENTO_USUARIO === 'Reactivado')
  const margenReactivados = segmentoUsuario.find((r) => r.SEGMENTO_USUARIO === 'Reactivado')?.MARGEN_PROMEDIO

  // Subtitulo calculado: lift, ejecucion del plan y tienda que concentro el
  // GMV - misma linea que encabeza el reporte HTML.
  const wknd = summary.por_origen.find((r) => r.ORIGEN_CAMPANA === 'WKND')
  const porTienda = new Map<number, number>()
  mechanics.forEach((r) => porTienda.set(r.STORE_ID, (porTienda.get(r.STORE_ID) ?? 0) + (r.GMV_TOTAL ?? 0)))
  const tiendaTop = Array.from(porTienda.entries()).sort((a, b) => b[1] - a[1])[0]
  const partes: string[] = []
  if (traccion != null) partes.push(`Lift ${traccion.toFixed(2)}x vs ritmo historico`)
  if (wknd) partes.push(`${wknd.SKU_TIENDAS_CON_PROMO_REAL} de ${wknd.SKU_TIENDAS} grupos ejecutados del plan WKND`)
  if (tiendaTop && gmvTotal > 0)
    partes.push(`${storeName(tiendaTop[0])} concentro ${((tiendaTop[1] / gmvTotal) * 100).toFixed(0)}% del GMV`)

  return (
    <div>
      {partes.length > 0 && (
        <p style={{ fontSize: '0.9rem', opacity: 0.8, margin: '0 0 0.75rem' }}>{partes.join(' · ')}</p>
      )}
      <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
        <div className="kpi-card">
          <div className="kpi-label">GMV de campaña</div>
          <div className="kpi-value">{gmvTotal > 0 ? moneda(gmvTotal) : 'N/D'}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Venta incremental</div>
          <div className="kpi-value">{ganancia == null ? 'N/D' : moneda(ganancia)}</div>
          {pctIncremental != null && (
            <div style={{ fontSize: '0.75rem', opacity: 0.7 }}>{pctIncremental.toFixed(0)}% del GMV · vs ritmo historico</div>
          )}
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Lift vs historico</div>
          <div className="kpi-value">{traccion == null ? 'N/D' : `${traccion.toFixed(2)}x`}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Clientes reactivados</div>
          <div className="kpi-value">{reactivadosUsuarios ? reactivadosUsuarios.USUARIOS_DISTINTOS : 'N/D'}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Margen en reactivados</div>
          <div className="kpi-value">{margenReactivados != null ? `${margenReactivados.toFixed(1)}%` : 'N/D'}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Planeado</div>
          <div className="kpi-value">{summary.total_planeado}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Adopcion</div>
          <div className="kpi-value">
            {summary.adopcion_pct === null ? 'N/D' : `${summary.adopcion_pct}%`}
          </div>
        </div>
        {/* Solo WKND - "Otra fuente" sacada del visual a proposito (pedido
            del usuario 2026-07-14): no responde a los filtros y con WKND
            fijo solo confundia. "Sin promo" ya estaba fuera por el mismo
            criterio del backend. */}
        {summary.por_origen
          .filter((row) => row.ORIGEN_CAMPANA === 'WKND')
          .map((row) => (
            <div className="kpi-card" key={row.ORIGEN_CAMPANA}>
              <div className="kpi-label">{row.ORIGEN_CAMPANA}</div>
              <div className="kpi-value">
                {row.SKU_TIENDAS_CON_PROMO_REAL} / {row.SKU_TIENDAS}
              </div>
            </div>
          ))}
        <p style={{ width: '100%', fontSize: '0.85rem', opacity: 0.7 }}>
          Venta incremental = GMV real menos lo que estos SKUs hubieran facturado a su ritmo historico
          (la "ganancia por estrategia" de la tabla). La adopcion compara contra toda la ventana de la
          campaña, no contra el dia especifico planeado para cada SKU (aproximado, no exacto).
        </p>
      </div>
    </div>
  )
}
