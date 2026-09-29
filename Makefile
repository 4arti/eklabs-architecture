.PHONY: check lint typecheck test boundary migrate

check: lint typecheck test boundary

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy src

test:
	pytest

boundary:
	python scripts/check_platform_product_boundary.py

migrate:
	alembic upgrade head
