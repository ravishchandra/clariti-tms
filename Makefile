.PHONY: sdks sdk-ts sdk-python spec dev test lint migrate help

## Default target
help:
	@echo "Available targets:"
	@echo "  make sdks        Regenerate both TypeScript and Python SDKs"
	@echo "  make sdk-ts      Generate TypeScript SDK into sdks/typescript/"
	@echo "  make sdk-python  Generate Python SDK into sdks/python/"
	@echo "  make spec        Fetch live OpenAPI spec from running dev server"
	@echo "  make dev         Start FastAPI dev server on port 8000"
	@echo "  make test        Run pytest"
	@echo "  make lint        Run ruff linter"
	@echo "  make migrate     Run Alembic migrations"

sdks: sdk-ts sdk-python

sdk-ts:
	npx @hey-api/openapi-ts -i sdk-gen/openapi.json -o sdks/typescript -c @hey-api/client-fetch

sdk-python:
	uvx openapi-python-client generate --path sdk-gen/openapi.json --output-path sdks/python --overwrite

# Generate the OpenAPI spec in-process (no running server needed) so it can
# never silently rot. `make spec-check` is the CI guard (fails on a stale spec).
spec:
	python scripts/dump_openapi.py

spec-check:
	python scripts/dump_openapi.py --check

dev:
	uvicorn app.main:app --reload --port 8000

test:
	.venv/bin/pytest tests/ -v

lint:
	.venv/bin/ruff check app/ cli/ tests/

migrate:
	alembic upgrade head
