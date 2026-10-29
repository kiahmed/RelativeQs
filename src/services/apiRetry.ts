/**
 * fetch() with a short retry for transient failures.
 *
 * The whole backend is behind a login token. Right after a page load (or a
 * token refresh) a request can go out with a stale token and get a 401 a moment
 * before the refreshed one lands in the auth store. A brief wait and one more try
 * — re-reading the token each time — clears that. Network errors and gateway
 * errors (502/503/504, e.g. the backend restarting) are retried the same way.
 *
 * Policy: wait 5 s between attempts, retry at most twice (3 attempts in all),
 * then log to the console and hand the last response (or error) back to the
 * caller, which already handles `!ok`.
 */

export const RETRY_DELAY_MS = 5000
export const MAX_RETRIES = 2
const RETRYABLE_STATUS = new Set([401, 502, 503, 504])

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/**
 * @param makeRequest builds and sends the request. Called afresh on every
 *   attempt, so it should read the current auth token itself.
 * @param label short name for the console message (e.g. the endpoint)
 */
export async function fetchWithRetry(
  makeRequest: () => Promise<Response>,
  label: string,
): Promise<Response> {
  let lastError: unknown = null
  let lastResponse: Response | null = null

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    if (attempt > 0) await sleep(RETRY_DELAY_MS)
    try {
      const res = await makeRequest()
      if (!RETRYABLE_STATUS.has(res.status)) return res
      lastResponse = res
      lastError = null
    } catch (err) {
      lastError = err
      lastResponse = null
    }
  }

  if (lastResponse) {
    console.error(
      `[api] ${label} still failing (HTTP ${lastResponse.status}) after ${MAX_RETRIES} retries`,
    )
    return lastResponse
  }
  console.error(`[api] ${label} failed after ${MAX_RETRIES} retries`, lastError)
  throw lastError
}
