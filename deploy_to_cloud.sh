#!/usr/bin/env bash
#
# deploy_to_cloud.sh — deploy RelativeQs to Vercel (frontend) and Fly.io (backend).
#
#   Frontend  ->  Vercel             ->  https://relativeqs.vercel.app
#   Backend   ->  Fly.io             ->  https://relativeqs-api.fly.dev
#
# Run `./deploy_to_cloud.sh --help` for usage.

set -euo pipefail

# ----------------------------------------------------------------------------
# Config (override via env, e.g. FLY_APP=foo ./deploy_to_cloud.sh -b)
# ----------------------------------------------------------------------------
FLY_APP="${FLY_APP:-relativeqs-api}"
VERCEL_PROJECT="${VERCEL_PROJECT:-relativeqs}"
FLY_REGION="${FLY_REGION:-iad}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
DEPLOY_DIR="$ROOT_DIR/deploy"
FLY_CONFIG="$DEPLOY_DIR/fly.toml"
DIST_DIR="$ROOT_DIR/dist"
PROD_ENV_FILE="$DEPLOY_DIR/.env.production"
DEPLOY_ENV_FILE="$DEPLOY_DIR/.env"
BACKEND_ENV_FILE="$BACKEND_DIR/.env"

# ----------------------------------------------------------------------------
# Flags
# ----------------------------------------------------------------------------
DO_FRONTEND=false
DO_BACKEND=false
DRY_RUN=false
SKIP_BUILD=false
SYNC_SECRETS=false
ASSUME_YES=false

# ----------------------------------------------------------------------------
# Pretty output
# ----------------------------------------------------------------------------
if [ -t 1 ]; then
  BOLD='\033[1m'; DIM='\033[2m'; RED='\033[0;31m'; GREEN='\033[0;32m'
  YELLOW='\033[0;33m'; BLUE='\033[0;34m'; NC='\033[0m'
else
  BOLD=''; DIM=''; RED=''; GREEN=''; YELLOW=''; BLUE=''; NC=''
fi
info()  { printf "${BLUE}==>${NC} %s\n" "$*"; }
ok()    { printf "${GREEN}✓${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}!${NC} %s\n" "$*"; }
die()   { printf "${RED}✗ %s${NC}\n" "$*" >&2; exit 1; }

# Run a command, or just print it in dry-run mode.
run() {
  if $DRY_RUN; then
    printf "${DIM}[dry-run]${NC} %s\n" "$*"
  else
    printf "${DIM}\$ %s${NC}\n" "$*"
    "$@"
  fi
}

usage() {
  cat <<EOF
${BOLD}deploy_to_cloud.sh${NC} — deploy RelativeQs to Vercel + Fly.io

${BOLD}USAGE${NC}
  ./deploy_to_cloud.sh [targets] [options]

${BOLD}TARGETS${NC} (default: both)
  -f, --frontend       Deploy only the frontend (Vercel)
  -b, --backend        Deploy only the backend (Fly.io)
      (no target)      Deploy both

${BOLD}OPTIONS${NC}
  -n, --dry-run        Print every command without running it
      --skip-build     Reuse existing .vercel/output (skip the frontend build)
      --sync-secrets   Push backend/.env -> Fly secrets, then exit
                       (also runnable alongside -b to sync before deploy)
  -y, --yes            Don't prompt for confirmation
  -h, --help           Show this help

${BOLD}CONFIG${NC} (env overrides)
  FLY_APP=$FLY_APP
  VERCEL_PROJECT=$VERCEL_PROJECT
  FLY_REGION=$FLY_REGION

${BOLD}EXAMPLES${NC}
  ./deploy_to_cloud.sh                 # build + deploy frontend and backend
  ./deploy_to_cloud.sh -f              # frontend only
  ./deploy_to_cloud.sh -b --sync-secrets
  ./deploy_to_cloud.sh -n              # dry run, see what would happen
  ./deploy_to_cloud.sh -f --skip-build # redeploy existing prebuilt output

${BOLD}PREREQS${NC}
  - flyctl      (https://fly.io/docs/flyctl/install)  + 'fly auth login'
  - vercel      (npm i -g vercel)                     + 'vercel login'
  - deploy/.env.production  (copy from .env.production.example, fill in)
EOF
}

# ----------------------------------------------------------------------------
# Parse args
# ----------------------------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    -f|--frontend)    DO_FRONTEND=true ;;
    -b|--backend)     DO_BACKEND=true ;;
    -n|--dry-run)     DRY_RUN=true ;;
    --skip-build)     SKIP_BUILD=true ;;
    --sync-secrets)   SYNC_SECRETS=true ;;
    -y|--yes)         ASSUME_YES=true ;;
    -h|--help)        usage; exit 0 ;;
    *) die "unknown option: $1  (try --help)" ;;
  esac
  shift
done

# No explicit target => do both (unless this is a secrets-only run).
if ! $DO_FRONTEND && ! $DO_BACKEND; then
  if $SYNC_SECRETS; then
    DO_BACKEND=false   # secrets-only: handled below, no deploy
  else
    DO_FRONTEND=true; DO_BACKEND=true
  fi
fi

confirm() {
  $ASSUME_YES && return 0
  $DRY_RUN && return 0
  printf "${YELLOW}%s${NC} [y/N] " "$1"
  read -r ans
  case "$ans" in [yY]|[yY][eE][sS]) return 0 ;; *) return 1 ;; esac
}

need() {
  command -v "$1" >/dev/null 2>&1 && return 0
  $DRY_RUN && { warn "$1 not found (ignored in dry-run) — $2"; return 0; }
  die "$1 not found — $2"
}

# Verify we're authenticated to Fly. Honors FLY_API_TOKEN (CI) or 'fly auth login'.
check_fly_auth() {
  $DRY_RUN && { warn "skipping Fly auth check (dry-run)"; return 0; }
  if flyctl auth whoami >/dev/null 2>&1; then
    ok "Fly auth OK ($(flyctl auth whoami 2>/dev/null))"
  else
    die "not logged in to Fly — run 'fly auth login' or export FLY_API_TOKEN=..."
  fi
}

# Verify we're authenticated to Vercel. Honors VERCEL_TOKEN (CI) or 'vercel login'.
check_vercel_auth() {
  $DRY_RUN && { warn "skipping Vercel auth check (dry-run)"; return 0; }
  if vercel whoami >/dev/null 2>&1; then
    ok "Vercel auth OK ($(vercel whoami 2>/dev/null))"
  else
    die "not logged in to Vercel — run 'vercel login' or export VERCEL_TOKEN=..."
  fi
}

# ----------------------------------------------------------------------------
# Backend secrets: backend/.env -> Fly secrets
# ----------------------------------------------------------------------------
# Create the Fly app if it doesn't exist yet (no-op if it does). Both secrets
# and deploy need the app record to exist first.
ensure_fly_app() {
  $DRY_RUN && return 0
  if flyctl apps list 2>/dev/null | grep -qw "$FLY_APP"; then return 0; fi
  warn "Fly app '$FLY_APP' not found — creating it"
  confirm "Create Fly app '$FLY_APP'?" || die "aborted"
  run flyctl apps create "$FLY_APP"
}

sync_secrets() {
  need flyctl "install flyctl + run 'fly auth login'"
  check_fly_auth
  ensure_fly_app
  [ -f "$BACKEND_ENV_FILE" ] || die "no $BACKEND_ENV_FILE to read secrets from"
  info "Syncing secrets from backend/.env -> Fly app '$FLY_APP'"

  # Build a KEY=VALUE list, skipping comments, blanks, and placeholder values.
  local args=()
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"                              # strip CR (CRLF files)
    line="${line#"${line%%[![:space:]]*}"}"           # ltrim
    [ -z "$line" ] && continue
    case "$line" in \#*) continue ;; esac
    case "$line" in *=*) ;; *) continue ;; esac
    local key="${line%%=*}"
    local val="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"              # rtrim key
    # strip one layer of surrounding quotes (e.g. REDIS_URL="rediss://...")
    case "$val" in
      \"*\") val="${val#\"}"; val="${val%\"}" ;;
      \'*\') val="${val#\'}"; val="${val%\'}" ;;
    esac
    # skip obvious unfilled placeholders
    case "$val" in your-*|YOUR-*|sk_test_your*|whsec_your*|price_your*|re_your*)
      warn "skipping placeholder $key"; continue ;; esac
    [ -z "$val" ] && continue
    args+=("$key=$val")
  done < "$BACKEND_ENV_FILE"

  [ ${#args[@]} -gt 0 ] || die "no usable secrets found in backend/.env"
  info "Will set ${#args[@]} secrets: ${args[*]%%=*}"
  run flyctl secrets set --app "$FLY_APP" "${args[@]}"
  ok "secrets synced"
}

# ----------------------------------------------------------------------------
# Backend: Fly.io
# ----------------------------------------------------------------------------
deploy_backend() {
  need flyctl "install flyctl + run 'fly auth login'"
  check_fly_auth
  info "Deploying backend -> Fly app '$FLY_APP' (region $FLY_REGION)"

  # 'deploy' creates machines but not the app record — make sure it exists first.
  ensure_fly_app

  # Build context = backend/ (where the Dockerfile and source live); config and
  # dockerfile are passed explicitly so paths don't get resolved relative to
  # deploy/ (where fly.toml lives).
  # --ha=false: this backend is a SINGLETON poller (one background loop hitting
  # Yahoo + writing Redis). A 2nd HA machine would duplicate every fetch and race
  # on the cache, so we deliberately run exactly one always-on machine.
  run flyctl deploy "$BACKEND_DIR" \
    --config "$FLY_CONFIG" \
    --dockerfile "$BACKEND_DIR/Dockerfile" \
    --app "$FLY_APP" \
    --regions "$FLY_REGION" \
    --ha=false
  ok "backend deployed -> https://$FLY_APP.fly.dev"

  # Keep the frontend pointed at the actual backend: write the live Fly URL into
  # deploy/.env.production so the next `make deploy-fe` bakes in the right host.
  write_backend_url
}

# Point the frontend prod env at the deployed backend (derived from $FLY_APP).
# Runs after a backend deploy; safe to call standalone too.
#
# The backend URL in deploy/.env.production has TWO possible owners:
#   - this script, when Fly hosts the backend        -> https://$FLY_APP.fly.dev
#   - deploy/cf-tunnel.sh, when a Cloudflare named tunnel fronts a locally
#     hosted backend                                 -> https://$RELQS_API_HOST
# Only one can be correct at a time. If deploy/.env names a tunnel host, the
# tunnel is the front door: stamping the Fly URL here would silently point the
# next frontend build at a backend that may not even be running. So we detect
# that case and leave the file alone rather than clobbering it.
write_backend_url() {
  [ -f "$PROD_ENV_FILE" ] || { warn "no $PROD_ENV_FILE — skipping frontend URL update"; return 0; }

  local tunnel_host=""
  if [ -f "$DEPLOY_ENV_FILE" ]; then
    tunnel_host=$(sed -n -E \
      's/^[[:space:]]*RELQS_API_HOST[[:space:]]*=[[:space:]]*"?([^"#[:space:]]+)"?.*/\1/p' \
      "$DEPLOY_ENV_FILE" | tail -n1)
  fi

  if [ -n "$tunnel_host" ]; then
    warn "deploy/.env sets RELQS_API_HOST=$tunnel_host — the Cloudflare tunnel owns"
    warn "$PROD_ENV_FILE, so it will NOT be rewritten to the Fly URL."
    warn "To resync it to the tunnel host: ./deploy/cf-tunnel.sh create"
    return 0
  fi

  local http_url="https://$FLY_APP.fly.dev"
  local ws_url="wss://$FLY_APP.fly.dev/ws/market"
  info "Updating $PROD_ENV_FILE -> backend $http_url"
  if $DRY_RUN; then
    printf "${DIM}[dry-run]${NC} set VITE_RELQS_BACKEND_URL=%s / VITE_RELQS_WS_URL=%s\n" "$http_url" "$ws_url"
    return 0
  fi
  # Replace the two URL lines in place (they always exist in our template).
  sed -i -E "s#^VITE_RELQS_BACKEND_URL=.*#VITE_RELQS_BACKEND_URL=${http_url}#" "$PROD_ENV_FILE"
  sed -i -E "s#^VITE_RELQS_WS_URL=.*#VITE_RELQS_WS_URL=${ws_url}#" "$PROD_ENV_FILE"
  ok "frontend backend URL synced"
}

# ----------------------------------------------------------------------------
# Frontend: build + Vercel
# ----------------------------------------------------------------------------
deploy_frontend() {
  need vercel "npm i -g vercel + run 'vercel login'"
  check_vercel_auth

  if [ ! -f "$PROD_ENV_FILE" ]; then
    $DRY_RUN && warn "missing $PROD_ENV_FILE (ignored in dry-run)" \
             || die "missing $PROD_ENV_FILE — copy deploy/.env.production.example and fill it in"
  fi

  # Link the local dir to a Vercel project named '$VERCEL_PROJECT' on first run.
  # This pins the public URL to https://$VERCEL_PROJECT.vercel.app.
  if ! $DRY_RUN && [ ! -f "$ROOT_DIR/.vercel/project.json" ]; then
    warn "no Vercel project link found — linking as '$VERCEL_PROJECT'"
    confirm "Link this directory to Vercel project '$VERCEL_PROJECT'?" || die "aborted"
    run vercel link --yes --project "$VERCEL_PROJECT"
  fi

  # Vite auto-loads .env.production (production build mode), so the prod VITE_*
  # vars get inlined — no need to set env in the Vercel dashboard.
  run cp "$PROD_ENV_FILE" "$ROOT_DIR/.env.production"

  if $SKIP_BUILD; then
    warn "--skip-build: deploying existing .vercel/output as-is"
    [ -d "$ROOT_DIR/.vercel/output" ] || die "nothing prebuilt — run without --skip-build first"
  else
    # 'vercel build' refuses to run until the project's settings (framework,
    # build command, output dir) exist locally — a fresh 'vercel link' writes
    # only projectId/orgId, so a first deploy fails with
    # "project_settings_required" without this. Idempotent, so run it always.
    info "Pulling Vercel project settings"
    run vercel pull --yes --environment=production

    info "Building frontend with prod env ($PROD_ENV_FILE)"
    run vercel build --prod
    ok "built -> .vercel/output"
  fi

  info "Deploying frontend -> Vercel project '$VERCEL_PROJECT'"
  run vercel deploy --prebuilt --prod --yes
  ok "frontend deployed -> https://$VERCEL_PROJECT.vercel.app"
}

# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
$DRY_RUN && warn "DRY RUN — no commands will execute"

if $SYNC_SECRETS; then
  sync_secrets
  # If --sync-secrets was the only intent (no target flags), we're done.
  $DO_BACKEND || { ok "done"; exit 0; }
fi

$DO_BACKEND  && deploy_backend
$DO_FRONTEND && deploy_frontend

ok "all done"
