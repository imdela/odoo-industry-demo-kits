# Odoo Industry Demo Kits

A scalable, dockerized environment for deploying **Odoo 19.0** demo instances pre-populated with industry-specific data. Designed for rapid development testing, end-to-end integration tests, and sales demonstrations.

## Quick Start

### 1. Prerequisites
- Docker & Docker Compose
- Make
- Python 3 (for seed scripts, run locally)

### 2. Environment Setup
```bash
make init
# Edit .env to set your Odoo credentials
```

### 3. Start Odoo
```bash
make up
```
Available at `http://localhost:8069`.

### 4. Seed Industry Data

Deploy a full industry package (accounting config + companies + resources):
```bash
make seed industry=aion
```

Generate invoices for existing partners (run after `make seed`):
```bash
make seed-invoices industry=aion
```

Full reset + seed + invoices in one command:
```bash
make seed-full industry=aion
```

### 5. Stop / Reset

Stop containers:
```bash
make down
```

Wipe all data (volumes) and restart fresh:
```bash
make reset
make up
```

## Available Commands

| Command | Description |
|---|---|
| `make init` | Initialize `.env` from template |
| `make up` | Start Odoo 19.0 and PostgreSQL containers |
| `make down` | Stop containers |
| `make ps` | List running services |
| `make seed industry=xxx` | Deploy industry data package |
| `make seed-invoices industry=xxx` | Generate invoices for existing partners |
| `make seed-full industry=xxx` | Clean DB + seed companies + generate invoices |
| `make reset` | Wipe all volumes and restart fresh |

## Project Structure

```
odoo-demo/
├── seeds/          # Industry data packages
│   └── aion/       # Aion SaaS industry kit
├── addons/         # Custom Odoo modules
├── seed_loader.py  # Seed automation engine (XML-RPC)
├── Makefile        # Command interface
└── compose.yml     # Docker Compose (Odoo 19.0)
```

## Environment Variables

| Variable | Description | Example |
|---|---|---|
| `ODOO_URL` | Odoo instance URL | `http://localhost:8069` |
| `ODOO_USER` | Admin username | `admin` |
| `ODOO_PASS` | Admin password | `admin` |

## License

LGPL-3.0 — compatible with the Odoo ecosystem.
