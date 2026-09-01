.PHONY: test lint audit oracle validate preview localstack-up localstack-down

test:
	pytest --cov=audit --cov=src --cov-report=term-missing

lint:
	ruff check audit preview src tests

audit:
	python -m audit.audit_template template.yaml --format markdown

oracle:
	python -m audit.oracle

validate:
	cfn-lint template.yaml
	sam validate --lint --template-file template.yaml

preview:
	python -m preview.app --host 0.0.0.0 --port 8000

localstack-up:
	@test -n "$$LOCALSTACK_AUTH_TOKEN" || (echo "LOCALSTACK_AUTH_TOKEN is required; IAM remains UNVERIFIED." && exit 2)
	docker compose up -d

localstack-down:
	docker compose down
