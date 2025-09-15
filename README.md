Bookcase Business Manager

A lightweight Flask-based app to manage customers, bookings, work orders, invoices, and transactions for small businesses.

📦 Features

Manage Customers (name, email, phone, address, notes)

Manage Bookings tied to customers (dates, status, notes)

Create and track Work Orders tied to bookings

Generate Invoices from work orders (with PDF export)

Record Transactions (income/expenses, receipts, status)

Configure Job Types with base pricing

Dashboard with key business metrics

Database Backup and restore support (from the settings page)

🚀 Installation
1. Clone the project
git clone https://github.com/YOUR-REPO/bookcase.git
cd bookcase

2. Docker Setup (Recommended)

Build and run the container:

docker build -t bookcase .
docker run -d -p 5000:5000 -v $(pwd)/instance:/app/instance bookcase


This will:

Expose the app on http://localhost:5000

Persist your SQLite DB in ./instance/business.db

3. Local Python Setup (Optional)

If you want to run outside Docker:

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py

💾 Database
Default DB

SQLite file: instance/business.db

Auto-created on first run.

Backup

From the Settings → Backup page you can click Backup Database.

This copies business.db into a timestamped file in backups/.

Example:

backups/business_backup_2025-09-12_16-30-00.db

Restore

To restore a backup:

Stop the app (Docker container or local run).

Copy the backup file back into instance/:

cp backups/business_backup_2025-09-12_16-30-00.db instance/business.db


Restart the app.
Your data will now be restored.

📑 Invoices

Generated directly from a booking’s work orders.

Stored in DB (Invoice + InvoiceItems).

Can be exported as PDF (/invoices/<id>/pdf).

Deleting an invoice will also delete its line items (cascade delete).

🛠 Development Notes

Models: SQLAlchemy

Templates: Jinja2 + Bootstrap

PDF generation: ReportLab

Backups: shutil.copy with timestamp

🔒 Security Notes

Default secret key is "dev-secret-key".
For production, set:

export SECRET_KEY="your-super-secret-key"


SQLite is fine for small-scale usage. For production, consider Postgres or MySQL.

👤 Author

Mike Rodriguez
(with ChatGPT co-pilot for code + docs)