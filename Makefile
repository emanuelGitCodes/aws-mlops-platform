.PHONY: install lint test synth deploy destroy wiki-init wiki-index wiki-search wiki-ingest wiki-lint

ENV ?= dev

install:
	pip install -e ".[dev]"

lint:
	ruff check .
	ruff format --check .

test:
	pytest tests/unit -q

synth:
	cd infra && cdk synth -c env=$(ENV)

deploy:
	cd infra && cdk deploy --all -c env=$(ENV) --require-approval never

destroy:
	cd infra && cdk destroy --all -c env=$(ENV)

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
