// Paleta "Weekly Pricing" (skill justo-brand-guide) - orden fijo por
// plataforma, no ciclado.
export const COLORES_PLATAFORMA: Record<string, string> = {
  justo: '#158158',
  express: '#058dc7',
  uber: '#ed561b',
  rappi: '#24cbe5',
  didi: '#64e572',
}

// Sin paleta de marca especifica para segmento de usuario - mismo orden
// fijo de acentos, reusando los mismos 5 colores en otro orden para no
// confundir visualmente con la paleta de plataforma.
export const COLORES_SEGMENTO: Record<string, string> = {
  Recurrente: '#158158',
  Reactivado: '#058dc7',
  New: '#ed561b',
  'Sin dato': '#888888',
}

export const COLOR_DEFAULT = '#888888'
