#!/usr/bin/env bash
# Update one or more columns of public.profiles by user email.
# Uses the Supabase service_role key from backend/.env (bypasses RLS).
#
# usage:
#   ./update-profile.sh <email> <column=value> [<column=value> ...]
#
# examples:
#   ./update-profile.sh user@example.com plan=pro
#   ./update-profile.sh user@example.com plan=pro alerts_enabled=true
#   ./update-profile.sh user@example.com full_name="Alice Example"
#
# values that parse as JSON (numbers, true/false/null) are sent as that type;
# everything else is sent as a string.

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "usage: $(basename "$0") <email> <column=value> [<column=value> ...]" >&2
  exit 1
fi

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
ENV_FILE="${ENV_FILE:-$SCRIPT_DIR/../backend/.env}"
[ -f "$ENV_FILE" ] || { echo "env file not found at $ENV_FILE" >&2; exit 1; }

# Pull only the keys we need — sourcing the whole file is fragile (CRLF,
# unquoted special chars, multi-line values). sed strips trailing \r and
# surrounding quotes.
read_env() {
  grep -E "^${1}=" "$ENV_FILE" | tail -1 \
    | sed -e 's/^[^=]*=//' -e 's/\r$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
}
SUPABASE_URL=$(read_env SUPABASE_URL)
SUPABASE_SERVICE_KEY=$(read_env SUPABASE_SERVICE_KEY)

: "${SUPABASE_URL:?SUPABASE_URL not set in $ENV_FILE}"
: "${SUPABASE_SERVICE_KEY:?SUPABASE_SERVICE_KEY not set in $ENV_FILE}"

EMAIL="$1"; shift

JSON=$(jq -n '{}')
for kv in "$@"; do
  case "$kv" in
    *=*) ;;
    *) echo "bad arg '$kv' — expected column=value" >&2; exit 1;;
  esac
  k="${kv%%=*}"
  v="${kv#*=}"
  JSON=$(jq --arg k "$k" --arg v "$v" \
    '. + {($k): ($v | (fromjson? // .))}' <<<"$JSON")
done

encoded_email=$(jq -nr --arg e "$EMAIL" '$e|@uri')

resp=$(curl -sS -w '\n%{http_code}' -X PATCH \
  "$SUPABASE_URL/rest/v1/profiles?email=eq.$encoded_email" \
  -H "apikey: $SUPABASE_SERVICE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
  -H "Content-Type: application/json" \
  -H "Prefer: return=representation" \
  --data "$JSON")

body=$(echo "$resp" | head -n -1)
code=$(echo "$resp" | tail -n 1)

if [ "$code" -ge 400 ]; then
  echo "HTTP $code" >&2
  echo "$body" >&2
  exit 1
fi

if [ -z "$body" ] || [ "$body" = "[]" ]; then
  echo "no profile found for email: $EMAIL" >&2
  exit 1
fi

echo "$body" | jq .
