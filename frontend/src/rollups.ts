import type { CategoriaRow, DepartamentoRow, MechanicRow } from './types'

interface Acumulado {
  SKUS: number
  UNIDADES_TOTALES: number
  GMV_TOTAL: number
  gmvXMargen: number // solo filas con margen != null, para el promedio ponderado
}

// Re-agregacion pura de la salida de /mechanics a nivel Categoria o
// Departamento - espejo exacto de postmortem._resumen_por_dimension
// (SKUS suma, margen ponderado por GMV, ticket = GMV/unidades). Se calcula
// en el navegador porque los datos ya llegaron con /mechanics: pedirselo al
// backend re-ejecutaba performance_por_mecanica completo (con sus escaneos
// pesados de Snowflake) dos veces mas por cada cambio de filtro.
function rollupPorDimension(rows: MechanicRow[], key: 'CATEGORIA' | 'DEPARTAMENTO') {
  const grupos = new Map<string | null, Acumulado>()
  for (const r of rows) {
    const etiqueta = r[key]
    const acc = grupos.get(etiqueta) ?? { SKUS: 0, UNIDADES_TOTALES: 0, GMV_TOTAL: 0, gmvXMargen: 0 }
    acc.SKUS += r.SKUS
    acc.UNIDADES_TOTALES += r.UNIDADES_TOTALES ?? 0
    acc.GMV_TOTAL += r.GMV_TOTAL ?? 0
    // igual que pandas: el numerador solo suma filas con margen conocido,
    // el denominador es el GMV completo del grupo
    if (r.MARGEN_PROMEDIO != null && r.GMV_TOTAL != null) {
      acc.gmvXMargen += r.GMV_TOTAL * r.MARGEN_PROMEDIO
    }
    grupos.set(etiqueta, acc)
  }
  return Array.from(grupos.entries())
    .map(([etiqueta, acc]) => ({
      [key]: etiqueta,
      SKUS: acc.SKUS,
      UNIDADES_TOTALES: acc.UNIDADES_TOTALES,
      GMV_TOTAL: acc.GMV_TOTAL,
      MARGEN_PROMEDIO: acc.GMV_TOTAL > 0 ? acc.gmvXMargen / acc.GMV_TOTAL : null,
      TICKET_POR_UNIDAD: acc.UNIDADES_TOTALES > 0 ? acc.GMV_TOTAL / acc.UNIDADES_TOTALES : null,
    }))
    .sort((a, b) => b.GMV_TOTAL - a.GMV_TOTAL)
}

export function rollupPorCategoria(rows: MechanicRow[]): CategoriaRow[] {
  return rollupPorDimension(rows, 'CATEGORIA') as unknown as CategoriaRow[]
}

export function rollupPorDepartamento(rows: MechanicRow[]): DepartamentoRow[] {
  return rollupPorDimension(rows, 'DEPARTAMENTO') as unknown as DepartamentoRow[]
}
