# Querious task runner — the Python equivalent of `npm run`.
# Run `make` (or `make help`) to list targets.

VENV   := .venv
PYTHON := $(VENV)/bin/python
HOST   ?= 0.0.0.0
PORT   ?= 8000

.DEFAULT_GOAL := help
.PHONY: help install setup run dev test stop clean

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-9s\033[0m %s\n", $$1, $$2}'

install: ## Create the virtualenv and install dependencies
	uv venv $(VENV) 2>/dev/null || python3 -m venv $(VENV)
	. $(VENV)/bin/activate && (uv pip install -r requirements-dev.txt 2>/dev/null || pip install -r requirements-dev.txt)

setup: ## Build the databases (seed acme.db + embed docs via Voyage)
	$(PYTHON) setup.py

run: ## Start the server (foreground) on 0.0.0.0:8000 (override HOST/PORT)
	HOST=$(HOST) PORT=$(PORT) ./run.sh

dev: ## Start the server with auto-reload
	HOST=$(HOST) PORT=$(PORT) ./run.sh --reload

test: ## Run the test suite
	$(PYTHON) -m pytest

stop: ## Stop a running server
	@pkill -f 'app[.]main:app' && echo "stopped" || echo "no server running"

clean: ## Remove generated databases and caches
	rm -f data/acme.db data/embeddings.db
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
