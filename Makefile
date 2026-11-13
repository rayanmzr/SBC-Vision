.PHONY: install check lint format test schema serve extension-check extension-build

install:
	python -m pip install -c requirements.lock -e '.[dev]'

check: lint test
	python scripts/export_contracts.py --check

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

test:
	pytest

schema:
	python scripts/export_contracts.py

serve:
	uvicorn sbc_vision.api.main:app --reload

extension-check:
	cd frontend && pnpm run check

extension-build:
	cd frontend && pnpm run build
