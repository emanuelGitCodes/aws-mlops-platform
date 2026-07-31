.PHONY: install lock-check lint typecheck test audit synth synth-all security \
	check-stack diff-stack deploy-stack deploy destroy verify-deploy smoke \
	wiki-init wiki-index wiki-search wiki-ingest wiki-lint

ENV ?= dev
CDK_CLI := uv run --locked npx aws-cdk@2.1130.0

install:
	uv sync --locked --extra dev

lock-check:
	uv lock --check

lint:
	uv run --locked ruff check .
	uv run --locked ruff format --check .

typecheck:
	uv run --locked --extra dev mypy

test:
	uv run --locked pytest tests/unit -q

audit:
	uv run --locked pip-audit --skip-editable

synth:
	cd infra && $(CDK_CLI) synth -c env=$(ENV) --no-lookups

# The authoritative cdk-nag gate. An acknowledgement whose construct path or
# finding id embeds the environment only fails for the environment it was
# written against, so a dev-only synth let prod stay unbuildable unnoticed.
synth-all:
	$(MAKE) synth ENV=dev
	$(MAKE) synth ENV=prod

security: lock-check audit synth-all

check-stack:
	@test -n "$(STACK)" || \
		(echo "STACK is required, for example STACK=Mlops-Dev-SecurityMonitoring" >&2; exit 2)

diff-stack: check-stack
	cd infra && $(CDK_CLI) diff "$(STACK)" -c env=$(ENV) \
		--no-lookups --no-change-set

deploy-stack: check-stack
	cd infra && $(CDK_CLI) deploy "$(STACK)" -c env=$(ENV) \
		--no-lookups --require-approval never

deploy:
	cd infra && $(CDK_CLI) deploy --all -c env=$(ENV) --require-approval never

destroy:
	cd infra && $(CDK_CLI) destroy --all -c env=$(ENV)

# What a deployment actually changed. Stack status does not answer this:
# UPDATE_COMPLETE is reported even when no resource was touched.
verify-deploy:
	uv run --locked --extra dev python scripts/verify_deployment.py \
		$(if $(SINCE),--since "$(SINCE)") $(if $(PREFIX),--prefix "$(PREFIX)")

# Post-deploy check against the live API. tests/integration skips itself when
# API_URL/API_KEY are unset, so every value is resolved and asserted here: a
# missing output must fail the run, not silently reduce it to zero tests.
smoke:
	@set -eu; \
	prefix=$$(uv run --locked --extra dev python -c \
		'from infra.app import stack_prefix; print(stack_prefix("$(ENV)"))'); \
	stack="$$prefix-Serving"; \
	stack_output() { \
		aws cloudformation describe-stacks --stack-name "$$stack" \
			--query "Stacks[0].Outputs[?OutputKey=='$$1'].OutputValue" \
			--output text; \
	}; \
	require() { \
		test -n "$$2" -a "$$2" != "None" || \
			{ echo "$$stack: no $$1" >&2; exit 1; }; \
	}; \
	url=$$(stack_output ApiUrl); require ApiUrl "$$url"; \
	key_id=$$(stack_output ApiKeyId); require ApiKeyId "$$key_id"; \
	api_key=$$(aws apigateway get-api-key --api-key "$$key_id" \
		--include-value --query value --output text); \
	require "value for API key $$key_id" "$$api_key"; \
	echo "smoke testing $$url"; \
	API_URL="$$url" API_KEY="$$api_key" \
		uv run --locked --extra dev pytest tests/integration -q

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
