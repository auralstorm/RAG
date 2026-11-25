.PHONY: install dev-backend dev-chat dev-admin lint format-check typecheck test build check contracts contracts-check infra-up infra-down infra-status infra-init infra-reset infra-test db-upgrade db-current poc-search poc-storage

PROFILE ?= development

install:
	uv sync --locked
	pnpm install --frozen-lockfile

dev-backend:
	uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-proxy-headers

dev-chat:
	pnpm dev:chat

dev-admin:
	pnpm dev:admin

lint:
	uv run --locked ruff check backend scripts
	pnpm lint

format-check:
	uv run --locked ruff format --check backend scripts
	pnpm format:check
	pnpm exec prettier --check infra/compose/*.yaml

typecheck:
	uv run --locked pyright
	pnpm typecheck

test:
	uv run --locked pytest
	pnpm test

build:
	pnpm build

contracts:
	uv run --locked python scripts/contracts.py

contracts-check:
	uv run --locked python scripts/contracts.py --check

check: lint format-check typecheck test build contracts-check
	uv run --locked python scripts/check_repository.py
	git diff --check

infra-up:
	uv run --locked python scripts/infrastructure.py up --profile $(PROFILE)

infra-down:
	uv run --locked python scripts/infrastructure.py down --profile $(PROFILE)

infra-status:
	uv run --locked python scripts/infrastructure.py status --profile $(PROFILE)

infra-init:
	uv run --locked python scripts/infrastructure.py init --profile $(PROFILE)

infra-reset:
	uv run --locked python scripts/infrastructure.py reset --profile $(PROFILE) --confirm-reset

infra-test:
	uv run --locked pytest -m infrastructure -v

db-upgrade:
	ENTERPRISE_RAG_INFRA_PROFILE=$(PROFILE) uv run --locked python -m scripts.migrate_database upgrade

db-current:
	ENTERPRISE_RAG_INFRA_PROFILE=$(PROFILE) uv run --locked python -m scripts.migrate_database current

poc-search:
	uv run --locked python scripts/poc/search.py

poc-storage:
	uv run --locked python scripts/poc/storage.py
