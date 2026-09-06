import axios, { AxiosError, AxiosHeaders } from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'
import client from './client'

afterEach(() => { vi.restoreAllMocks(); localStorage.clear() })

describe('authenticated API client', () => {
  it('shares refresh across concurrent failures and saves the rotated refresh token', async () => {
    localStorage.setItem('access_token', 'expired')
    localStorage.setItem('refresh_token', 'original-refresh')
    const refresh = vi.spyOn(axios, 'post').mockResolvedValue({ data: { access: 'renewed', refresh: 'rotated' } })
    const adapter = vi.fn(async config => {
      if (config.headers.Authorization === 'Bearer expired') {
        throw new AxiosError('expired', 'ERR_BAD_REQUEST', config, undefined,
          { data: {}, status: 401, statusText: 'Unauthorized', headers: new AxiosHeaders(), config })
      }
      return { data: { ok: true }, status: 200, statusText: 'OK', headers: new AxiosHeaders(), config }
    })
    const responses = await Promise.all([client.get('/monitors/', { adapter }), client.get('/incidents/', { adapter })])
    expect(responses.every(response => response.data.ok)).toBe(true)
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem('refresh_token')).toBe('rotated')
    expect(adapter).toHaveBeenCalledTimes(4)
  })
})
