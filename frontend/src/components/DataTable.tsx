import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'

export interface Column<T> {
  key: string
  label: string
  sortable?: boolean
  render?: (row: T) => ReactNode
  sortValue?: (row: T) => string | number | null
}

interface Props<T> {
  columns: Column<T>[]
  rows: T[]
  pageSize?: number
}

export default function DataTable<T>({ columns, rows, pageSize = 10 }: Props<T>) {
  const [page, setPage] = useState(0)
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  const sorted = useMemo(() => {
    if (!sortKey) return rows
    const col = columns.find((c) => c.key === sortKey)
    if (!col) return rows
    const getValue = col.sortValue ?? ((row: T) => (row as Record<string, unknown>)[col.key] as string | number | null)
    const copy = [...rows]
    copy.sort((a, b) => {
      const va = getValue(a)
      const vb = getValue(b)
      if (va == null && vb == null) return 0
      if (va == null) return 1
      if (vb == null) return -1
      if (va < vb) return sortDir === 'asc' ? -1 : 1
      if (va > vb) return sortDir === 'asc' ? 1 : -1
      return 0
    })
    return copy
  }, [rows, sortKey, sortDir, columns])

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize))
  const clampedPage = Math.min(page, pageCount - 1)
  const paged = sorted.slice(clampedPage * pageSize, clampedPage * pageSize + pageSize)

  function toggleSort(key: string) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
    setPage(0)
  }

  return (
    <div>
      <table>
        <thead>
          <tr>
            {columns.map((c) => {
              const isSortable = c.sortable !== false
              return (
                <th
                  key={c.key}
                  onClick={isSortable ? () => toggleSort(c.key) : undefined}
                  style={{ cursor: isSortable ? 'pointer' : 'default', userSelect: 'none' }}
                >
                  {c.label}
                  {sortKey === c.key ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {paged.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.key}>
                  {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? 'N/D')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {pageCount > 1 && (
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginTop: '0.5rem' }}>
          <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={clampedPage === 0}>
            Anterior
          </button>
          <span>
            Pagina {clampedPage + 1} de {pageCount} ({sorted.length} filas)
          </span>
          <button
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            disabled={clampedPage >= pageCount - 1}
          >
            Siguiente
          </button>
        </div>
      )}
    </div>
  )
}
