import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchWithRetry, MAX_RETRIES, RETRY_DELAY_MS } from '../apiRetry'

const res = (status: number) => ({ status, ok: status >= 200 && status < 300 }) as Response

describe('fetchWithRetry', () => {
  let errorSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.useFakeTimers()
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })
  afterEach(() => {
    vi.useRealTimers()
    errorSpy.mockRestore()
  })

  it('returns immediately on success, no delay, no log', async () => {
    const send = vi.fn().mockResolvedValue(res(200))
    const out = await fetchWithRetry(send, '/x')
    expect(out.status).toBe(200)
    expect(send).toHaveBeenCalledTimes(1)
    expect(errorSpy).not.toHaveBeenCalled()
  })

  it('retries a 401 after 5 s and succeeds', async () => {
    const send = vi.fn().mockResolvedValueOnce(res(401)).mockResolvedValueOnce(res(200))
    const p = fetchWithRetry(send, '/x')
    await vi.advanceTimersByTimeAsync(RETRY_DELAY_MS - 1)
    expect(send).toHaveBeenCalledTimes(1) // still waiting
    await vi.advanceTimersByTimeAsync(1)
    expect((await p).status).toBe(200)
    expect(send).toHaveBeenCalledTimes(2)
    expect(errorSpy).not.toHaveBeenCalled()
  })

  it('never retries more than twice, then logs and returns the last response', async () => {
    const send = vi.fn().mockResolvedValue(res(401))
    const p = fetchWithRetry(send, '/api/x')
    await vi.advanceTimersByTimeAsync(RETRY_DELAY_MS * 5)
    expect((await p).status).toBe(401)
    expect(send).toHaveBeenCalledTimes(1 + MAX_RETRIES)
    expect(errorSpy).toHaveBeenCalledTimes(1)
    expect(String(errorSpy.mock.calls[0][0])).toContain('/api/x')
  })

  it('does not retry client errors that a retry cannot fix (403, 404)', async () => {
    for (const status of [403, 404]) {
      const send = vi.fn().mockResolvedValue(res(status))
      expect((await fetchWithRetry(send, '/x')).status).toBe(status)
      expect(send).toHaveBeenCalledTimes(1)
    }
  })

  it('retries a network error, and throws after the last attempt', async () => {
    const send = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    const p = fetchWithRetry(send, '/x')
    const assertion = expect(p).rejects.toThrow('Failed to fetch')
    await vi.advanceTimersByTimeAsync(RETRY_DELAY_MS * 5)
    await assertion
    expect(send).toHaveBeenCalledTimes(1 + MAX_RETRIES)
    expect(errorSpy).toHaveBeenCalledTimes(1)
  })

  it('rebuilds the request on each attempt (so a refreshed token is picked up)', async () => {
    let token = 'stale'
    const send = vi.fn(async () => (token === 'fresh' ? res(200) : res(401)))
    const p = fetchWithRetry(send, '/x')
    token = 'fresh' // the auth store receives the refreshed token during the wait
    await vi.advanceTimersByTimeAsync(RETRY_DELAY_MS)
    expect((await p).status).toBe(200)
  })
})
