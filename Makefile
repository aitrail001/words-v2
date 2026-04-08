SHELL := /bin/bash

PROJECT_NAME ?= words-stack
ENV_FILE ?= .env.stack.mac

DEV_DB_NAME ?= vocabapp_dev_full
TEST_DB_NAME ?= vocabapp_test_full
TEST_TEMPLATE_DB_NAME ?= vocabapp_test_template_full
SMOKE_TEMPLATE_DB_NAME ?= vocabapp_test_template_smoke
FULL_DUMP_PATH ?= $(HOME)/words-shared/postgres/dumps/vocabapp_full.dump

NUC_HOST ?= youruser@your-nuc-host
NUC_REPO_DIR ?= /srv/words/words-v2
NUC_ENV_FILE ?= .env.stack.nuc
NUC_SHARED_DATA_DIR ?= /srv/words-shared

INFRA_COMPOSE := docker compose -p $(PROJECT_NAME) --env-file $(ENV_FILE) -f compose.infra.yml
TOOLS_COMPOSE := docker compose -p $(PROJECT_NAME) --env-file $(ENV_FILE) -f compose.infra.yml -f compose.tools.yml
STACK_COMPOSE := docker compose -p $(PROJECT_NAME) --env-file $(ENV_FILE) -f compose.infra.yml -f compose.teststack.yml
E2E_COMPOSE := docker compose -p $(PROJECT_NAME) --env-file $(ENV_FILE) -f compose.infra.yml -f compose.teststack.yml -f compose.e2e.yml

.PHONY: help config chmod-scripts \
        volumes infra-up infra-down tools-up tools-down \
        stack-up stack-build stack-down stack-logs stack-smoke stack-full \
        db-bootstrap db-backup-dev db-backup-test db-restore-dev db-restore-test db-refresh-template db-create-run \
        backend-install frontend-install admin-install e2e-install \
        local-backend-dev local-frontend-dev local-admin-dev \
        test-backend test-frontend test-admin smoke-local \
        nuc-rsync-data deploy-nuc

help:
	@printf "%s\n" \
	  "make volumes               # create external docker volumes once" \
	  "make infra-up              # start postgres + redis" \
	  "make tools-up              # start pgAdmin + Redis Commander" \
	  "make db-bootstrap          # create long-lived databases" \
	  "make backend-install       # create backend venv and install deps" \
	  "make frontend-install      # install learner frontend deps" \
	  "make admin-install         # install admin frontend deps" \
	  "make e2e-install           # install Playwright deps" \
	  "make local-backend-dev     # run backend locally" \
	  "make local-frontend-dev    # run learner frontend locally" \
	  "make local-admin-dev       # run admin frontend locally" \
	  "make test-backend          # run backend pytest" \
	  "make test-frontend         # run learner frontend jest" \
	  "make test-admin            # run admin frontend jest" \
	  "make smoke-local           # run local Playwright smoke" \
	  "make stack-up              # start persistent test stack without rebuilding" \
	  "make stack-build           # rebuild/start persistent test stack" \
	  "make stack-smoke           # run Playwright smoke against running test stack" \
	  "make stack-full            # run full Playwright suite against running test stack" \
	  "make db-backup-dev         # dump dev DB to FULL_DUMP_PATH" \
	  "make db-backup-test        # dump test DB to FULL_DUMP_PATH" \
	  "make db-restore-dev        # restore dev DB from FULL_DUMP_PATH" \
	  "make db-restore-test       # restore test DB from FULL_DUMP_PATH" \
	  "make db-refresh-template   # refresh template DB from test DB" \
	  "make db-create-run         # create disposable DB cloned from template" \
	  "make deploy-nuc            # pull latest code on NUC and deploy"

config:
	$(STACK_COMPOSE) config >/dev/null

chmod-scripts:
	chmod +x scripts/db/*.sh scripts/deploy/*.sh

volumes:
	docker volume create words_pg_data
	docker volume create words_redis_data
	docker volume create words_uploads_data

infra-up: volumes
	$(INFRA_COMPOSE) up -d

infra-down:
	$(INFRA_COMPOSE) down --remove-orphans

tools-up: infra-up
	$(TOOLS_COMPOSE) --profile tools up -d

tools-down:
	$(TOOLS_COMPOSE) down --remove-orphans

db-bootstrap: infra-up chmod-scripts
	./scripts/db/bootstrap-long-lived.sh $(ENV_FILE)

stack-up: infra-up
	$(STACK_COMPOSE) up -d

stack-build: infra-up
	$(STACK_COMPOSE) up -d --build

stack-down:
	$(STACK_COMPOSE) down --remove-orphans

stack-logs:
	$(STACK_COMPOSE) logs -f --tail=200

stack-smoke:
	$(E2E_COMPOSE) --profile tests run --rm playwright npm run test:smoke:ci

stack-full:
	$(E2E_COMPOSE) --profile tests run --rm playwright npm run test:full

db-backup-dev: chmod-scripts
	./scripts/db/backup-db.sh $(ENV_FILE) $(DEV_DB_NAME) $(FULL_DUMP_PATH)

db-backup-test: chmod-scripts
	./scripts/db/backup-db.sh $(ENV_FILE) $(TEST_DB_NAME) $(FULL_DUMP_PATH)

db-restore-dev: chmod-scripts
	./scripts/db/restore-db-from-dump.sh $(ENV_FILE) $(DEV_DB_NAME) $(FULL_DUMP_PATH)

db-restore-test: chmod-scripts
	./scripts/db/restore-db-from-dump.sh $(ENV_FILE) $(TEST_DB_NAME) $(FULL_DUMP_PATH)

db-refresh-template: chmod-scripts
	./scripts/db/refresh-template-from-db.sh $(ENV_FILE) $(TEST_DB_NAME) $(TEST_TEMPLATE_DB_NAME)

db-create-run: chmod-scripts
	./scripts/db/create-run-db.sh $(ENV_FILE)

backend-install:
	cd backend && python3.13 -m venv .venv-backend && source .venv-backend/bin/activate && pip install -r requirements.txt -r requirements-test.txt

frontend-install:
	cd frontend && npm ci

admin-install:
	cd admin-frontend && npm ci

e2e-install:
	cd e2e && npm ci

local-backend-dev:
	cd backend && source .venv-backend/bin/activate && set -a && source ../.env.localdev && set +a && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

local-frontend-dev:
	cd frontend && NEXT_PUBLIC_API_URL=http://localhost:8000/api npm run dev

local-admin-dev:
	cd admin-frontend && NEXT_PUBLIC_API_URL=http://localhost:8000/api npm run dev

test-backend:
	cd backend && source .venv-backend/bin/activate && set -a && source ../.env.localdev && set +a && pytest -q

test-frontend:
	cd frontend && npm test -- --runInBand

test-admin:
	cd admin-frontend && npm test -- --runInBand

smoke-local:
	cd e2e && npx playwright test -c playwright.local.config.ts --grep @smoke

nuc-rsync-data:
	rsync -a --delete $(HOME)/words-shared/ $(NUC_HOST):$(NUC_SHARED_DATA_DIR)/

deploy-nuc:
	ssh $(NUC_HOST) "cd $(NUC_REPO_DIR) && git fetch origin && git checkout main && git reset --hard origin/main && chmod +x scripts/db/*.sh scripts/deploy/*.sh && ./scripts/deploy/nuc-deploy.sh $(NUC_ENV_FILE)"
