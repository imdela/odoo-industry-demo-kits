# Odoo Industry Demo Kits - Automation
SHELL := /bin/bash

# Load environment variables from .env file
ifneq (,$(wildcard ./.env))
    include .env
    export
endif

.PHONY: help init up down ps seed reset

help:
	@echo "Odoo Lifecycle Management"
	@echo "Commands:"
	@echo "  make init               Initialize environment from template"
	@echo "  make up                 Start environment"
	@echo "  make down               Stop environment"
	@echo "  make ps                 List active services"
	@echo "  make seed industry=xxx  Deploy data package (e.g. industry=portage)"
	@echo "  make reset              Wipe all data and restart fresh"

init:
	@if [ ! -f .env ]; then cp .env.example .env && echo ".env created from template"; else echo ".env already exists"; fi

up:
	docker compose up -d
	@echo "Initializing services..."
	@sleep 10

down:
	docker compose down

ps:
	docker compose ps

seed:
	@if [ -z "$(industry)" ]; then echo "Error: industry=name is required (e.g. make seed industry=portage)"; exit 1; fi
	@echo "Syncing data to container..."
	docker exec odoo-demo-web-1 mkdir -p /tmp/seeds
	docker cp seeds/. odoo-demo-web-1:/tmp/seeds
	docker cp seed_loader.py odoo-demo-web-1:/tmp/seed_loader.py
	@echo "Deploying $(industry) industry data..."
	docker exec \
		-e ODOO_URL=$(ODOO_URL) \
		-e ODOO_DB=$(ODOO_DB) \
		-e ODOO_USER=$(ODOO_USER) \
		-e ODOO_PASS=$(ODOO_PASS) \
		odoo-demo-web-1 python3 /tmp/seed_loader.py --industry $(industry)

reset:
	docker compose down -v
	@echo "Volumes purged. Ready for fresh install."
