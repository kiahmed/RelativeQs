#!/usr/bin/env bash
# Clear the backend's Redis cache (snapshot, QQQ score, price history).
#
# Everything repopulates automatically: the background poll loop rewrites
# snapshot:latest / qqq_score:latest within one cycle (~POLL_INTERVAL_SECONDS),
# and history:* entries are refetched from the data provider on the next call.
#
# usage:
#   ./clear-redis-cache.sh           # delete app keys (snapshot, qqq_score, history)
#   ./clear-redis-cache.sh --all     # flush the entire db
#
# env overrides:
#   REDIS_CONTAINER  docker container name (default: postiz-redis)
#   REDIS_DB         redis db number       (default: 1, matches docker-compose REDIS_URL)

set -euo pipefail

REDIS_CONTAINER="${REDIS_CONTAINER:-postiz-redis}"
REDIS_DB="${REDIS_DB:-1}"

rcli() {
  docker exec "$REDIS_CONTAINER" redis-cli -n "$REDIS_DB" "$@"
}

if ! docker ps --format '{{.Names}}' | grep -qx "$REDIS_CONTAINER"; then
  echo "error: redis container '$REDIS_CONTAINER' is not running" >&2
  exit 1
fi

# red warning + explicit confirmation before touching anything
RED='\033[0;31m'
NC='\033[0m'
printf "${RED}WARNING: this will delete ALL cached market data for ALL live users.${NC}\n"
printf "${RED}Dashboards may show stale/empty data until the next poll cycle repopulates the cache.${NC}\n"
read -r -p "Are you sure? [y/N] " answer
case "$answer" in
  [yY]|[yY][eE][sS]) ;;
  *) echo "aborted, nothing deleted"; exit 0 ;;
esac

if [ "${1:-}" = "--all" ]; then
  rcli FLUSHDB > /dev/null
  echo "flushed redis db $REDIS_DB"
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
