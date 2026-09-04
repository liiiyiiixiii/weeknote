PYTHON ?= .venv/bin/python

.PHONY: setup format format-check lint test audit check

setup:
	python3 -m venv backend/.venv
	cd backend && $(PYTHON) -m pip install -r requirements-dev.txt
	npm ci

format:
	cd backend && $(PYTHON) -m ruff format .
	cd backend && $(PYTHON) -m ruff check --fix .
	npm run format

format-check:
	cd backend && $(PYTHON) -m ruff format --check .
	npm run format:check

lint:
	cd backend && $(PYTHON) -m ruff check .

test:
	cd backend && $(PYTHON) -m pytest -q

audit:
	cd backend && $(PYTHON) -m pip check
	cd backend && $(PYTHON) -m pip_audit -r requirements.txt
	gitleaks git --redact --no-banner .

check: format-check lint test audit
