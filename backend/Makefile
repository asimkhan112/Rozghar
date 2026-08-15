.PHONY: up down migrate downgrade reset seed check verify lint fmt run

VENV := ./.venv/bin

up:            ## start postgres + redis
	docker compose up -d
down:          ## stop them
	docker compose down
migrate:       ## apply all migrations
	$(VENV)/alembic upgrade head
downgrade:     ## roll back one revision
	$(VENV)/alembic downgrade -1
reset:         ## drop everything and rebuild
	$(VENV)/alembic downgrade base && $(VENV)/alembic upgrade head
check:         ## fail if the models and the database have drifted
	$(VENV)/alembic check
verify:        ## full milestone-1 gate: round-trip twice, then check drift
	$(VENV)/alembic downgrade base && $(VENV)/alembic upgrade head
	$(VENV)/alembic downgrade base && $(VENV)/alembic upgrade head
	$(VENV)/alembic check
lint:
	$(VENV)/ruff check app alembic
fmt:
	$(VENV)/ruff format app alembic
run:           ## dev server (no routes until milestone 2)
	$(VENV)/uvicorn app.main:app --reload --port 8000
