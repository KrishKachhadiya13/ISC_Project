.PHONY: help setup test lint format run-backend run-frontend dev docker

PYTHON ?= python
NPM ?= npm

help:
	@echo "StegaGuard Management Commands"
	@echo "  make setup        Install all backend and frontend dependencies"
	@echo "  make test         Run backend test suite with pytest"
	@echo "  make lint         Run linter and static type checkers (ruff, mypy)"
	@echo "  make format       Format backend code with ruff"
	@echo "  make run-backend  Run FastAPI backend development server"
	@echo "  make run-frontend Run Vite React frontend development server"
	@echo "  make dev          Run both backend and frontend"
	@echo "  make docker       Build and launch docker-compose containers"

setup:
	$(PYTHON) -m pip install -r backend/requirements.txt
	$(PYTHON) -m pip install -r backend/requirements-dev.txt
	cd frontend && $(NPM) install

test:
	set PYTHONPATH=backend&& $(PYTHON) -m pytest backend/tests -v

lint:
	$(PYTHON) -m ruff check backend
	$(PYTHON) -m ruff format backend --check
	$(PYTHON) -m mypy backend/app

format:
	$(PYTHON) -m ruff check backend --fix
	$(PYTHON) -m ruff format backend

run-backend:
	set PYTHONPATH=backend&& $(PYTHON) -m uvicorn app.main:app --reload --port 8000

run-frontend:
	cd frontend && $(NPM) run dev

docker:
	docker compose up --build
