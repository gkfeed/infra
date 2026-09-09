DBMATE_VERSION := 2.35.1
DBMATE_IMAGE := ghcr.io/amacneil/dbmate:$(DBMATE_VERSION)
export NAME

DBMATE = docker run --rm --network=host \
	--user "$$(id -u):$$(id -g)" \
	-v "$(CURDIR):/work" -w /work \
	-e DATABASE_URL -e DBMATE_STRICT=true \
	$(DBMATE_IMAGE)

.DEFAULT_GOAL := help

.PHONY: help migrate status new dump postgres-config postgres-up postgres-stop

help: ## Show available commands
	@echo "make migrate              Apply pending migrations"
	@echo "make status               Show migration status"
	@echo "make new NAME=add_example Create a migration"
	@echo "make dump                 Write db/schema.sql"
	@echo "make postgres-config      Validate production Compose"
	@echo "make postgres-up          Start production PostgreSQL"
	@echo "make postgres-stop        Stop production PostgreSQL"

migrate: ## Apply pending migrations with strict ordering
	@$(DBMATE) migrate --strict

status: ## Show migration status
	@$(DBMATE) status

new: check-name ## Create a timestamped migration (NAME=...)
	@$(DBMATE) new "$$NAME"

dump: ## Write the current schema to db/schema.sql
	@$(DBMATE) dump

postgres-config: ## Validate the production Compose file and environment
	@docker compose --env-file .env config --quiet

postgres-up: ## Start production PostgreSQL and wait for health
	@docker compose --env-file .env up -d --wait postgres

postgres-stop: ## Stop PostgreSQL without deleting its data
	@docker compose --env-file .env stop postgres

.PHONY: check-name

check-name:
	@if [ -z "$${NAME:-}" ]; then \
		echo "NAME must be passed explicitly, for example: make new NAME=add_feed" >&2; \
		exit 2; \
	fi
