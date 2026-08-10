.PHONY: install lock-check lint typecheck test docs-sync audit synth synth-all \
	diagrams security bootstrap check-stack diff-stack deploy-stack deploy \
	destroy verify-deploy smoke wiki-init wiki-index wiki-search wiki-ingest \
	wiki-lint public-check

ENV ?= dev
CDK_CLI := uv run --locked npx aws-cdk@2.1130.0
CDK_DIA := npx --yes cdk-dia@0.12.3
DIAGRAM_DIR ?= $(CURDIR)/wiki/assets/architecture
DIAGRAM_FULL := $(abspath $(DIAGRAM_DIR))/cdk-full-$(ENV)
DIAGRAM_PLATFORM := $(abspath $(DIAGRAM_DIR))/cdk-platform-$(ENV)
DIAGRAM_SECURITY_CICD := $(abspath $(DIAGRAM_DIR))/cdk-security-cicd-$(ENV)

# Install the development and pipeline dependencies from the lockfile.
install:
	uv sync --locked --extra dev --extra pipeline

lock-check:
	uv lock --check

lint:
	uv run --locked ruff check .
	uv run --locked ruff format --check .

# Type-check with the development and pipeline dependencies.
typecheck:
	uv run --locked --extra dev --extra pipeline mypy

# Run unit tests and enforce `fail_under` from `pyproject.toml`.
test:
	uv run --locked --extra dev --extra pipeline pytest tests/unit -q \
		--cov --cov-report=term-missing

# Require the Git index to store `CLAUDE.md` as a symlink to `AGENTS.md`.
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

# Run the cdk-nag synthesis gate for both environments.
synth-all:
	$(MAKE) synth ENV=dev
	$(MAKE) synth ENV=prod

# Render the synthesized design. These diagrams do not represent live AWS state.
# Convert local cdk-dia icon paths into portable DOT and SVG assets.
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
		--target "$(DIAGRAM_FULL).png"; \
	$(CDK_DIA) --tree cdk.out/tree.json \
		--target "$(DIAGRAM_PLATFORM).png" \
		--include "$$prefix-Data" "$$prefix-Ingestion" "$$prefix-Registry" \
			"$$prefix-Training" "$$prefix-Serving" "$$prefix-Monitoring"; \
	$(CDK_DIA) --tree cdk.out/tree.json \
		--target "$(DIAGRAM_SECURITY_CICD).png" \
		--include "$$prefix-Security" "$$prefix-SecurityMonitoring" \
			"$$prefix-Cicd"
	uv run --locked python scripts/prepare_cdk_diagrams.py \
		"$(DIAGRAM_FULL).dot" "$(DIAGRAM_PLATFORM).dot" \
		"$(DIAGRAM_SECURITY_CICD).dot"

security: lock-check audit synth-all

# Bootstrap each target account and region once with the pinned CDK CLI.
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

# Report resource changes from CloudFormation events.
# `UPDATE_COMPLETE` can represent a no-op stack update.
#
# Use a profile with `cloudformation:ListStacks`.
# `${AWS_SECURITY_AUDITOR_USER_NAME}` and `${AWS_ADMIN_USER_NAME}` have this access.
#     AWS_PROFILE=${AWS_SECURITY_AUDITOR_USER_NAME} \
#         make verify-deploy SINCE=<YYYY-MM-DD>
verify-deploy:
	uv run --locked --extra dev python scripts/verify_deployment.py \
		$(if $(SINCE),--since "$(SINCE)") $(if $(PREFIX),--prefix "$(PREFIX)")

# Resolve the deployed API URL and run the signed integration tests.
# The caller needs `execute-api:Invoke` on the method.
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

public-check:
	uv run --locked python scripts/check_public_release.py
