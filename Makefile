# RelativeQs — task runner.
#   Local backend  -> Docker Compose (backend/docker-compose.yml)
#   Local frontend -> Vite (npm)
#   Cloud          -> deploy_to_cloud.sh (Fly.io backend + Vercel UI)
#
# Run `make` or `make help` to list targets.

SHELL    := /bin/bash
COMPOSE  := docker compose -f backend/docker-compose.yml
DEPLOY   := ./deploy_to_cloud.sh
SERVICE  := relqs-web-service
PROJECT  := relqs_backend

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
        deploy deploy-be deploy-fe deploy-dry vercel-check fly-check \
        secrets deploy-be-secrets clear-cache quotes prune
