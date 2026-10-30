import type { MonitorResult } from '../api/monitorTypes'

// Read only the certificate captured by this probe, never the task's current certificate.
export function certificateExpiry(result: Pick<MonitorResult, 'detail' | 'metrics'>): string | null {
  for (const value of [result.detail?.not_after, result.metrics?.expires_at]) {
    if (typeof value === 'string' && value.trim() && Number.isFinite(Date.parse(value))) return value
  }
  return null
}
