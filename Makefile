.PHONY: install check lint format test schema serve

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
