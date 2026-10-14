# Everyday commands. Everything runs in Docker; the host only needs Docker (with Compose) and make.
# `make help` lists the targets.

SHELL := /bin/bash
export HOST_UID := $(shell id -u)
export HOST_GID := $(shell id -g)

SYNTHEA_JAR := data/raw/synthea/synthea-with-dependencies-v3.3.0.jar
SYNTHEA_URL := https://github.com/synthetichealth/synthea/releases/download/v3.3.0/synthea-with-dependencies.jar
SYNTHEA_SHA256 := 8ba04f7d73abadd5a377e41edf24c5c83935a1cb07c6d982cd5db731ef1cf445
SYNTHEA_OUT := data/raw/synthea/output_gastric

APP := docker compose --profile dev run --rm app
PSQL := docker compose exec -T db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -v ON_ERROR_STOP=1'

.DEFAULT_GOAL := help
.PHONY: help env build db reset-db test test-fast lint format module synthea-jar generate etl post-etl

help: ## List the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

env: ## Create .env from .env.example (set a real password afterwards)
	@test -f .env && echo ".env already exists" || (cp .env.example .env && echo "created .env: edit POSTGRES_PASSWORD")

build: ## Build the Python image
	docker compose --profile dev build app

db: ## Start PostgreSQL (OMOP)
	docker compose up -d --wait db

reset-db: ## DESTROYS the database volume (the ETL needs an empty database)
	@read -r -p "This deletes the whole OMOP database. Type 'yes' to continue: " a && [ "$$a" = yes ]
	docker compose down -v

test-fast: ## Tests that need no database (what CI runs)
	$(APP) pytest -m "not db"

test: db ## All tests (those marked db need the OMOP database loaded)
	$(APP) pytest

lint: ## ruff check + format check
	$(APP) sh -c 'ruff check . && ruff format --check .'

format: ## Format the code with ruff
	$(APP) ruff format .

module: ## Regenerate the gastric module and check its codes against the vocabulary
	$(APP) python synthea/build_gastric_cancer.py
	$(APP) python -m oncology_assistant.synthea_codes synthea/modules/gastric_cancer.json

synthea-jar: ## Download Synthea v3.3.0 and verify its SHA-256
	@mkdir -p $(dir $(SYNTHEA_JAR))
	@test -f $(SYNTHEA_JAR) || curl -fL -o $(SYNTHEA_JAR) $(SYNTHEA_URL)
	@echo "$(SYNTHEA_SHA256)  $(SYNTHEA_JAR)" | sha256sum -c -

generate: synthea-jar ## Generate the gastric population (SYNTHEA_POP=650 vivos, ~1 300 registros)
	docker compose --profile synthea run --rm synthea

etl: db ## Load Synthea CSVs + Athena vocabulary into an EMPTY database (~30 min; see reset-db)
	SYNTHEA_CSV_DIR=/data/raw/synthea/output_gastric/csv docker compose --profile etl run --rm etl

post-etl: ## Steps after the ETL (value_as_concept_id)
	$(PSQL) < etl/post_etl/01_value_as_concept.sql
