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

3. Update database credentials

Open `app.py` and set your MySQL password on the `get_db_connection()` function, or modify the app to read from environment variables.

4. Run the app

```powershell
python app.py
```

Open http://127.0.0.1:5000

Notes
- Ensure MySQL is running and `vehicle_insurance_db` with table `Customer` exists.
- This repository is intended for local development and teaching — do not use the development server in production.
