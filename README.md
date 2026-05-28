# Odoo Industry Demo Kits

A scalable, dockerized environment for deploying Odoo 19.0 demo instances pre-populated with industry-specific data. Designed for rapid sales demonstrations, training, and testing across different business sectors.

## 🚀 Quick Start

### 1. Prerequisites
- Docker & Docker Compose
- Make (optional, but recommended)

### 2. Environment Initialization
Initialize your local environment settings from the provided template:
```bash
make init
# Then edit .env to customize your Odoo credentials
```

### 3. Launching Odoo
Use the Makefile for easy orchestration:
```bash
make up
```
The instance will be available at `http://localhost:8069`.

### 4. Seeding Industry Data
To populate the database with a specific industry kit (e.g., Portage/Developer Placement):
```bash
make seed industry=portage
```
This command handles data sync and automated record creation, including realistic financial history and sequence numbering.

## 📂 Project Structure
- `seeds/`: Industry-specific data packages (JSON format).
    - `portage/`: Agency, Client, and Developer data for placement businesses.
- `addons/`: Custom Odoo modules.
- `seed_loader.py`: Generic automation engine using XML-RPC and Environment variables.
- `Makefile`: Unified command interface for deployment.

## ⚖️ License
This project is licensed under the **LGPL-3.0 License**. This ensures compatibility with the Odoo ecosystem while protecting the core logic.

## 🤝 Contribution
To add a new industry:
1. Create a subfolder in `seeds/`.
2. Provide `agency.json`, `clients.json`, and `developers.json`.
3. Run `make seed industry=your_new_industry`.
