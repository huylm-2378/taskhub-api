.PHONY: dev db-stop

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
