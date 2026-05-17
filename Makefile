.PHONY: help install install-dev dev-api dev-ui build-ui lint format test test-cov clean bundle

PY ?= python3.12
VENV ?= .venv
VENV_BIN := $(VENV)/bin
GUNICORN := $(VENV_BIN)/gunicorn

help:
	@echo "openclaw-panel — Makefile targets"
	@echo "  install        Install Python production deps in .venv"
	@echo "  install-dev    Install Python dev deps + UI deps"
	@echo "  dev-api        Run Flask dev server (gunicorn gevent on :9998)"
	@echo "  dev-ui         Run Vite dev server (:5173, proxies /api → :9998)"
	@echo "  build-ui       Build SPA → static/dist/"
	@echo "  lint           ruff + black --check + mypy"
	@echo "  format         ruff --fix + black"
	@echo "  test           pytest"
	@echo "  test-cov       pytest with coverage"
	@echo "  bundle         Build offline installer zip (dist/openclaw-panel-offline-*.zip)"
	@echo "  clean          Remove build artifacts + caches"

$(VENV):
	$(PY) -m venv $(VENV)
	$(VENV_BIN)/pip install --upgrade pip

install: $(VENV)
	$(VENV_BIN)/pip install -r requirements.txt

install-dev: $(VENV)
	$(VENV_BIN)/pip install -r requirements-dev.txt
	cd ui && npm install

dev-api: $(VENV)
	$(GUNICORN) -k gevent -b 127.0.0.1:9998 --reload wsgi:app

dev-ui:
	cd ui && npm run dev

build-ui:
	cd ui && npm run build

lint:
	$(VENV_BIN)/ruff check app tests
	$(VENV_BIN)/black --check app tests
	$(VENV_BIN)/mypy app

format:
	$(VENV_BIN)/ruff check --fix app tests
	$(VENV_BIN)/black app tests

test:
	$(VENV_BIN)/pytest

test-cov:
	$(VENV_BIN)/pytest --cov=app --cov-report=term-missing --cov-report=html

bundle:
	bash scripts/build-offline-bundle.sh

clean:
	rm -rf $(VENV) ui/node_modules ui/dist static/dist
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
