.PHONY: install lock-check lint typecheck test docs-sync audit synth synth-all \
	diagrams security bootstrap check-stack diff-stack deploy-stack deploy \
	destroy verify-deploy smoke wiki-init wiki-index wiki-search wiki-ingest \
	wiki-lint

ENV ?= dev
CDK_CLI := uv run --locked npx aws-cdk@2.1130.0
CDK_DIA := npx --yes cdk-dia@0.12.3
DIAGRAM_DIR ?= $(CURDIR)/wiki/assets/architecture

# The tests need the `pipeline` extra, not only the SageMaker images.
# src/pipeline/pipeline.py imports the SageMaker SDK at module level, and a
# stub reduces the pipeline tests to assertions against mocks.
install:
	uv sync --locked --extra dev --extra pipeline

lock-check:
	uv lock --check

lint:
	uv run --locked ruff check .
	uv run --locked ruff format --check .

# Both extras, like `test`. Without sagemaker, mypy falls back to the
# ignore_missing_imports override, src/pipeline/ types as Any, and the run
# passes without checking that package.
typecheck:
	uv run --locked --extra dev --extra pipeline mypy

# Every run measures coverage and enforces it against `fail_under` in
# pyproject. Without a floor, coverage falls without any failure.
test:
	uv run --locked --extra dev --extra pipeline pytest tests/unit -q \
		--cov --cov-report=term-missing

# AGENTS.md is the single source, and CLAUDE.md is a symlink to it. The two
# cannot drift while the symlink survives. A checkout without symlink support,
# or an agent that writes CLAUDE.md directly, replaces it with a regular file.
# Assert against the git index, not the working tree. The index is what CI
# checks out and what a bad commit carries.
docs-sync:
	@mode=$$(git ls-files -s CLAUDE.md | cut -d' ' -f1); \
	if [ "$$mode" != "120000" ]; then \
		echo "CLAUDE.md must be a symlink to AGENTS.md; git records mode '$$mode'" >&2; \
		exit 1; \
	fi; \
	target=$$(git cat-file -p :CLAUDE.md); \
	if [ "$$target" != "AGENTS.md" ]; then \
		echo "CLAUDE.md points at '$$target', expected AGENTS.md" >&2; \
		exit 1; \
	fi; \
	test -s AGENTS.md || { echo "AGENTS.md is missing or empty" >&2; exit 1; }; \
	echo "docs-sync: CLAUDE.md -> AGENTS.md"

audit:
	uv run --locked pip-audit --skip-editable

synth:
	cd infra && $(CDK_CLI) synth -c env=$(ENV) --no-lookups

# The authoritative cdk-nag gate. An acknowledgement whose construct path or
# finding id embeds the environment fails only for that environment, so a
# dev-only synth leaves prod unbuildable.
synth-all:
	$(MAKE) synth ENV=dev
	$(MAKE) synth ENV=prod

# These diagrams show the synthesized design. They do not show live AWS state.
# cdk-dia writes local icon paths into DOT sidecars. Keep only the PNG files.
diagrams: synth
	@command -v dot >/dev/null 2>&1 || { \
		echo "Graphviz is required. Install it with: brew install graphviz" >&2; \
		exit 2; \
	}
	@mkdir -p "$(abspath $(DIAGRAM_DIR))"
	@set -eu; \
	prefix=$$(uv run --locked --extra dev python -c \
		'from infra.app import stack_prefix; print(stack_prefix("$(ENV)"))'); \
	cd infra; \
	$(CDK_DIA) --tree cdk.out/tree.json \
		--target "$(abspath $(DIAGRAM_DIR))/cdk-full-$(ENV).png"; \
	$(CDK_DIA) --tree cdk.out/tree.json \
		--target "$(abspath $(DIAGRAM_DIR))/cdk-platform-$(ENV).png" \
		--include "$$prefix-Data" "$$prefix-Ingestion" "$$prefix-Registry" \
			"$$prefix-Training" "$$prefix-Serving" "$$prefix-Monitoring"; \
	$(CDK_DIA) --tree cdk.out/tree.json \
		--target "$(abspath $(DIAGRAM_DIR))/cdk-security-cicd-$(ENV).png" \
		--include "$$prefix-Security" "$$prefix-SecurityMonitoring" \
			"$$prefix-Cicd"
	@rm -f "$(abspath $(DIAGRAM_DIR))/cdk-full-$(ENV).dot" \
		"$(abspath $(DIAGRAM_DIR))/cdk-platform-$(ENV).dot" \
		"$(abspath $(DIAGRAM_DIR))/cdk-security-cicd-$(ENV).dot"

security: lock-check audit synth-all

# Run this once per account and region, before the first deploy. It is a
# target, so the bootstrap uses the same pinned CLI version as every other CDK
# invocation.
bootstrap:
	cd infra && $(CDK_CLI) bootstrap -c env=$(ENV)

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

# What a deployment changed. Stack status does not answer this. CloudFormation
# reports UPDATE_COMPLETE even when it touched no resource.
#
# This needs a profile with cloudformation:ListStacks. Use
# mlops-security-auditor or aws-admin. mlops-deployer can deploy but cannot
# enumerate stacks:
#     AWS_PROFILE=mlops-security-auditor make verify-deploy SINCE=2026-08-01
verify-deploy:
	uv run --locked --extra dev python scripts/verify_deployment.py \
		$(if $(SINCE),--since "$(SINCE)") $(if $(PREFIX),--prefix "$(PREFIX)")

# Post-deploy check against the live API. tests/integration skips itself when
# API_URL or API_KEY is unset, so this target resolves and asserts every value.
# A missing output must fail the run, not reduce it to zero tests.
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
	echo "smoke testing $$url"; \
	API_URL="$$url" \
		uv run --locked --extra dev pytest tests/integration -q

wiki-init:
	uv run --locked python scripts/wiki.py init

wiki-index:
	uv run --locked python scripts/wiki.py index

wiki-search:
	uv run --locked python scripts/wiki.py search "$(Q)"

wiki-ingest:
	uv run --locked python scripts/wiki.py add-source "$(SOURCE)" $(if $(TITLE),--title "$(TITLE)")

wiki-lint:
	uv run --locked python scripts/wiki.py lint
