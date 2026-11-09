import { describe, expect, it } from 'vitest'

import { compactPackageGridClass, packageGridClass } from '@/utils/cardGrid'

describe('packageGridClass', () => {
  it('uses one column per card up to four, without orphans', () => {
    expect(packageGridClass(1)).toBe('grid-cols-1')
    expect(packageGridClass(2)).toBe('grid-cols-1 sm:grid-cols-2')
    expect(packageGridClass(3)).toBe('grid-cols-1 lg:grid-cols-3')
    expect(packageGridClass(4)).toBe('grid-cols-1 sm:grid-cols-2 xl:grid-cols-4')
    expect(packageGridClass(7)).toBe(packageGridClass(4))
  })

  it('treats an empty or unknown count as one column', () => {
    expect(packageGridClass(0)).toBe('grid-cols-1')
    expect(packageGridClass(undefined)).toBe('grid-cols-1')
  })

  it('puts three dialog cards on one row from sm', () => {
    expect(compactPackageGridClass(3)).toBe('grid-cols-1 sm:grid-cols-3')
    expect(compactPackageGridClass(4)).toBe('grid-cols-1 sm:grid-cols-2')
  })
})
