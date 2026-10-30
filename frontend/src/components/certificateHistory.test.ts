import { expect, it } from 'vitest'
import { certificateExpiry } from './certificateHistory'

it('uses the certificate captured in each historical record', () => {
  const old = { detail: { not_after: '2026-11-01T00:00:00+00:00' }, metrics: {} }
  const renewed = { detail: { not_after: '2027-11-01T00:00:00+00:00' }, metrics: {} }
  expect(certificateExpiry(old)).toBe('2026-11-01T00:00:00+00:00')
  expect(certificateExpiry(renewed)).toBe('2027-11-01T00:00:00+00:00')
})
it('supports the newer stored metrics without requiring a backend upgrade', () => {
  expect(certificateExpiry({ detail: {}, metrics: { expires_at: '2026-12-01T00:00:00Z' } })).toBe('2026-12-01T00:00:00Z')
})
it('does not invent expiry for missing or invalid certificate data', () => {
  expect(certificateExpiry({ detail: {}, metrics: {} })).toBeNull()
  expect(certificateExpiry({ detail: { not_after: 'invalid' }, metrics: { expires_at: 10 } })).toBeNull()
})
