# Developer shortcuts. Run `make help` for the list.
SHELL := /bin/bash
COMPOSE := docker compose
DEMO := $(COMPOSE) -f docker-compose.yml -f docker-compose.demo.yml
LAB := $(COMPOSE) -f docker-compose.yml -f lab/docker-compose.lab.yml

.DEFAULT_GOAL := help

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- local development
install: ## Install backend (uv) and frontend (npm) dependencies
	cd backend && uv sync
	cd frontend && npm ci

dev-db: ## Initialise a local SQLite database with demo data and a week of history
	cd backend && uv run netmon init --demo --history-hours 168

dev-backend: ## Run the API with auto-reload in simulation mode (http://localhost:8000/docs)
	cd backend && NETMON_MONITOR_MODE=simulation uv run netmon serve --reload

dev-frontend: ## Run the Vite dev server (http://localhost:5173)
	cd frontend && npm run dev

migration: ## Create a new Alembic migration: make migration m="describe change"
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

# ---------------------------------------------------------------- quality
lint: ## Lint and type-check everything
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy netmon
	cd frontend && npm run lint && npm run format:check && npm run typecheck

format: ## Auto-format backend and frontend code
	cd backend && uv run ruff check --fix . && uv run ruff format .
	cd frontend && npm run format

test: ## Run backend and frontend test suites
	cd backend && uv run pytest
	cd frontend && npm test

coverage: ## Backend tests with an HTML coverage report (backend/htmlcov)
	cd backend && uv run pytest --cov --cov-report=html

# ---------------------------------------------------------------- docker
up: ## Start the production-style stack (needs .env)
	$(COMPOSE) up -d --build

demo: ## Start the stack with a simulated network and synthetic history
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example - edit the secrets!")
	$(DEMO) up -d --build

lab: ## Start the stack plus the virtual SNMP lab
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example - edit the secrets!")
	$(LAB) up -d --build

down: ## Stop all containers (data volumes are kept)
	$(LAB) down

logs: ## Follow backend logs
	$(COMPOSE) logs -f backend

.PHONY: help install dev-db dev-backend dev-frontend migration lint format test coverage up demo lab down logs
