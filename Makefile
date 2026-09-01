VENV_DIR ?= .venv
PYTHON := $(VENV_DIR)/bin/python
SAM := $(if $(wildcard $(VENV_DIR)/bin/sam),$(VENV_DIR)/bin/sam,sam)

.PHONY: preview-bootstrap dev-bootstrap test lint audit oracle validate preview localstack-up localstack-down

preview-bootstrap:
	@VENV_DIR="$(VENV_DIR)" bash scripts/bootstrap_env.sh preview

dev-bootstrap:
	@VENV_DIR="$(VENV_DIR)" bash scripts/bootstrap_env.sh dev

test: dev-bootstrap
	"$(PYTHON)" -m pytest --cov=audit --cov=src --cov-report=term-missing

lint: dev-bootstrap
	"$(PYTHON)" -m ruff check audit preview src tests

audit: preview-bootstrap
	"$(PYTHON)" -m audit.audit_template template.yaml --format markdown

oracle: preview-bootstrap
	"$(PYTHON)" -m audit.oracle

validate: dev-bootstrap
	"$(VENV_DIR)/bin/cfn-lint" template.yaml
	"$(SAM)" validate --lint --template-file template.yaml

preview: preview-bootstrap
	"$(PYTHON)" -m preview.app --host 0.0.0.0 --port 8000

localstack-up:
	@test -n "$$LOCALSTACK_AUTH_TOKEN" || (echo "LOCALSTACK_AUTH_TOKEN is required; IAM remains UNVERIFIED." && exit 2)
	docker compose up -d

localstack-down:
	docker compose down
