import type { CampaignFilters, Filters } from '../types'

interface Props {
  filters: Filters
  value: CampaignFilters
  onChange: (f: CampaignFilters) => void
}

const ADOPCION_LABELS: Record<string, string> = {
  con_mecanica: 'Con mecanica (adoptado)',
  sin_mecanica: 'Sin mecanica (no adoptado)',
}

export default function FilterBar({ filters, value, onChange }: Props) {
  return (
    <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', margin: '0.75rem 0' }}>
      <select
        value={value.departamento ?? ''}
        onChange={(e) => onChange({ ...value, departamento: e.target.value || undefined })}
      >
        <option value="">Todos los departamentos</option>
        {filters.departamentos.map((d) => (
          <option key={d} value={d}>
            {d}
          </option>
        ))}
      </select>

      <select
        value={value.categoria ?? ''}
        onChange={(e) => onChange({ ...value, categoria: e.target.value || undefined })}
      >
        <option value="">Todas las categorias</option>
        {filters.categorias.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>

      <select
        value={value.store_id ?? ''}
        onChange={(e) => onChange({ ...value, store_id: e.target.value ? Number(e.target.value) : undefined })}
      >
        <option value="">Todas las bodegas</option>
        {filters.stores.map((s) => (
          <option key={s.id} value={s.id}>
            {s.nombre}
          </option>
        ))}
      </select>

      <select
        value={value.origen ?? ''}
        onChange={(e) => onChange({ ...value, origen: e.target.value || undefined })}
      >
        <option value="">Todos los origenes</option>
        {filters.origenes.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>

      <select
        value={value.adopcion ?? ''}
        onChange={(e) => onChange({ ...value, adopcion: e.target.value || undefined })}
      >
        <option value="">Con o sin mecanica</option>
        {filters.adopciones.map((a) => (
          <option key={a} value={a}>
            {ADOPCION_LABELS[a] ?? a}
          </option>
        ))}
      </select>

      <select
        value={value.marketplace ?? ''}
        onChange={(e) => onChange({ ...value, marketplace: e.target.value || undefined })}
      >
        <option value="">Todas las plataformas</option>
        {filters.marketplaces.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>

      <select
        value={value.segmento_usuario ?? ''}
        onChange={(e) => onChange({ ...value, segmento_usuario: e.target.value || undefined })}
      >
        <option value="">Todos los tipos de cliente</option>
        {filters.segmentos_usuario.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>

      <select
        value={value.mecanica ?? ''}
        onChange={(e) => onChange({ ...value, mecanica: e.target.value || undefined })}
      >
        <option value="">Todas las mecanicas</option>
        {filters.mecanicas.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
    </div>
  )
}
