import { BACKEND_URL } from '../config'

/**
 * Ask the backend to create a Stripe Checkout session, then redirect the
 * browser to Stripe's hosted checkout page. On success this navigates away,
 * so it does not return; on failure it throws.
 */
export async function startCheckout(token: string): Promise<void> {
  const res = await fetch(`${BACKEND_URL}/api/billing/create-checkout-session`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok || !data?.url) {
    throw new Error(data?.detail || 'Could not start checkout. Please try again.')
  }
  window.location.href = data.url as string
}

/**
 * Open the Stripe Customer Portal (manage payment method, cancel, invoices).
 * Redirects the browser to Stripe on success; throws on failure.
 */
export async function openBillingPortal(token: string): Promise<void> {
  const res = await fetch(`${BACKEND_URL}/api/billing/portal`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok || !data?.url) {
    throw new Error(data?.detail || 'Could not open the billing portal.')
  }
  window.location.href = data.url as string
}
