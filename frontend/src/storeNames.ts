export const STORE_NAMES: Record<number, string> = {
  9: 'Atizapan',
  14: 'Coyoacan',
}

export function storeName(storeId: number): string {
  return STORE_NAMES[storeId] ?? `Tienda ${storeId}`
}
