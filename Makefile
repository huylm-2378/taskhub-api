.PHONY: dev db-stop migration

PYTHON := $(CURDIR)/venv/bin/python3
HOST ?= 127.0.0.1
PORT ?= 8000

dev:
	@test -x "$(PYTHON)" || { echo "Chưa có venv. Hãy cài môi trường theo README.md."; exit 1; }
	docker compose up -d --wait db
	"$(PYTHON)" -m alembic upgrade head
	"$(PYTHON)" -m uvicorn main:app --reload --host "$(HOST)" --port "$(PORT)"

db-stop:
	docker compose stop db

migration: export MIGRATION_MESSAGE = $(m)
migration:
	@test -n "$$MIGRATION_MESSAGE" || { echo 'Cách dùng: make migration m="add categories"'; exit 1; }
	@test -x "$(PYTHON)" || { echo "Chưa có venv. Hãy cài môi trường theo README.md."; exit 1; }
	"$(PYTHON)" -m alembic revision --autogenerate -m "$$MIGRATION_MESSAGE"
