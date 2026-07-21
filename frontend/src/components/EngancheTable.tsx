import type { EngancheOrdenRow, EngancheRow, EngancheSegmentoRow } from '../types'
import DataTable, { type Column } from './DataTable'
import GroupedBarChart, { type GroupedBarGroup } from './GroupedBarChart'

interface Props {
  porOrden: EngancheOrdenRow[]
  porCliente: EngancheRow[]
  porSegmento: EngancheSegmentoRow[]
}

const COLOR_CON_CAMPANA = '#158158'
const COLOR_SIN_CAMPANA = '#888888'

function moneda(v: number | null | undefined): string {
  return v == null ? 'N/D' : `$${v.toLocaleString('es-MX', { maximumFractionDigits: 0 })}`
}

function pct(v: number | null | undefined): string {
  return v == null ? 'N/D' : `${v.toFixed(1)}%`
}

const columnasOrden: Column<EngancheOrdenRow>[] = [
  { key: 'GRUPO', label: 'Grupo' },
  { key: 'ORDENES', label: 'Ordenes' },
  { key: 'TICKET_PROMEDIO_ORDEN', label: 'Ticket promedio por orden', render: (r) => moneda(r.TICKET_PROMEDIO_ORDEN) },
  { key: 'GASTO_CAMPANA_PROMEDIO', label: 'Gasto en campaña', render: (r) => moneda(r.GASTO_CAMPANA_PROMEDIO) },
  { key: 'GASTO_RESTO_PROMEDIO', label: 'Resto del carrito', render: (r) => moneda(r.GASTO_RESTO_PROMEDIO) },
  { key: 'PCT_CAMPANA_EN_TICKET', label: '% campaña en el ticket', render: (r) => pct(r.PCT_CAMPANA_EN_TICKET) },
]

const columnasCliente: Column<EngancheRow>[] = [
  { key: 'GRUPO', label: 'Grupo' },
  { key: 'USUARIOS', label: 'Clientes' },
  { key: 'TICKET_TOTAL_PROMEDIO', label: 'Gasto TOTAL por cliente (ventana)', render: (r) => moneda(r.TICKET_TOTAL_PROMEDIO) },
  { key: 'GASTO_CAMPANA_PROMEDIO', label: 'Gasto en campaña', render: (r) => moneda(r.GASTO_CAMPANA_PROMEDIO) },
  { key: 'GASTO_RESTO_PROMEDIO', label: 'Resto del carrito', render: (r) => moneda(r.GASTO_RESTO_PROMEDIO) },
  { key: 'PCT_CAMPANA_EN_TICKET', label: '% campaña en el ticket', render: (r) => pct(r.PCT_CAMPANA_EN_TICKET) },
]

const columnasSegmento: Column<EngancheSegmentoRow>[] = [
  { key: 'SEGMENTO_USUARIO', label: 'Tipo de cliente', render: (r) => r.SEGMENTO_USUARIO ?? 'Sin dato' },
  { key: 'GRUPO', label: 'Grupo' },
  { key: 'USUARIOS', label: 'Clientes' },
  { key: 'TICKET_TOTAL_PROMEDIO', label: 'Gasto TOTAL por cliente (ventana)', render: (r) => moneda(r.TICKET_TOTAL_PROMEDIO) },
  { key: 'GASTO_CAMPANA_PROMEDIO', label: 'Gasto en campaña', render: (r) => moneda(r.GASTO_CAMPANA_PROMEDIO) },
  { key: 'GASTO_RESTO_PROMEDIO', label: 'Resto del carrito', render: (r) => moneda(r.GASTO_RESTO_PROMEDIO) },
  { key: 'PCT_CAMPANA_EN_TICKET', label: '% campaña en el ticket', render: (r) => pct(r.PCT_CAMPANA_EN_TICKET) },
]

// Barras comparativas por tipo de cliente: para cada segmento, el gasto
// total del que compro campaña (verde) vs. el que no (gris) - la lectura
// visual directa de "¿el reactivado que toco la promo compro mas?".
function gruposSegmento(rows: EngancheSegmentoRow[]): GroupedBarGroup[] {
  const segmentos = Array.from(new Set(rows.map((r) => r.SEGMENTO_USUARIO ?? 'Sin dato')))
  return segmentos
    .map((seg) => ({
      label: seg,
      bars: rows
        .filter((r) => (r.SEGMENTO_USUARIO ?? 'Sin dato') === seg && r.TICKET_TOTAL_PROMEDIO != null)
        .sort((a) => (a.GRUPO.startsWith('Compraron') ? -1 : 1))
        .map((r) => ({
          seriesLabel: r.GRUPO,
          value: r.TICKET_TOTAL_PROMEDIO as number,
          color: r.GRUPO.startsWith('Compraron') ? COLOR_CON_CAMPANA : COLOR_SIN_CAMPANA,
        })),
    }))
    .filter((g) => g.bars.length > 0)
}

// Responde "¿la promo fue un gancho?" en tres cortes complementarios:
// - Por ORDEN: ¿el carrito que traia promo fue mas grande? (incluye
//   marketplaces externos, no requiere USER_ID).
// - Por CLIENTE: gasto total de la persona en la ventana.
// - Por TIPO DE CLIENTE: el mismo contraste dentro de cada segmento -
//   responde "¿el reactivado que compro campaña termino comprando mas?".
export default function EngancheTable({ porOrden, porCliente, porSegmento }: Props) {
  return (
    <div>
      {porOrden.length > 0 && (
        <div style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ color: 'var(--text-h)', margin: '0 0 0.5rem' }}>Por orden (¿el carrito con promo fue mas grande?)</h3>
          <DataTable columns={columnasOrden} rows={porOrden} pageSize={5} />
        </div>
      )}
      {porCliente.length > 0 && (
        <div style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ color: 'var(--text-h)', margin: '0 0 0.5rem' }}>Por cliente (gasto total en la ventana)</h3>
          <DataTable columns={columnasCliente} rows={porCliente} pageSize={5} />
        </div>
      )}
      {porSegmento.length > 0 && (
        <div style={{ marginBottom: '1rem' }}>
          <h3 style={{ color: 'var(--text-h)', margin: '0 0 0.5rem' }}>
            Por tipo de cliente (¿el reactivado que compro campaña, compro mas?)
          </h3>
          <div style={{ marginBottom: '1rem' }}>
            <GroupedBarChart
              title="Gasto TOTAL por cliente en la ventana"
              groups={gruposSegmento(porSegmento)}
              formatValue={(v) => moneda(v)}
            />
          </div>
          <DataTable columns={columnasSegmento} rows={porSegmento} pageSize={10} />
        </div>
      )}
      <p style={{ fontSize: '0.85rem', opacity: 0.7, marginTop: '0.5rem' }}>
        "Resto del carrito" = lo que se llevo ademas de los productos de campaña. La vista por orden
        incluye marketplaces externos; las vistas por cliente/segmento no (requieren usuario
        identificable). Comparacion descriptiva, no causal: quien busca promos puede ser de por si
        un cliente de canasta grande.
      </p>
    </div>
  )
}
