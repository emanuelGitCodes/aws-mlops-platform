.PHONY: install lint test synth deploy destroy

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
