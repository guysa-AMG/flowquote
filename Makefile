# Makefile

.PHONY: test eval demo lint typecheck install dev-up dev-down

# Run unit tests + no-network + schema-guard + matcher eval on typed phrases
test:
	uv run pytest tests/ -v -x --tb=short

# Full audio eval (local only, requires eval audio + truth.jsonl)
eval:
	uv run python eval/run_eval.py

# Demo helpers (record, playback, etc.)
demo:
	@echo "Demo targets not yet implemented"

# Lint with ruff
lint:
	uv run ruff check app/ tests/ eval/

# Typecheck with pyright/mypy (TBD)
typecheck:
	@echo "Typecheck not yet configured"

# Install dev dependencies
install:
	uv sync --dev

# Start dev stack (app + ollama)
dev-up:
	docker compose up -d

# Stop dev stack
dev-down:
	docker compose down

# Run everything in container (matches CI)
ci: lint typecheck test
	@echo "CI checks passed"