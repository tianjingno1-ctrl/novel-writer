/** 书型（project.type）与题材（plan.meta.genre）分离 */

export const BOOK_FORMATS = [
  { id: 'short', label: '短篇' },
  { id: 'novel', label: '长篇' },
] as const

export type BookFormatId = (typeof BOOK_FORMATS)[number]['id']

export const GENRE_CHIPS = [
  { id: 'urban', label: '都市' },
  { id: 'sweet', label: '甜宠' },
  { id: 'ancient', label: '古言' },
] as const

export type GenreId = (typeof GENRE_CHIPS)[number]['id']

export function isBookFormat(value: string | undefined): value is BookFormatId {
  return value === 'short' || value === 'novel'
}

export function normalizeBookFormat(
  value: string | undefined,
  fallback: BookFormatId = 'novel',
): BookFormatId {
  return isBookFormat(value) ? value : fallback
}

export function normalizeGenre(value: string | undefined): GenreId | '' {
  const g = (value || '').trim().toLowerCase()
  return GENRE_CHIPS.some((c) => c.id === g) ? (g as GenreId) : ''
}
