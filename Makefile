# NovaBank Digital — developer entry points. Nothing here touches AWS.
PY ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: install lint test coverage tf-fmt tf-validate tf-test security build local-api demo clean

install:
	$(PY) -m venv $(VENV) && $(BIN)/pip install -r requirements-dev.txt

lint:
	$(BIN)/ruff check . && $(BIN)/ruff format --check .

test:
	$(BIN)/python -m pytest -q

coverage:
	$(BIN)/python -m pytest -q --cov --cov-report=term --cov-report=xml

tf-fmt:
	terraform fmt -recursive terraform

tf-validate:
	@for d in terraform/bootstrap terraform/envs/dev terraform/envs/staging terraform/envs/prod; do \
	  terraform -chdir=$$d init -backend=false -input=false >/dev/null && terraform -chdir=$$d validate || exit 1; done

tf-test:
	@for d in terraform/modules/*/; do [ -d $$d/tests ] || continue; \
	  terraform -chdir=$$d init -backend=false -input=false >/dev/null && terraform -chdir=$$d test || exit 1; done

security:
	$(BIN)/bandit -q -c pyproject.toml -r shared services workers
	checkov -d terraform --framework terraform --compact --quiet
	tflint --init --config $(CURDIR)/.tflint.hcl && tflint --recursive --config $(CURDIR)/.tflint.hcl --chdir terraform

build:
	$(BIN)/python scripts/build_lambda.py --out dist

local-api:
	$(BIN)/python scripts/local_api.py

demo:
	NO_PROXY=127.0.0.1 $(BIN)/python scripts/simulate_transfer.py && NO_PROXY=127.0.0.1 $(BIN)/python scripts/simulate_fraud.py

clean:
	rm -rf dist .pytest_cache .ruff_cache .coverage coverage.xml reports
