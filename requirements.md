# Odoo ERP Demo Instance Requirements

## Objective
Create a fully dockerized Odoo ERP environment for demonstration purposes, specifically tailored for a developer placement and portage company. This environment will serve as a training ground and a sales tool.

## Key Features
1. **Dockerized Environment**:
   - Odoo ERP (Official Docker image).
   - PostgreSQL Database (Official Docker image).
   - Persistent storage for Odoo addons and database data.

2. **Customized Data (Portage/Developer Placement)**:
   - Pre-loaded dummy data reflecting a "Developer Placement" business model.
   - Example entities: Developers (Employees/Partners), Client Companies, Projects.
   - Sample Transactions: Invoices for services rendered, payroll/payouts for developers.

3. **Open Source approach**:
   - Using Odoo Community Edition.
   - Configuration via `docker-compose.yml`.

4. **Automation**:
   - Automated setup of the database and initial configuration if possible.
   - Scripts or Odoo modules to load the dummy data.

## Proposed Tech Stack
- **Engine**: Docker & Docker Compose.
- **ERP**: Odoo 17.0 (Latest Stable Community Edition).
- **Database**: PostgreSQL 15+.
- **Language**: Python (for any custom scripts or Odoo modules).

## Next Steps
1. Define the specific dummy data structure (Client list, Developer list, Invoice templates).
2. Create the `compose.yml` file.
3. Develop a data loading strategy (CSV imports or a custom Odoo module).
