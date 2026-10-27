// Columns for a row of package cards: as many as there are cards (up to four), so the row
// spans the content width with no empty column or orphaned last card.
// Class names are literal so Tailwind keeps them.
const PACKAGE_GRID_CLASSES = {
  1: 'grid-cols-1',
  2: 'grid-cols-1 sm:grid-cols-2',
  3: 'grid-cols-1 lg:grid-cols-3',
  4: 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-4',
}

export function packageGridClass(count) {
  const columns = Math.min(Math.max(Number(count) || 0, 1), 4)
  return PACKAGE_GRID_CLASSES[columns]
}

// Compact variant for a dialog, where cards are small enough to sit three across from sm.
const COMPACT_GRID_CLASSES = {
  1: 'grid-cols-1',
  2: 'grid-cols-1 sm:grid-cols-2',
  3: 'grid-cols-1 sm:grid-cols-3',
  4: 'grid-cols-1 sm:grid-cols-2',
}

export function compactPackageGridClass(count) {
  const columns = Math.min(Math.max(Number(count) || 0, 1), 4)
  return COMPACT_GRID_CLASSES[columns]
}
