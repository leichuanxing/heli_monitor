.PHONY: lint test test-backend test-frontend build compose-config up down smoke-test

lint:
	docker compose run --rm backend ruff check .
	docker compose run --rm frontend npm run lint

test: test-backend test-frontend

test-backend:
	docker compose run --rm backend pytest

test-frontend:
	docker compose run --rm frontend npm run test

build:
	docker compose build

compose-config:
	docker compose config --quiet

up:
	docker compose up -d --build

down:
	docker compose down

smoke-test:
	python scripts/smoke_test.py http://localhost:$${NGINX_PORT:-80}

