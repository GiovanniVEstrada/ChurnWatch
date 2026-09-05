.PHONY: up down psql venv download load reset-db segment churn forecast dashboard all

up:
	docker compose up -d
	@echo "waiting for postgres..."
	@until docker exec churnwatch-postgres pg_isready -U $${POSTGRES_USER:-churnwatch} > /dev/null 2>&1; do sleep 1; done
	docker exec -i churnwatch-postgres psql -U $${POSTGRES_USER:-churnwatch} -d $${POSTGRES_DB:-churnwatch} < sql/01_schema.sql

down:
	docker compose down

reset-db: down
	rm -rf pgdata
	$(MAKE) up

psql:
	docker exec -it churnwatch-postgres psql -U $${POSTGRES_USER:-churnwatch} -d $${POSTGRES_DB:-churnwatch}

venv:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

download:
	python3 -m scripts.ingest.download_data

load:
	python3 -m scripts.ingest.load_to_postgres

segment:
	python3 -m scripts.segmentation.rfm_segmentation

churn:
	python3 -m scripts.churn.survival_analysis

forecast:
	python3 -m scripts.forecasting.sales_forecast

dashboard:
	python3 -m scripts.dashboard.export_dashboard_data

## Full pipeline from raw data to dashboard inputs (assumes `make up` already ran)
all: download load segment churn forecast dashboard
