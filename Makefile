.PHONY: install lock-check lint typecheck test docs-sync audit synth synth-all \
	diagrams security bootstrap check-stack check-alert-email diff-stack \
	deploy-stack deploy destroy verify-deploy smoke wiki-init wiki-index \
	wiki-search wiki-ingest wiki-lint public-check graph graph-query \
	graph-explain graph-hooks frontend-check check-website-hold

ENV ?= dev
CDK_CLI := uv run --locked npx aws-cdk@2.1130.0
CDK_DIA := npx --yes cdk-dia@0.12.3
DIAGRAM_DIR ?= $(CURDIR)/diagrams
DIAGRAM_FULL := $(abspath $(DIAGRAM_DIR))/cdk-full-$(ENV)
DIAGRAM_PLATFORM := $(abspath $(DIAGRAM_DIR))/cdk-platform-$(ENV)
DIAGRAM_SECURITY_CICD := $(abspath $(DIAGRAM_DIR))/cdk-security-cicd-$(ENV)
DIAGRAM_WEBSITE := $(abspath $(DIAGRAM_DIR))/cdk-website-$(ENV)

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
# The website diagram renders only where `website.enabled` is true. The website
# is the one stack with a VPC, so it gets its own view rather than a place in
# the platform diagram.
diagrams: synth
	@command -v dot >/dev/null 2>&1 || { \
		echo "Graphviz is required. Install it with: brew install graphviz" >&2; \
		exit 2; \
	}
	@mkdir -p "$(abspath $(DIAGRAM_DIR))"
	@set -eu; \
	prefix=$$(uv run --locked --extra dev python -c \
		'from infra.app import stack_prefix; print(stack_prefix("$(ENV)"))'); \
	website=$$(uv run --locked --extra dev python -c \
		'from infra.app import load_config; print(load_config("$(ENV)")["website"]["enabled"])'); \
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
			"$$prefix-Cicd"; \
	dots="$(DIAGRAM_FULL).dot $(DIAGRAM_PLATFORM).dot $(DIAGRAM_SECURITY_CICD).dot"; \
	if [ "$$website" = "True" ]; then \
		$(CDK_DIA) --tree cdk.out/tree.json \
			--target "$(DIAGRAM_WEBSITE).png" \
			--include "$$prefix-Website"; \
		dots="$$dots $(DIAGRAM_WEBSITE).dot"; \
	fi; \
	cd "$(CURDIR)"; \
	uv run --locked python scripts/prepare_cdk_diagrams.py $$dots

# Check the frontend. `npm ci` installs from `frontend/package-lock.json`.
# CI does not run this target yet; the website work is on hold.
frontend-check:
	cd website/frontend && npm ci && npm run typecheck && npm test

security: lock-check audit synth-all

# Bootstrap each target account and region once with the pinned CDK CLI.
# Uses the repository-owned execution policy from scripts/setup_account.sh
# instead of the default AdministratorAccess bootstrap grant.
bootstrap:
	@test -n "$(AWS_ACCOUNT_ID)" || \
		(echo "AWS_ACCOUNT_ID is required, e.g. from .env: set -a && source .env && set +a" >&2; exit 2)
	cd infra && $(CDK_CLI) bootstrap -c env=$(ENV) \
		--cloudformation-execution-policies \
		"arn:aws:iam::$(AWS_ACCOUNT_ID):policy/MLOpsCloudFormationExecutionPolicy,arn:aws:iam::$(AWS_ACCOUNT_ID):policy/MLOpsCloudFormationExecutionPolicyExtension"

check-stack:
	@test -n "$(STACK)" || \
		(echo "STACK is required, for example STACK=Mlops-Dev-SecurityMonitoring" >&2; exit 2)

# The Security stack declares SecurityAlertEmail with no default. CloudFormation
# reuses a stored value on update, so only a first deploy fails without it.
# Pass it on every deploy so a new account behaves like an existing one.
STACK_PREFIX = $(shell uv run --locked --extra dev python -c \
	'from infra.app import stack_prefix; print(stack_prefix("$(ENV)"))')
SECURITY_EMAIL_PARAM = --parameters \
	"$(STACK_PREFIX)-Security:SecurityAlertEmail=$(SECURITY_ALERT_EMAIL)"

check-alert-email:
	@test -n "$(SECURITY_ALERT_EMAIL)" || (echo \
		"SECURITY_ALERT_EMAIL is required. Set it in .env, then: set -a && source .env && set +a" >&2; \
		exit 2)

diff-stack: check-stack
	cd infra && $(CDK_CLI) diff "$(STACK)" -c env=$(ENV) \
		--no-lookups --no-change-set

deploy-stack: check-stack check-alert-email
	cd infra && $(CDK_CLI) deploy "$(STACK)" -c env=$(ENV) \
		--no-lookups --require-approval never $(SECURITY_EMAIL_PARAM)

# `deploy` deploys every stack. The website stack is a leaf, so no other stack
# pulls it in, and `deploy-stack` names its target. Only this target can create
# the website by surprise, so only this target asks.
#
# The stack builds an instance, an address, a distribution, a VPC, and a table.
# That is real monthly cost through a path no deploy has proved.
check-website-hold:
	@website=$$(uv run --locked --extra dev python -c \
		'from infra.app import load_config; print(load_config("$(ENV)")["website"]["enabled"])'); \
	if [ "$$website" = "True" ] && [ -z "$(ALLOW_WEBSITE_DEPLOY)" ]; then \
		echo "$(ENV) builds the website stack, and no deploy has proved it." >&2; \
		echo "Read wiki/pages/decisions/website-local-first-rebuild.md first." >&2; \
		echo "" >&2; \
		echo "  Deploy the rest:  make deploy-stack STACK=Mlops-$$(echo $(ENV) | \
			awk '{print toupper(substr($$0,1,1)) substr($$0,2)}')-<Stack> ENV=$(ENV)" >&2; \
		echo "  Deploy it too:    ALLOW_WEBSITE_DEPLOY=1 make deploy ENV=$(ENV)" >&2; \
		exit 2; \
	fi

deploy: check-alert-email check-website-hold
	cd infra && $(CDK_CLI) deploy --all -c env=$(ENV) --require-approval never \
		$(SECURITY_EMAIL_PARAM)

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

# Rebuild the graphify code graph in `graphify-out/`, which stays untracked.
# The extraction is local and deterministic and needs no LLM.
graph:
	graphify update .

graph-query:
	@test -n "$(Q)" || \
		(echo "Q is required, for example Q='what calls the drift Lambda?'" >&2; exit 2)
	graphify query "$(Q)"

graph-explain:
	@test -n "$(NODE)" || \
		(echo "NODE is required, for example NODE=proxy_handler" >&2; exit 2)
	graphify explain "$(NODE)"

# Install the three git hooks that rebuild the graph.
# `graphify hook install` writes post-commit and post-checkout. Neither runs
# for a pull, so `scripts/git-hooks/post-merge` covers that case.
#
# The installer also registers a union merge driver for
# `graphify-out/graph.json`. This repository never tracks that file, so the
# registration is removed again here.
graph-hooks:
	@set -eu; \
	graphify hook install; \
	hooks=$$(git rev-parse --git-common-dir)/hooks; \
	install -m 755 scripts/git-hooks/post-merge "$$hooks/post-merge"; \
	echo "post-merge: installed at $$hooks/post-merge"; \
	git config --unset merge.graphify.name 2>/dev/null || true; \
	git config --unset merge.graphify.driver 2>/dev/null || true; \
	if [ -f .gitattributes ] && \
		[ "$$(cat .gitattributes)" = "graphify-out/graph.json merge=graphify" ]; then \
		rm .gitattributes; \
		echo "merge driver: registration removed"; \
	fi
