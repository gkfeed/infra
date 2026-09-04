DBMATE_VERSION := 2.35.1
DBMATE_IMAGE := ghcr.io/amacneil/dbmate:$(DBMATE_VERSION)
export NAME

DBMATE = docker run --rm --network=host \
	--user "$$(id -u):$$(id -g)" \
	-v "$(CURDIR):/work" -w /work \
	-e DATABASE_URL -e DBMATE_STRICT=true \
	$(DBMATE_IMAGE)

.DEFAULT_GOAL := help

.PHONY: help migrate status new dump

help: ## Show available commands
	@echo "make migrate              Apply pending migrations"
	@echo "make status               Show migration status"
	@echo "make new NAME=add_example Create a migration"
	@echo "make dump                 Write db/schema.sql"

migrate: ## Apply pending migrations with strict ordering
	@$(DBMATE) migrate --strict

status: ## Show migration status
	@$(DBMATE) status

new: check-name ## Create a timestamped migration (NAME=...)
	@$(DBMATE) new "$$NAME"

dump: ## Write the current schema to db/schema.sql
	@$(DBMATE) dump

.PHONY: check-name

check-name:
	@if [ -z "$${NAME:-}" ]; then \
		echo "NAME must be passed explicitly, for example: make new NAME=add_feed" >&2; \
		exit 2; \
	fi
