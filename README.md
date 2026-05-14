# Car Insurance Portal (Flask + MySQL)

Local motor-insurance workflow app with customer intake, role-based underwriting dashboard, policy PDF generation, and submission acknowledgements.

## Features

- Public customer application form with live premium estimate.
- Admin/reviewer login and role-based dashboard.
- Application workflow: Pending -> Under Review -> Approved/Rejected.
- Policy PDF generation after approval.
- Email/SMS acknowledgement attempt on successful submission.
- Auto schema setup for MySQL database/table/users.

## Step-by-step setup (Windows PowerShell)

1. Create and activate virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies

```powershell
pip install -r requirements.txt
```

3. Create local environment config

```powershell
Copy-Item .env.example .env
```

4. Edit `.env` and set at least your MySQL credentials:

```text
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password_here
MYSQL_DB=vehicle_insurance_db
FLASK_SECRET_KEY=replace_with_a_long_random_secret
```

5. Run app

```powershell
python app.py
```

Open public portal: http://127.0.0.1:5000

## Step 1: Admin login + role dashboard

- Login URL: http://127.0.0.1:5000/login
- Default seeded users (change in `.env` for production-like setup):
	- `admin / Admin@12345`
	- `reviewer / Reviewer@12345`
- Role permissions:
	- `admin`: review + approve/reject + generate/download policy PDF
	- `reviewer`: mark under review + view/download policy PDF for approved cases

## Step 2: Policy PDF generation after approval

- In dashboard, admin clicks **Approve + PDF** on an application.
- App sets a policy number and generates PDF under `generated_policies/`.
- Approved entries show **Download PDF** action.

## Step 3: Email/SMS acknowledgement on submission

When a customer submits form, app attempts acknowledgements:

- Email via SMTP (configure all):
	- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS`
- SMS via Twilio (configure all):
	- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `DEFAULT_SMS_COUNTRY_CODE`

If channels are not configured, submission still succeeds and the app shows a message that acknowledgements were not sent.

## Important

- This is for local development/demo workflow.
- Never commit real credentials in `.env`.
