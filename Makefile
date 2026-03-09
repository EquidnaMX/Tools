.PHONY: help install install-dev test test-cloud lint format typecheck quality pre-commit pre-commit-install

help:
	@echo "Available targets:"
	@echo "  install            Install runtime dependencies and package"
	@echo "  install-dev        Install development dependencies and package"
	@echo "  test               Run full test suite"
	@echo "  test-cloud         Run cloud test suite"
	@echo "  lint               Run flake8"
	@echo "  format             Run black formatter"
	@echo "  typecheck          Run mypy (tools package)"
	@echo "  quality            Run lint + test"
	@echo "  pre-commit-install Install git pre-commit hooks"
	@echo "  pre-commit         Run pre-commit on all files"

install:
	python -m pip install --upgrade pip
	python -m pip install -e .

install-dev:
	python -m pip install --upgrade pip
	python -m pip install -r requirements-dev.txt
	python -m pip install -e .

test:
	python -m pytest tests -q

test-cloud:
	python -m pytest tests/cloud -q

lint:
	python -m flake8 tools tests

format:
	python -m black tools tests examples

typecheck:
	python -m mypy tools || true

quality: lint test

pre-commit-install:
	python -m pre_commit install

pre-commit:
	python -m pre_commit run --all-files
