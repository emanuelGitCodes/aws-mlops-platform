.PHONY: install lock-check lint test audit synth security deploy destroy wiki-init wiki-index wiki-search wiki-ingest wiki-lint

ENV ?= dev

install:
	uv sync --locked --extra dev

lock-check:
	uv lock --check

lint:
	uv run --locked ruff check .
	uv run --locked ruff format --check .

test:
	uv run --locked pytest tests/unit -q

audit:
	uv run --locked pip-audit --skip-editable

synth:
	cd infra && uv run --locked npx aws-cdk@2.1130.0 synth -c env=$(ENV) --no-lookups

security: lock-check audit synth

deploy:
	cd infra && uv run --locked npx aws-cdk@2.1130.0 deploy --all -c env=$(ENV) --require-approval never

destroy:
	cd infra && uv run --locked npx aws-cdk@2.1130.0 destroy --all -c env=$(ENV)

wiki-init:
	python3 scripts/wiki.py init

wiki-index:
	python3 scripts/wiki.py index

wiki-search:
	python3 scripts/wiki.py search "$(Q)"

wiki-ingest:
	python3 scripts/wiki.py add-source "$(SOURCE)" $(if $(TITLE),--title "$(TITLE)")

wiki-lint:
	python3 scripts/wiki.py lint
