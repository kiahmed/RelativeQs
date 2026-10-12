#!/usr/bin/env bash
# Clear the backend's Redis cache (snapshot, QQQ score, price history).
#
# Everything repopulates automatically: the background poll loop rewrites
# snapshot:latest / qqq_score:latest within one cycle (~POLL_INTERVAL_SECONDS),
# and history:* entries are refetched from the data provider on the next call.
#
# Redis is the managed Upstash instance the backend (local or Fly) points at
# via REDIS_URL -- there's no local Redis container to exec into anymore.
#
# usage:
#   ./clear-redis-cache.sh           # delete app keys (snapshot, qqq_score, history)
#   ./clear-redis-cache.sh --all     # flush the entire db
#
# env overrides:
#   REDIS_URL  redis connection string (default: read from backend/.env;
#              an already-exported REDIS_URL takes precedence over the file)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ENV="$SCRIPT_DIR/../backend/.env"

if [ -z "${REDIS_URL:-}" ] && [ -f "$BACKEND_ENV" ]; then
  REDIS_URL="$(grep -E '^REDIS_URL=' "$BACKEND_ENV" | tail -n1 | cut -d'=' -f2-)"
  # strip matching surrounding quotes, if any
  REDIS_URL="${REDIS_URL%\"}"; REDIS_URL="${REDIS_URL#\"}"
  REDIS_URL="${REDIS_URL%\'}"; REDIS_URL="${REDIS_URL#\'}"
fi

if [ -z "${REDIS_URL:-}" ]; then
  echo "error: REDIS_URL is not set and not found in $BACKEND_ENV" >&2
  echo "set REDIS_URL (the Upstash URL) in backend/.env, or export it before running this script" >&2
  exit 1
fi

# Never print the URL itself (it carries a password) -- only a redacted host.
redis_host="$(printf '%s' "$REDIS_URL" | sed -E 's#^[A-Za-z]+://([^@/]*@)?##; s#[/?].*$##')"

if command -v redis-cli >/dev/null 2>&1; then
  rcli() {
    redis-cli -u "$REDIS_URL" "$@"
  }
else
  rcli() {
    docker run --rm redis:7-alpine redis-cli -u "$REDIS_URL" "$@"
  }
fi

echo "target: $redis_host"

# red warning + explicit confirmation before touching anything
RED='\033[0;31m'
NC='\033[0m'
printf "${RED}WARNING: this will delete ALL cached market data for ALL live users.${NC}\n"
printf "${RED}Dashboards may show stale/empty data until the next poll cycle repopulates the cache.${NC}\n"
printf "${RED}This is the shared Upstash instance -- local and any running cloud poller both read it.${NC}\n"
read -r -p "Are you sure? [y/N] " answer
case "$answer" in
  [yY]|[yY][eE][sS]) ;;
  *) echo "aborted, nothing deleted"; exit 0 ;;
esac

if [ "${1:-}" = "--all" ]; then
  rcli FLUSHDB > /dev/null
  echo "flushed redis at $redis_host"
  exit 0
fi

total=0
for pattern in 'snapshot:*' 'qqq_score:*' 'history:*'; do
  # --scan instead of KEYS so we never block redis
  keys=$(rcli --scan --pattern "$pattern")
  if [ -n "$keys" ]; then
    # shellcheck disable=SC2086
    count=$(rcli DEL $keys)
    echo "deleted $count key(s) matching $pattern"
    total=$((total + count))
  else
    echo "no keys matching $pattern"
  fi
done

echo "done: $total key(s) deleted (cache repopulates on next poll cycle / request)"
