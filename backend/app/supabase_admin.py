"""
Server-side writes to Supabase using the service_role key.

The service_role key bypasses Row Level Security, so this module is the
*only* place the backend mutates the `profiles` table. It must never be
exposed to the browser.
"""

import logging
from typing import Optional

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)


async def update_profile(user_id: str, fields: dict) -> bool:
    """PATCH a row in public.profiles for the given user. Returns True on success."""
    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY):
        logger.error("[SUPABASE] SUPABASE_URL / SUPABASE_SERVICE_KEY not configured")
        return False

    url = settings.SUPABASE_URL.rstrip("/") + "/rest/v1/profiles"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    params = {"id": f"eq.{user_id}"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.patch(
                url, headers=headers, params=params, json=fields, timeout=15
            ) as resp:
                if resp.status not in (200, 204):
                    body = await resp.text()
                    logger.error(
                        "[SUPABASE] profile update failed (%s): %s", resp.status, body
                    )
                    return False
                logger.info("[SUPABASE] profile %s updated: %s", user_id, list(fields))
                return True
    except Exception as exc:
        logger.error("[SUPABASE] profile update error for %s: %s", user_id, exc)
        return False


async def list_alert_recipients() -> list:
    """Return [{id, email}] for Pro users who have regime alerts enabled."""
    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY):
        return []
    url = settings.SUPABASE_URL.rstrip("/") + "/rest/v1/profiles"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
    }
    params = {"select": "id,email", "plan": "eq.pro", "alerts_enabled": "is.true"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params, timeout=15) as resp:
                if resp.status != 200:
                    logger.error("[SUPABASE] list_alert_recipients failed (%s)", resp.status)
                    return []
                return await resp.json()
    except Exception as exc:
        logger.error("[SUPABASE] list_alert_recipients error: %s", exc)
        return []


async def get_alerts_enabled(user_id: str) -> bool:
    """Read a user's regime-alert preference from public.profiles."""
    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY):
        return False
    url = settings.SUPABASE_URL.rstrip("/") + "/rest/v1/profiles"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
    }
    params = {"id": f"eq.{user_id}", "select": "alerts_enabled"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params, timeout=15) as resp:
                if resp.status != 200:
                    return False
                rows = await resp.json()
                return bool(rows[0]["alerts_enabled"]) if rows else False
    except Exception as exc:
        logger.error("[SUPABASE] get_alerts_enabled error for %s: %s", user_id, exc)
        return False


async def _read_profile_field(user_id: str, column: str):
    """Read a single column from a user's profiles row, or None."""
    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY):
        return None
    url = settings.SUPABASE_URL.rstrip("/") + "/rest/v1/profiles"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
    }
    params = {"id": f"eq.{user_id}", "select": column}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params, timeout=15) as resp:
                if resp.status != 200:
                    return None
                rows = await resp.json()
                return rows[0][column] if rows else None
    except Exception as exc:
        logger.error("[SUPABASE] read %s error for %s: %s", column, user_id, exc)
        return None


async def get_profile_plan(user_id: str) -> Optional[str]:
    """Read a user's current plan from public.profiles (server-side)."""
    return await _read_profile_field(user_id, "plan")


async def get_stripe_customer_id(user_id: str) -> Optional[str]:
    """Read a user's stored Stripe customer id from public.profiles."""
    return await _read_profile_field(user_id, "stripe_customer_id")
