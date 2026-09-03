# RelativeQs — task runner.
#   Local backend  -> Docker Compose (backend/docker-compose.yml)
#                     + a Cloudflare named tunnel publishing it at
#                       https://edge-relativeq.facades.trade
#   Local frontend -> Vite (npm)
#   Cloud          -> deploy_to_cloud.sh (Vercel UI -> the tunnel above)
#
# Run `make` or `make help` to list targets.

SHELL    := /bin/bash
COMPOSE  := docker compose --env-file deploy/.env -f backend/docker-compose.yml
DEPLOY   := ./deploy_to_cloud.sh
TUNNEL   := ./deploy/cf-tunnel.sh
SERVICE  := relqs-web-service
PROJECT  := relqs_backend
FLY_APP  ?= relativeqs-api

# Pass extra flags through, e.g.  make deploy ARGS="-n"  /  make quotes ARGS="QQQ SMH"
ARGS ?=

.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
help: ## Show this help
	@awk 'BEGIN{FS=":.*##"; print "RelativeQs — make targets\n"} \
		/^# ===/{next} \
		/^[a-zA-Z0-9_-]+:.*##/{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2} \
		/^## /{printf "\n\033[1m%s\033[0m\n", substr($$0,4)}' $(MAKEFILE_LIST)

## Local — backend (Docker Compose)
be-up: ## Build + start the backend container (detached)
	$(COMPOSE) up --build -d

be-down: ## Stop and remove the backend container
	$(COMPOSE) down

be-restart: ## Restart the backend container
	$(COMPOSE) restart $(SERVICE)

be-build: ## Rebuild the backend image (no start)
	$(COMPOSE) build

be-logs: ## Tail backend logs (Ctrl-C to stop)
	$(COMPOSE) logs -f $(SERVICE)

be-ps: ## Show backend container status
	$(COMPOSE) ps

be-shell: ## Open a shell inside the running backend container
	$(COMPOSE) exec $(SERVICE) /bin/bash

## Local — Cloudflare tunnel (publishes the backend on a permanent hostname)
# The tunnel definition lives in Cloudflare; the container only holds a token.
# Create it once, then `be-up` starts the connector alongside the backend.
tunnel-create: ## Create (or adopt) the named tunnel + DNS record, write the token
	$(TUNNEL) create

tunnel-status: ## Show tunnel state, ingress, DNS, connector and a public health probe
	@$(TUNNEL) status

tunnel-delete: ## Destroy the tunnel and its DNS record (prompts; ARGS=-y to skip)
	$(TUNNEL) delete $(ARGS)

## Local — frontend (Vite)
fe-install: ## Install frontend dependencies
	npm install

fe-dev: ## Run the Vite dev server (localhost:5173)
	npm run dev

fe-build: ## Production build into dist/
	npm run build

fe-preview: ## Serve the built dist/ locally (localhost:4173)
	npm run preview

fe-test: ## Run frontend tests (vitest)
	npm run test

## Local — combined
dev: be-up ## Start backend (docker) then run frontend dev server
	@echo "backend up — starting frontend dev server..."
	npm run dev

down: be-down ## Stop the local backend stack

## Cloud — deploy (Fly.io + Vercel)
deploy: ## Deploy both backend and frontend (ARGS for extra flags)
	$(DEPLOY) $(ARGS)

deploy-be: ## Deploy only the backend to Fly.io
	$(DEPLOY) -b $(ARGS)

deploy-fe: ## Deploy only the frontend to Vercel
	$(DEPLOY) -f $(ARGS)

deploy-dry: ## Dry-run the full deploy (prints commands, runs nothing)
	$(DEPLOY) -n -y

# The backend is a SINGLETON poller: it writes bars:<date> and snapshot:latest
# into the shared Upstash Redis. Fly and a local container must never run at
# the same time or they clobber each other's bars. Stop Fly first.
fly-stop: ## Stop the Fly machine(s) so the local backend is the only poller
	@flyctl machine list --app $(FLY_APP) -q | xargs -r -n1 flyctl machine stop --app $(FLY_APP)
	@flyctl machine list --app $(FLY_APP)

fly-start: ## Restart the stopped Fly machine(s) (stop the local backend first)
	@flyctl machine list --app $(FLY_APP) -q | xargs -r -n1 flyctl machine start --app $(FLY_APP)
	@flyctl machine list --app $(FLY_APP)

fly-retire: ## Destroy the Fly machine(s) for good (redeploy with 'make deploy-be')
	flyctl scale count 0 --app $(FLY_APP) --yes
	@flyctl machine list --app $(FLY_APP)

takeover: fly-stop be-up ## Stop Fly, then start the local backend on the same Upstash
	@echo "✓ Fly stopped, local backend up on :8001 — it now owns the Upstash keys"

## Cloud — checks
vercel-check: ## Verify Vercel login / token
	@vercel whoami && echo "OK: logged in to Vercel" || echo "FAIL: run 'vercel login' or export VERCEL_TOKEN"

fly-check: ## Verify Fly login / token
	@flyctl auth whoami && echo "OK: logged in to Fly" || echo "FAIL: run 'fly auth login' or export FLY_API_TOKEN"

## Cloud — secrets / env
secrets: ## Push backend/.env -> Fly secrets (api keys & tokens)
	$(DEPLOY) --sync-secrets

deploy-be-secrets: ## Sync secrets, then deploy the backend
	$(DEPLOY) -b --sync-secrets $(ARGS)

## Utilities
clear-cache: ## Clear Redis market-data cache (prompts for confirmation)
	./dev-utils/clear-redis-cache.sh $(ARGS)

quotes: ## Fetch live quotes, e.g. make quotes ARGS="QQQ SMH XLK"
	./dev-utils/fetch-quotes.py $(ARGS)

## Docker cleanup
prune: ## Remove THIS project's exited containers, dangling images & old build cache (other stacks untouched)
	@echo "→ exited containers ($(PROJECT))…"
	-docker ps -aq --filter status=exited --filter label=com.docker.compose.project=$(PROJECT) | xargs -r docker rm
	@echo "→ dangling images ($(PROJECT))…"
	-docker image prune -f --filter label=com.docker.compose.project=$(PROJECT)
	@echo "→ unused build cache older than a week…"
	-docker builder prune -f --filter until=168h
	@echo "✓ prune complete"

.PHONY: help be-up be-down be-restart be-build be-logs be-ps be-shell \
        fe-install fe-dev fe-build fe-preview fe-test dev down \
        tunnel-create tunnel-status tunnel-delete \
        deploy deploy-be deploy-fe deploy-dry vercel-check fly-check \
        fly-stop fly-start fly-retire takeover \
        secrets deploy-be-secrets clear-cache quotes prune
