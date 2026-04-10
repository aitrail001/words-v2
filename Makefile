SHELL := /bin/bash

PROJECT_NAME ?= words-stack
ENV_FILE ?= .env.stack.mac
CI_PROJECT_NAME ?= words-ci-stack
CI_ENV_FILE ?= .env.stack.ci

DEV_DB_NAME ?= vocabapp_dev_full
TEST_DB_NAME ?= vocabapp_test_full
TEST_TEMPLATE_DB_NAME ?= vocabapp_test_template_full
SMOKE_TEMPLATE_DB_NAME ?= vocabapp_test_template_smoke
TEST_FULL_DUMP_PATH ?= $(HOME)/words-shared/postgres/dumps/vocabapp_test_full.dump
DEV_FULL_DUMP_PATH ?= $(HOME)/words-shared/postgres/dumps/vocabapp_dev_full.dump

NUC_HOST ?= youruser@your-nuc-host
NUC_REPO_DIR ?= /srv/words/words-v2
NUC_ENV_FILE ?= .env.stack.nuc
NUC_SHARED_DATA_DIR ?= /srv/words-shared

INFRA_COMPOSE := docker compose -p $(PROJECT_NAME) --env-file $(ENV_FILE) -f compose.infra.yml
TOOLS_COMPOSE := docker compose -p $(PROJECT_NAME) --env-file $(ENV_FILE) -f compose.infra.yml -f compose.tools.yml
STACK_COMPOSE := docker compose -p $(PROJECT_NAME) --env-file $(ENV_FILE) -f compose.infra.yml -f compose.teststack.yml
E2E_COMPOSE := docker compose -p $(PROJECT_NAME) --env-file $(ENV_FILE) -f compose.infra.yml -f compose.teststack.yml -f compose.e2e.yml
STACK_WORKER_SCALE := --scale worker=2
CI_INFRA_COMPOSE := docker compose -p $(CI_PROJECT_NAME) --env-file $(CI_ENV_FILE) -f compose.infra.yml
CI_STACK_COMPOSE := docker compose -p $(CI_PROJECT_NAME) --env-file $(CI_ENV_FILE) -f compose.infra.yml -f compose.teststack.yml
CI_E2E_COMPOSE := docker compose -p $(CI_PROJECT_NAME) --env-file $(CI_ENV_FILE) -f compose.infra.yml -f compose.teststack.yml -f compose.e2e.yml
CI_STACK_WORKER_SCALE := --scale worker=1

PYTHON ?= python3.13
CACHE_ROOT ?= $(HOME)/.cache/words
NPM_CACHE ?= $(CACHE_ROOT)/npm
PLAYWRIGHT_BROWSERS_PATH ?= $(CACHE_ROOT)/ms-playwright

BACKEND_REQ_HASH := $(shell cat backend/requirements.txt backend/requirements-test.txt 2>/dev/null | shasum -a 256 | cut -c1-12)
BACKEND_VENV := $(CACHE_ROOT)/venvs/backend-$(BACKEND_REQ_HASH)
LEXICON_REQ_HASH := $(shell cat tools/lexicon/requirements.txt tools/lexicon/requirements-dev.txt 2>/dev/null | shasum -a 256 | cut -c1-12)
LEXICON_VENV := $(CACHE_ROOT)/venvs/lexicon-$(LEXICON_REQ_HASH)

FRONTEND_LOCK_HASH := $(shell shasum -a 256 frontend/package-lock.json | cut -c1-12)
ADMIN_LOCK_HASH := $(shell shasum -a 256 admin-frontend/package-lock.json | cut -c1-12)
E2E_LOCK_HASH := $(shell shasum -a 256 e2e/package-lock.json | cut -c1-12)
LEXICON_LOCK_HASH := $(shell shasum -a 256 tools/lexicon/package-lock.json | cut -c1-12)
LEXICON_NODE_LOCK_HASH := $(shell shasum -a 256 tools/lexicon/node/package-lock.json | cut -c1-12)

FRONTEND_STAMP := frontend/node_modules/.lock-$(FRONTEND_LOCK_HASH)
ADMIN_STAMP := admin-frontend/node_modules/.lock-$(ADMIN_LOCK_HASH)
E2E_STAMP := e2e/node_modules/.lock-$(E2E_LOCK_HASH)
LEXICON_STAMP := tools/lexicon/node_modules/.lock-$(LEXICON_LOCK_HASH)
LEXICON_NODE_STAMP := tools/lexicon/node/node_modules/.lock-$(LEXICON_NODE_LOCK_HASH)

.PHONY: help config chmod-scripts \
        volumes infra-up infra-down tools-up tools-down tools-logs \
        stack-up stack-build stack-down stack-logs stack-ps stack-restart stack-smoke stack-full \
        ci-config ci-stack-up ci-stack-build ci-stack-down ci-stack-logs ci-stack-ps ci-stack-restart ci-stack-smoke ci-stack-full \
        db-bootstrap db-backup-dev db-backup-test db-restore-dev db-restore-test db-refresh-template db-create-run \
        backend-install lexicon-install frontend-install admin-install e2e-install \
        worktree-bootstrap clean-worktree-links \
        local-backend-dev local-worker-dev local-frontend-dev local-admin-dev \
        lint-backend lint-frontend lint-admin \
        test-backend test-frontend test-admin smoke-local \
        nuc-rsync-data deploy-nuc

help:
	@printf "%s\n" \
	  "make volumes               # create external docker volumes once" \
	  "make infra-up              # start postgres + redis" \
	  "make infra-down            # stop postgres + redis" \
	  "make tools-up              # start pgAdmin + Redis Commander" \
	  "make tools-down            # stop pgAdmin + Redis Commander" \
	  "make tools-logs            # tail logs for pgAdmin + Redis Commander" \
	  "make db-bootstrap          # create long-lived databases" \
	  "make backend-install       # create/reuse shared backend venv and install deps" \
	  "make lexicon-install       # create/reuse shared lexicon venv and install deps" \
	  "make frontend-install      # install learner frontend deps in this worktree" \
	  "make admin-install         # install admin frontend deps in this worktree" \
	  "make e2e-install           # install Playwright deps in this worktree" \
	  "make worktree-bootstrap    # bootstrap worktree with shared venv and local node_modules" \
	  "make clean-worktree-links  # remove the repo-root backend venv symlink" \
	  "make local-backend-dev     # run backend locally" \
	  "make local-worker-dev      # run celery worker locally" \
	  "make local-frontend-dev    # run learner frontend locally" \
	  "make local-admin-dev       # run admin frontend locally" \
	  "make lint-backend          # run backend lint" \
	  "make lint-frontend         # run learner frontend lint" \
	  "make lint-admin            # run admin frontend lint" \
	  "make test-backend          # run backend pytest" \
	  "make test-frontend         # run learner frontend jest" \
	  "make test-admin            # run admin frontend jest" \
	  "make smoke-local           # run local Playwright smoke" \
	  "make stack-up              # start persistent test stack without rebuilding" \
	  "make stack-build           # rebuild/start persistent test stack" \
	  "make stack-down            # stop persistent test stack" \
	  "make stack-logs            # tail stack logs" \
	  "make stack-ps              # show stack containers" \
	  "make stack-restart         # restart stack containers" \
	  "make stack-smoke           # run Playwright smoke against running test stack" \
	  "make stack-full            # run full Playwright suite against running test stack" \
	  "make ci-config             # validate CI-style compose config using CI_ENV_FILE" \
	  "make ci-stack-up           # start CI-style stack without rebuilding" \
	  "make ci-stack-build        # rebuild/start CI-style stack" \
	  "make ci-stack-down         # stop CI-style stack" \
	  "make ci-stack-logs         # tail CI-style stack logs" \
	  "make ci-stack-ps           # show CI-style stack containers" \
	  "make ci-stack-restart      # restart CI-style stack containers" \
	  "make ci-stack-smoke        # run Playwright smoke against CI-style stack" \
	  "make ci-stack-full         # run full Playwright suite against CI-style stack" \
	  "make db-backup-dev         # dump dev DB to DEV_FULL_DUMP_PATH" \
	  "make db-backup-test        # dump test DB to TEST_FULL_DUMP_PATH" \
	  "make db-restore-dev        # restore dev DB from TEST_FULL_DUMP_PATH" \
	  "make db-restore-test       # restore test DB from TEST_FULL_DUMP_PATH" \
	  "make db-refresh-template   # refresh template DB from test DB" \
	  "make db-create-run         # create disposable DB cloned from template" \
	  "make nuc-rsync-data        # sync shared data root to NUC" \
	  "make deploy-nuc            # pull latest code on NUC and deploy"

config:
	$(STACK_COMPOSE) config >/dev/null

ci-config:
	$(CI_STACK_COMPOSE) config >/dev/null

chmod-scripts:
	chmod +x scripts/db/*.sh scripts/deploy/*.sh

volumes:
	docker volume create words_pg_data >/dev/null
	docker volume create words_redis_data >/dev/null
	docker volume create words_uploads_data >/dev/null
	docker volume create words_pgadmin_data >/dev/null
	docker volume create words_redis_commander_data >/dev/null

infra-up: volumes
	$(INFRA_COMPOSE) up -d

infra-down:
	$(INFRA_COMPOSE) down --remove-orphans

tools-up:
	$(TOOLS_COMPOSE) --profile tools up -d

tools-down:
	$(TOOLS_COMPOSE) stop pgadmin redis-commander

tools-logs:
	$(TOOLS_COMPOSE) logs -f --tail=200

db-bootstrap: infra-up chmod-scripts
	./scripts/db/bootstrap-long-lived.sh $(ENV_FILE)

stack-up: infra-up
	$(STACK_COMPOSE) up -d $(STACK_WORKER_SCALE)

stack-build: infra-up
	$(STACK_COMPOSE) up -d --build $(STACK_WORKER_SCALE)

stack-down:
	$(STACK_COMPOSE) down --remove-orphans

stack-logs:
	$(STACK_COMPOSE) logs -f --tail=200

stack-ps:
	$(STACK_COMPOSE) ps

stack-restart:
	$(STACK_COMPOSE) restart

stack-smoke:
	$(E2E_COMPOSE) --profile tests run --rm playwright npm run test:smoke:ci

stack-full:
	$(E2E_COMPOSE) --profile tests run --rm playwright npm run test:full

ci-stack-up: volumes
	$(CI_STACK_COMPOSE) up -d $(CI_STACK_WORKER_SCALE)

ci-stack-build: volumes
	$(CI_STACK_COMPOSE) up -d --build $(CI_STACK_WORKER_SCALE)

ci-stack-down:
	$(CI_STACK_COMPOSE) down --remove-orphans

ci-stack-logs:
	$(CI_STACK_COMPOSE) logs -f --tail=200

ci-stack-ps:
	$(CI_STACK_COMPOSE) ps

ci-stack-restart:
	$(CI_STACK_COMPOSE) restart

ci-stack-smoke:
	$(CI_E2E_COMPOSE) --profile tests run --rm playwright npm run test:smoke:ci

ci-stack-full:
	$(CI_E2E_COMPOSE) --profile tests run --rm playwright npm run test:full

db-backup-dev: chmod-scripts
	./scripts/db/backup-db.sh $(ENV_FILE) $(DEV_DB_NAME) $(DEV_FULL_DUMP_PATH)

db-backup-test: chmod-scripts
	./scripts/db/backup-db.sh $(ENV_FILE) $(TEST_DB_NAME) $(TEST_FULL_DUMP_PATH)

db-restore-dev: chmod-scripts
	./scripts/db/restore-db-from-dump.sh $(ENV_FILE) $(DEV_DB_NAME) $(TEST_FULL_DUMP_PATH)

db-restore-test: chmod-scripts
	./scripts/db/restore-db-from-dump.sh $(ENV_FILE) $(TEST_DB_NAME) $(TEST_FULL_DUMP_PATH)

db-refresh-template: chmod-scripts
	./scripts/db/refresh-template-from-db.sh $(ENV_FILE) $(TEST_DB_NAME) $(TEST_TEMPLATE_DB_NAME)

db-create-run: chmod-scripts
	./scripts/db/create-run-db.sh $(ENV_FILE)

backend-install:
	@mkdir -p "$(CACHE_ROOT)/venvs"
	@if [ ! -x "$(BACKEND_VENV)/bin/python" ]; then \
		echo "Creating shared backend venv: $(BACKEND_VENV)"; \
		$(PYTHON) -m venv "$(BACKEND_VENV)"; \
		. "$(BACKEND_VENV)/bin/activate" && \
		python -m pip install --upgrade pip && \
		pip install ruff && \
		pip install -r backend/requirements.txt -r backend/requirements-test.txt; \
	else \
		echo "Reusing shared backend venv: $(BACKEND_VENV)"; \
	fi
	@ln -sfn "$(BACKEND_VENV)" .venv-backend
	@echo "Linked current worktree .venv-backend -> $(BACKEND_VENV)"

lexicon-install:
	@mkdir -p "$(CACHE_ROOT)/venvs" "$(NPM_CACHE)"
	@if [ ! -x "$(LEXICON_VENV)/bin/python" ]; then \
		echo "Creating shared lexicon venv: $(LEXICON_VENV)"; \
		$(PYTHON) -m venv "$(LEXICON_VENV)"; \
		. "$(LEXICON_VENV)/bin/activate" && \
		python -m pip install --upgrade pip && \
		pip install -r tools/lexicon/requirements-dev.txt; \
	else \
		echo "Reusing shared lexicon venv: $(LEXICON_VENV)"; \
	fi
	@if [ ! -e .venv-lexicon ]; then \
		ln -sfn "$(LEXICON_VENV)" .venv-lexicon; \
		echo "Linked current worktree .venv-lexicon -> $(LEXICON_VENV)"; \
	elif [ -L .venv-lexicon ]; then \
		ln -sfn "$(LEXICON_VENV)" .venv-lexicon; \
		echo "Updated current worktree .venv-lexicon -> $(LEXICON_VENV)"; \
	else \
		echo "Keeping existing local .venv-lexicon directory"; \
	fi
	@if [ ! -f "$(LEXICON_STAMP)" ]; then \
		echo "Installing lexicon tool npm dependencies"; \
		rm -rf tools/lexicon/node_modules; \
		cd tools/lexicon && npm ci --cache "$(NPM_CACHE)"; \
		mkdir -p "$$(dirname "$(LEXICON_STAMP)")"; \
		touch "$(LEXICON_STAMP)"; \
	else \
		echo "Lexicon tool node_modules already matches lockfile"; \
	fi
	@if [ ! -f "$(LEXICON_NODE_STAMP)" ]; then \
		echo "Installing lexicon node transport npm dependencies"; \
		rm -rf tools/lexicon/node/node_modules; \
		cd tools/lexicon/node && npm ci --cache "$(NPM_CACHE)"; \
		mkdir -p "$$(dirname "$(LEXICON_NODE_STAMP)")"; \
		touch "$(LEXICON_NODE_STAMP)"; \
	else \
		echo "Lexicon node transport node_modules already matches lockfile"; \
	fi

frontend-install:
	@mkdir -p "$(NPM_CACHE)"
	@if [ ! -f "$(FRONTEND_STAMP)" ]; then \
		echo "Installing frontend dependencies"; \
		rm -rf frontend/node_modules; \
		cd frontend && npm ci --cache "$(NPM_CACHE)"; \
		mkdir -p "$$(dirname "$(FRONTEND_STAMP)")"; \
		touch "$(FRONTEND_STAMP)"; \
	else \
		echo "Frontend node_modules already matches lockfile"; \
	fi

admin-install:
	@mkdir -p "$(NPM_CACHE)"
	@if [ ! -f "$(ADMIN_STAMP)" ]; then \
		echo "Installing admin frontend dependencies"; \
		rm -rf admin-frontend/node_modules; \
		cd admin-frontend && npm ci --cache "$(NPM_CACHE)"; \
		mkdir -p "$$(dirname "$(ADMIN_STAMP)")"; \
		touch "$(ADMIN_STAMP)"; \
	else \
		echo "Admin frontend node_modules already matches lockfile"; \
	fi

e2e-install:
	@mkdir -p "$(NPM_CACHE)" "$(PLAYWRIGHT_BROWSERS_PATH)"
	@if [ ! -f "$(E2E_STAMP)" ]; then \
		echo "Installing e2e dependencies"; \
		rm -rf e2e/node_modules; \
		cd e2e && npm ci --cache "$(NPM_CACHE)"; \
		mkdir -p "$$(dirname "$(E2E_STAMP)")"; \
		touch "$(E2E_STAMP)"; \
	else \
		echo "E2E node_modules already matches lockfile"; \
	fi
	@echo "Ensuring Playwright browsers exist in shared cache"
	@cd e2e && PLAYWRIGHT_BROWSERS_PATH="$(PLAYWRIGHT_BROWSERS_PATH)" npx playwright install

worktree-bootstrap: backend-install lexicon-install frontend-install admin-install e2e-install
	@echo "Worktree bootstrap complete"

clean-worktree-links:
	rm -f .venv-backend

local-backend-dev:
	bash -lc 'source .venv-backend/bin/activate && set -a && source .env.localdev && set +a && cd backend && uvicorn app.main:app --host 0.0.0.0 --port $$BACKEND_PORT --reload'

local-worker-dev:
	bash -lc 'source .venv-backend/bin/activate && set -a && source .env.localdev && set +a && cd backend && celery -A app.celery_app:celery_app worker --loglevel=info --concurrency=2 --queues=$${CELERY_QUEUES:-default,imports}'

local-frontend-dev:
	bash -lc 'set -a && source .env.localdev && set +a && cd frontend && NEXT_PUBLIC_API_URL=http://localhost:$$BACKEND_PORT/api npm run dev -- --hostname 0.0.0.0 -p $$FRONTEND_PORT'

local-admin-dev:
	bash -lc 'set -a && source .env.localdev && set +a && cd admin-frontend && NEXT_PUBLIC_API_URL=http://localhost:$$BACKEND_PORT/api npm run dev'

lint-backend:
	bash -lc 'source .venv-backend/bin/activate && cd backend && ruff check .'

lint-frontend:
	cd frontend && npm run lint

lint-admin:
	cd admin-frontend && npm run lint

test-backend:
	bash -lc 'source .venv-backend/bin/activate && set -a && source .env.localdev && set +a && cd backend && pytest -q'

test-frontend:
	cd frontend && npm test -- --runInBand

test-admin:
	cd admin-frontend && npm test -- --runInBand

smoke-local:
	bash -lc 'set -euo pipefail; \
		set -a; source .env.localdev; set +a; \
		export PLAYWRIGHT_BROWSERS_PATH="$(PLAYWRIGHT_BROWSERS_PATH)"; \
		export E2E_BASE_URL=http://localhost:$$FRONTEND_PORT; \
		export E2E_API_URL=http://localhost:$$BACKEND_PORT/api; \
		export E2E_ADMIN_URL=http://localhost:$$ADMIN_FRONTEND_PORT; \
		export E2E_DB_NAME=$${E2E_DB_NAME:-$$DEV_DB_NAME}; \
		export E2E_WORDS_DATA_ROOT=$${E2E_WORDS_DATA_ROOT:-$$WORDS_DATA_DIR}; \
		WORKER_LOG=/tmp/words-local-worker.log; \
		source .venv-backend/bin/activate; \
		cd backend; \
		celery -A app.celery_app:celery_app worker --loglevel=info --concurrency=2 --queues=$${CELERY_QUEUES:-default,imports} >"$$WORKER_LOG" 2>&1 & \
		WORKER_PID=$$!; \
		cd ..; \
		trap "kill $$WORKER_PID >/dev/null 2>&1 || true" EXIT INT TERM; \
		for _ in $$(seq 1 30); do \
			if grep -q "ready" "$$WORKER_LOG"; then \
				break; \
			fi; \
			sleep 1; \
		done; \
		./e2e/node_modules/.bin/playwright test -c e2e/playwright.local.config.ts --grep @smoke'

nuc-rsync-data:
	rsync -a --delete $(HOME)/words-shared/ $(NUC_HOST):$(NUC_SHARED_DATA_DIR)/

deploy-nuc:
	ssh $(NUC_HOST) "cd $(NUC_REPO_DIR) && git fetch origin && git checkout main && git reset --hard origin/main && chmod +x scripts/db/*.sh scripts/deploy/*.sh && ./scripts/deploy/nuc-deploy.sh $(NUC_ENV_FILE)"
