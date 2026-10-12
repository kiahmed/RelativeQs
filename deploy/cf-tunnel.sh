#!/usr/bin/env bash
#
# cf-tunnel.sh — manage the Cloudflare *named* tunnel that publishes the local
# RelativeQs backend on a permanent HTTPS hostname.
#
#   browser -> https://edge-relativeq.facades.trade  (Cloudflare edge)
#           -> relqs-cloudflared (this tunnel)
#           -> http://relativeq-backend:8000        (compose network)
#
# A *named* tunnel keeps the same hostname across restarts, rebuilds and host
# moves — which is why the Vercel frontend can bake the URL in at build time
# instead of discovering a rotating *.trycloudflare.com address at runtime.
#
# The tunnel definition (name, ingress, DNS) lives in Cloudflare; the container
# only holds a connector token. So `delete` really does destroy it, and
# `create` is idempotent — re-running it adopts the existing tunnel.
#
# Usage:  ./deploy/cf-tunnel.sh {create|status|delete} [-y]
# Driven by:  make tunnel-create / tunnel-status / tunnel-delete
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/deploy/.env"
PROD_ENV_FILE="$ROOT_DIR/deploy/.env.production"

if [ -t 1 ]; then
  BOLD='\033[1m'; DIM='\033[2m'; RED='\033[0;31m'; GREEN='\033[0;32m'
  YELLOW='\033[0;33m'; BLUE='\033[0;34m'; NC='\033[0m'
else
  BOLD=''; DIM=''; RED=''; GREEN=''; YELLOW=''; BLUE=''; NC=''
fi
info() { printf "${BLUE}==>${NC} %s\n" "$*"; }
ok()   { printf "${GREEN}✓${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}!${NC} %s\n" "$*"; }
die()  { printf "${RED}✗ %s${NC}\n" "$*" >&2; exit 1; }

CMD="${1:-}"; shift || true
ASSUME_YES=false
for a in "$@"; do [ "$a" = "-y" ] || [ "$a" = "--yes" ] && ASSUME_YES=true; done

[ -f "$ENV_FILE" ] || die "missing $ENV_FILE — copy deploy/.env.example and fill in CF_API_TOKEN / CF_ACCOUNT_ID"
set -a; . "$ENV_FILE"; set +a

TUNNEL_NAME="${RELQS_TUNNEL_NAME:-relativeq-backend-tunnel}"
API_HOST="${RELQS_API_HOST:-edge-relativeq.facades.trade}"
ORIGIN_SERVICE="${RELQS_ORIGIN_SERVICE:-http://relativeq-backend:8000}"
CF_ZONE="${RELQS_CF_ZONE:-facades.trade}"

: "${CF_API_TOKEN:?CF_API_TOKEN must be set in deploy/.env}"
: "${CF_ACCOUNT_ID:?CF_ACCOUNT_ID must be set in deploy/.env}"

CF_API="https://api.cloudflare.com/client/v4"

# cf METHOD PATH [JSON_BODY] -> raw response body on stdout
cf() {
  local method="$1" path="$2" body="${3:-}"
  if [ -n "$body" ]; then
    curl -sS -X "$method" "$CF_API$path" \
      -H "Authorization: Bearer $CF_API_TOKEN" \
      -H "Content-Type: application/json" --data "$body"
  else
    curl -sS -X "$method" "$CF_API$path" \
      -H "Authorization: Bearer $CF_API_TOKEN" \
      -H "Content-Type: application/json"
  fi
}

# pyq EXPR  — read JSON on stdin as `d`, print EXPR (blank on any failure).
pyq() {
  python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
try:
    v = ($1)
except Exception:
    sys.exit(0)
if v is None:
    sys.exit(0)
print(v if isinstance(v, str) else json.dumps(v))
"
}

# Fail loudly when the API says success:false — a silent empty result here
# would otherwise look like "nothing there yet" and make create() do the
# wrong thing.
cf_ok() {
  local resp="$1" what="$2"
  local okflag; okflag=$(printf '%s' "$resp" | pyq "d.get('success')")
  [ "$okflag" = "true" ] && return 0
  local errs; errs=$(printf '%s' "$resp" | pyq "d.get('errors')")
  die "Cloudflare API rejected $what: ${errs:-unknown error}"
}

# upsert_env KEY VALUE — set (or add) KEY=VALUE in deploy/.env, in place.
upsert_env() {
  local key="$1" val="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    python3 - "$ENV_FILE" "$key" "$val" <<'PY'
import sys
path, key, val = sys.argv[1], sys.argv[2], sys.argv[3]
lines = open(path).read().splitlines(True)
out = []
for line in lines:
    if line.split("=", 1)[0].strip() == key:
        out.append(f"{key}={val}\n")
    else:
        out.append(line)
open(path, "w").write("".join(out))
PY
  else
    printf '%s=%s\n' "$key" "$val" >> "$ENV_FILE"
  fi
}

tunnel_id_by_name() {
  cf GET "/accounts/$CF_ACCOUNT_ID/cfd_tunnel?name=$TUNNEL_NAME&is_deleted=false" \
    | pyq "next((t['id'] for t in (d.get('result') or []) if t['name']=='$TUNNEL_NAME'), None)"
}

zone_id() {
  cf GET "/zones?name=$CF_ZONE" \
    | pyq "next((z['id'] for z in (d.get('result') or [])), None)"
}

dns_record_id() {
  local zid="$1"
  cf GET "/zones/$zid/dns_records?name=$API_HOST" \
    | pyq "next((r['id'] for r in (d.get('result') or [])), None)"
}

# ---------------------------------------------------------------------------
create() {
  info "Tunnel '$TUNNEL_NAME' -> $ORIGIN_SERVICE, public at https://$API_HOST"

  local tid; tid=$(tunnel_id_by_name)
  if [ -n "$tid" ]; then
    ok "tunnel already exists (id $tid) — adopting it"
  else
    info "creating tunnel '$TUNNEL_NAME'"
    # config_src=cloudflare -> ingress is managed via the API/dashboard (below)
    # rather than a local config.yml, so the container needs only a token.
    local resp; resp=$(cf POST "/accounts/$CF_ACCOUNT_ID/cfd_tunnel" \
      "$(python3 -c "import json,sys; print(json.dumps({'name':sys.argv[1],'config_src':'cloudflare'}))" "$TUNNEL_NAME")")
    cf_ok "$resp" "tunnel create"
    tid=$(printf '%s' "$resp" | pyq "d['result']['id']")
    [ -n "$tid" ] || die "tunnel created but no id came back"
    ok "created tunnel $tid"
  fi

  info "writing ingress: $API_HOST -> $ORIGIN_SERVICE"
  local cfg; cfg=$(python3 -c "
import json, sys
host, svc = sys.argv[1], sys.argv[2]
print(json.dumps({'config': {'ingress': [
    {'hostname': host, 'service': svc},
    {'service': 'http_status:404'},
]}}))
" "$API_HOST" "$ORIGIN_SERVICE")
  local resp; resp=$(cf PUT "/accounts/$CF_ACCOUNT_ID/cfd_tunnel/$tid/configurations" "$cfg")
  cf_ok "$resp" "tunnel configuration"
  ok "ingress set"

  # DNS: the hostname is only reachable once a proxied CNAME points at
  # <tunnel-id>.cfargotunnel.com. Needs Zone:DNS:Edit on $CF_ZONE.
  local zid; zid=$(zone_id)
  if [ -z "$zid" ]; then
    warn "CF_API_TOKEN cannot see zone '$CF_ZONE' — skipping DNS."
    warn "Add this record by hand (Cloudflare -> $CF_ZONE -> DNS), or re-run"
    warn "with a token that has Zone:DNS:Edit on $CF_ZONE:"
    warn "    CNAME  ${API_HOST%%.$CF_ZONE}  ->  ${tid}.cfargotunnel.com   (Proxied)"
  else
    local rid; rid=$(dns_record_id "$zid")
    local body; body=$(python3 -c "
import json, sys
print(json.dumps({'type':'CNAME','name':sys.argv[1],
                  'content':sys.argv[2]+'.cfargotunnel.com',
                  'proxied':True,'ttl':1,
                  'comment':'RelativeQs backend tunnel'}))
" "$API_HOST" "$tid")
    if [ -n "$rid" ]; then
      resp=$(cf PUT "/zones/$zid/dns_records/$rid" "$body")
      cf_ok "$resp" "DNS update"
      ok "DNS record updated: $API_HOST -> $tid.cfargotunnel.com"
    else
      resp=$(cf POST "/zones/$zid/dns_records" "$body")
      cf_ok "$resp" "DNS create"
      ok "DNS record created: $API_HOST -> $tid.cfargotunnel.com"
    fi
  fi

  info "fetching connector token"
  resp=$(cf GET "/accounts/$CF_ACCOUNT_ID/cfd_tunnel/$tid/token")
  cf_ok "$resp" "tunnel token"
  local token; token=$(printf '%s' "$resp" | pyq "d['result']")
  [ -n "$token" ] || die "no connector token returned"
  upsert_env CF_TUNNEL_TOKEN "$token"
  upsert_env RELQS_TUNNEL_ID "$tid"
  ok "CF_TUNNEL_TOKEN written to deploy/.env"

  sync_frontend_url
  echo
  ok "tunnel ready — run 'make be-up' to start the backend + connector"
  printf "  API  ${BOLD}https://%s${NC}\n  WS   ${BOLD}wss://%s/ws/market${NC}\n" "$API_HOST" "$API_HOST"
}

# Keep the Vercel build env pointed at the tunnel hostname.
sync_frontend_url() {
  [ -f "$PROD_ENV_FILE" ] || { warn "no $PROD_ENV_FILE — skipping frontend URL sync"; return 0; }
  sed -i -E "s#^VITE_RELQS_BACKEND_URL=.*#VITE_RELQS_BACKEND_URL=https://${API_HOST}#" "$PROD_ENV_FILE"
  sed -i -E "s#^VITE_RELQS_WS_URL=.*#VITE_RELQS_WS_URL=wss://${API_HOST}/ws/market#" "$PROD_ENV_FILE"
  ok "deploy/.env.production -> https://$API_HOST"
}

# ---------------------------------------------------------------------------
status() {
  local tid; tid=$(tunnel_id_by_name)
  if [ -z "$tid" ]; then
    warn "no tunnel named '$TUNNEL_NAME' in this account — run 'make tunnel-create'"
    return 1
  fi

  printf "${BOLD}Tunnel${NC}\n"
  cf GET "/accounts/$CF_ACCOUNT_ID/cfd_tunnel/$tid" | python3 -c "
import sys, json
d = json.load(sys.stdin); r = d.get('result') or {}
conns = r.get('connections') or []
print(f\"  name        {r.get('name')}\")
print(f\"  id          {r.get('id')}\")
print(f\"  status      {r.get('status')}\")
print(f\"  created     {r.get('created_at')}\")
print(f\"  connections {len(conns)}\")
for c in conns:
    print(f\"    - {c.get('colo_name')}  origin={c.get('origin_ip')}  since={c.get('opened_at')}\")
"

  printf "\n${BOLD}Ingress${NC}\n"
  cf GET "/accounts/$CF_ACCOUNT_ID/cfd_tunnel/$tid/configurations" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for rule in ((d.get('result') or {}).get('config') or {}).get('ingress', []):
    h = rule.get('hostname') or '(catch-all)'
    print(f\"  {h}  ->  {rule.get('service')}\")
"

  printf "\n${BOLD}DNS${NC}\n"
  local zid; zid=$(zone_id)
  if [ -z "$zid" ]; then
    printf "  (token cannot read zone %s — check the record in the dashboard)\n" "$CF_ZONE"
  else
    cf GET "/zones/$zid/dns_records?name=$API_HOST" | python3 -c "
import sys, json
d = json.load(sys.stdin); rs = d.get('result') or []
if not rs:
    print('  (no record — the hostname will not resolve)')
for r in rs:
    print(f\"  {r['type']}  {r['name']}  ->  {r['content']}  proxied={r.get('proxied')}\")
"
  fi

  printf "\n${BOLD}Local connector${NC}\n"
  docker ps --filter name=relqs-cloudflared --format '  {{.Names}}  {{.Status}}' 2>/dev/null \
    | grep . || printf "  (relqs-cloudflared not running — 'make be-up')\n"

  printf "\n${BOLD}Public health probe${NC}\n"
  local code
  # curl -w always prints a status (000 when no response ever arrived), so a
  # `|| echo 000` fallback concatenates a second one and reports "HTTP 000000".
  # Swallow curl's exit status instead, then normalise an empty result.
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "https://$API_HOST/api/health" 2>/dev/null || true)
  [ -n "$code" ] || code=000
  if [ "$code" = "200" ]; then
    ok "https://$API_HOST/api/health -> 200"
  elif [ "$code" = "000" ]; then
    warn "https://$API_HOST/api/health -> no response"
    warn "  (hostname not resolving, or the edge cannot reach the connector)"
  fi
}

# ---------------------------------------------------------------------------
delete() {
  local tid; tid=$(tunnel_id_by_name)
  [ -n "$tid" ] || { warn "no tunnel named '$TUNNEL_NAME' — nothing to delete"; return 0; }

  if ! $ASSUME_YES; then
    printf "${YELLOW}About to DELETE tunnel '%s' (%s), its DNS record %s, and the local token.${NC}\n" \
      "$TUNNEL_NAME" "$tid" "$API_HOST"
    read -r -p "Type 'yes' to continue: " reply
    [ "$reply" = "yes" ] || die "aborted"
  fi

  # Stop the connector first, otherwise Cloudflare refuses to delete a tunnel
  # that still has active connections.
  if docker ps --format '{{.Names}}' | grep -q '^relqs-cloudflared$'; then
    info "stopping the local connector"
    docker stop relqs-cloudflared >/dev/null || true
  fi

  local zid; zid=$(zone_id)
  if [ -n "$zid" ]; then
    local rid; rid=$(dns_record_id "$zid")
    if [ -n "$rid" ]; then
      cf DELETE "/zones/$zid/dns_records/$rid" >/dev/null
      ok "DNS record $API_HOST removed"
    fi
  else
    warn "token cannot read zone $CF_ZONE — remove the $API_HOST CNAME by hand"
  fi

  local resp; resp=$(cf DELETE "/accounts/$CF_ACCOUNT_ID/cfd_tunnel/$tid")
  cf_ok "$resp" "tunnel delete"
  ok "tunnel '$TUNNEL_NAME' deleted"

  upsert_env CF_TUNNEL_TOKEN ""
  upsert_env RELQS_TUNNEL_ID ""
  ok "cleared CF_TUNNEL_TOKEN / RELQS_TUNNEL_ID in deploy/.env"
}

case "$CMD" in
  create) create ;;
  status) status ;;
  delete) delete ;;
  *) die "usage: $(basename "$0") {create|status|delete} [-y]" ;;
esac
