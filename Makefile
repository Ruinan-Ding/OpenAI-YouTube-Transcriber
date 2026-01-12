.PHONY: install deps lint format test run clean help

install:
	python -m pip install --upgrade pip
	pip install -e .

deps:
	pip install --upgrade -r OpenAIYouTubeTranscriber/requirements.txt

dev:
	@echo "Installing development dependencies..."
	pip install -r requirements-dev.txt

lint:
	@echo "Running flake8..."
	pip install --no-input flake8
	flake8

format:
	@echo "Running black to format code..."
	pip install --no-input black
	black .

run:
	python OpenAIYouTubeTranscriber.py

clean:
	rm -rf build dist *.egg-info __pycache__ .pytest_cache

help:
	@echo "Make targets:"
	@echo "  install  - Install package in editable mode"
	@echo "  deps     - Install runtime dependencies from requirements.txt"
	@echo "  dev      - Install development dependencies from requirements-dev.txt"
	@echo "  lint     - Run flake8 linting (installs flake8 if missing)"
	@echo "  format   - Run black formatter (installs black if missing)"
	@echo "  run      - Run the main script"
	@echo "  clean    - Remove build artifacts"
	@echo "  help     - Show this message"

precommit-install:
	@echo "Installing pre-commit hooks"
	pip install --no-input pre-commit
	pre-commit install