"""
Stripe billing — subscription checkout + webhook.

Flow:
  1. The frontend calls POST /api/billing/create-checkout-session (with the
     user's Supabase token). The backend creates a Stripe Checkout Session
     using the secret key and returns its URL; the browser redirects there.
  2. The user pays on Stripe's hosted page.
  3. Stripe calls POST /api/billing/webhook. The backend verifies the
     signature and flips the user's `plan` in the Supabase profiles table.

The webhook is the ONLY trustworthy "did they pay" signal — the frontend is
never trusted to grant a plan.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request

from app import auth, supabase_admin
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

if settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY


def _ts_to_iso(ts: Optional[int]) -> Optional[str]:
    """Convert a Unix timestamp to an ISO string for a timestamptz column."""
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()


async def _get_or_create_customer(user: dict) -> str:
    """Return the user's Stripe customer id, reusing the stored one or
    creating (and persisting) a new one on first checkout."""
    customer_id = await supabase_admin.get_stripe_customer_id(user["id"])
    if customer_id:
        return customer_id
    customer = await asyncio.to_thread(
        stripe.Customer.create,
        email=user["email"] or None,
        metadata={"supabase_user_id": user["id"]},
    )
    customer_id = customer.id
    # remember it now, so an abandoned checkout still reuses this customer
    await supabase_admin.update_profile(user["id"], {"stripe_customer_id": customer_id})
    logger.info("[BILLING] created Stripe customer %s for user %s", customer_id, user["id"])
    return customer_id


@router.post("/billing/create-checkout-session")
async def create_checkout_session(user: dict = Depends(auth.get_current_user)):
    """Start a Stripe Checkout subscription session for the current user.

    Reuses one Stripe customer per user: it is created on the first checkout
    and stored on the profile, so repeat checkouts map to the same customer.
    """
    if not (settings.STRIPE_SECRET_KEY and settings.STRIPE_PRICE_ID):
        raise HTTPException(status_code=500, detail="Stripe is not configured on the server")

    try:
        customer_id = await _get_or_create_customer(user)
        # Stripe SDK calls are blocking — run them off the event loop.
        session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            mode="subscription",
            line_items=[{"price": settings.STRIPE_PRICE_ID, "quantity": 1}],
            success_url=(
                f"{settings.FRONTEND_URL}/billing/success"
                "?session_id={CHECKOUT_SESSION_ID}"
            ),
            cancel_url=f"{settings.FRONTEND_URL}/pricing",
            customer=customer_id,
            # carry the Supabase user id so the webhook knows who paid
            client_reference_id=user["id"],
            metadata={"supabase_user_id": user["id"]},
            subscription_data={"metadata": {"supabase_user_id": user["id"]}},
        )
    except Exception as exc:
        logger.error("[BILLING] checkout session creation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Could not start checkout")

    logger.info("[BILLING] checkout session created for user %s", user["id"])
    return {"url": session.url}


@router.post("/billing/portal")
async def create_portal_session(user: dict = Depends(auth.get_current_user)):
    """Open the Stripe Customer Portal so the user can update their payment
    method, view invoices, or cancel their subscription."""
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe is not configured on the server")

    customer_id = await supabase_admin.get_stripe_customer_id(user["id"])
    if not customer_id:
        raise HTTPException(status_code=400, detail="No subscription found for this account.")

    try:
        session = await asyncio.to_thread(
            stripe.billing_portal.Session.create,
            customer=customer_id,
            return_url=f"{settings.FRONTEND_URL}/dashboard",
        )
    except Exception as exc:
        logger.error("[BILLING] portal session creation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Could not open the billing portal")

    logger.info("[BILLING] portal session opened for user %s", user["id"])
    return {"url": session.url}


@router.post("/billing/webhook")
async def stripe_webhook(request: Request):
    """Receive Stripe events, verify the signature, and update the user's plan."""
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Stripe webhook secret not configured")

    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception as exc:
        logger.warning("[BILLING] webhook signature verification failed: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event["type"]
    obj = event["data"]["object"]
    logger.info("[BILLING] webhook event: %s", event_type)

    if event_type == "checkout.session.completed":
        # subscription purchased — grant Pro
        user_id = obj.get("client_reference_id") or (obj.get("metadata") or {}).get(
            "supabase_user_id"
        )
        if user_id:
            await supabase_admin.update_profile(
                user_id,
                {
                    "plan": "pro",
                    "stripe_customer_id": obj.get("customer"),
                    "stripe_subscription_id": obj.get("subscription"),
                    "subscription_status": "active",
                },
            )

    elif event_type == "customer.subscription.updated":
        # status changed (renewed, past_due, paused, …) — keep plan in sync
        user_id = (obj.get("metadata") or {}).get("supabase_user_id")
        status = obj.get("status")
        if user_id:
            await supabase_admin.update_profile(
                user_id,
                {
                    "plan": "pro" if status in ("active", "trialing") else "free",
                    "subscription_status": status,
                    "current_period_end": _ts_to_iso(obj.get("current_period_end")),
                },
            )

    elif event_type == "customer.subscription.deleted":
        # subscription ended — revoke Pro
        user_id = (obj.get("metadata") or {}).get("supabase_user_id")
        if user_id:
            await supabase_admin.update_profile(
                user_id,
                {"plan": "free", "subscription_status": obj.get("status") or "canceled"},
            )

    # Stripe only needs a 2xx to consider the event delivered.
    return {"received": True}
