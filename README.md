# Car-insurance-dbms

Simple Flask app that connects to a local MySQL database (vehicle_insurance_db)

Quick start

1. Create and activate a virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

2. Install dependencies

```powershell
pip install -r requirements.txt
```

3. Configure database credentials (recommended: environment variables)

Create a `.env` file in the project root (do NOT commit it) based on `.env.example` and set `MYSQL_PASSWORD` and any other values you need. The app uses `python-dotenv` in development to load `.env` values. Example `.env` (copy from `.env.example`):

```text
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password_here
MYSQL_DB=vehicle_insurance_db
```

Alternatively you can set environment variables directly in your shell.

4. Run the app

```powershell
python app.py
```

Open http://127.0.0.1:5000

Notes
- Ensure MySQL is running and `vehicle_insurance_db` with table `Customer` exists.
- This repository is intended for local development and teaching — do not use the development server in production.
