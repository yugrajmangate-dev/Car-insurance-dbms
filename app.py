import base64
import importlib.util
import os
import smtplib
from datetime import date, datetime
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import mysql.connector
from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from mysql.connector import Error
from werkzeug.security import check_password_hash, generate_password_hash

PDF_ENGINE_AVAILABLE = importlib.util.find_spec("reportlab") is not None

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

POLICY_DIR = Path(__file__).resolve().parent / "generated_policies"
ALLOWED_DASHBOARD_ROLES = {"admin", "reviewer"}


def get_mysql_settings(include_database=True):
    """Build MySQL connection settings from environment variables."""
    settings = {
        "host": os.environ.get("MYSQL_HOST", "localhost"),
        "user": os.environ.get("MYSQL_USER", "root"),
        "password": os.environ.get("MYSQL_PASSWORD"),
    }
    if include_database:
        settings["database"] = os.environ.get("MYSQL_DB", "vehicle_insurance_db")
    return settings


def get_server_connection():
    """Return a MySQL server connection without selecting a database."""
    return mysql.connector.connect(**get_mysql_settings(include_database=False))


def get_db_connection():
    """Return a MySQL connection using configured database settings."""
    return mysql.connector.connect(**get_mysql_settings(include_database=True))


def ensure_column_exists(cursor, table_name, column_name, definition_sql):
    """Ensure a column exists for backward-compatible table migrations."""
    db_name = os.environ.get("MYSQL_DB", "vehicle_insurance_db")
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
          AND column_name = %s
        """,
        (db_name, table_name, column_name),
    )
    if cursor.fetchone() is None:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition_sql}")


def ensure_index_exists(cursor, table_name, index_name, index_sql):
    """Ensure a named index exists on a table."""
    db_name = os.environ.get("MYSQL_DB", "vehicle_insurance_db")
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = %s
          AND table_name = %s
          AND index_name = %s
        LIMIT 1
        """,
        (db_name, table_name, index_name),
    )
    if cursor.fetchone() is None:
        cursor.execute(f"ALTER TABLE {table_name} ADD {index_sql}")


def seed_default_user(cursor, username, password, role, full_name, email):
    """Create a seed user if username is not already present."""
    if not username or not password:
        return

    cursor.execute("SELECT user_id FROM users WHERE username = %s", (username,))
    if cursor.fetchone() is not None:
        return

    cursor.execute(
        """
        INSERT INTO users (username, password_hash, role, full_name, email, is_active)
        VALUES (%s, %s, %s, %s, %s, 1)
        """,
        (username, generate_password_hash(password), role, full_name, email),
    )


def ensure_default_users(cursor):
    """Ensure admin and reviewer accounts are available."""
    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@12345")
    reviewer_username = os.environ.get("REVIEWER_USERNAME", "reviewer")
    reviewer_password = os.environ.get("REVIEWER_PASSWORD", "Reviewer@12345")

    seed_default_user(
        cursor,
        username=admin_username,
        password=admin_password,
        role="admin",
        full_name="System Admin",
        email="admin@novadrive.local",
    )
    seed_default_user(
        cursor,
        username=reviewer_username,
        password=reviewer_password,
        role="reviewer",
        full_name="Policy Reviewer",
        email="reviewer@novadrive.local",
    )


def ensure_database_and_tables():
    """Create database schema, tables, and seed users when missing."""
    db_name = os.environ.get("MYSQL_DB", "vehicle_insurance_db").replace("`", "")

    server_conn = get_server_connection()
    server_cursor = server_conn.cursor()
    server_cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
    server_conn.commit()
    server_cursor.close()
    server_conn.close()

    app_conn = get_db_connection()
    app_cursor = app_conn.cursor()

    app_cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS insurance_applications (
            application_id INT AUTO_INCREMENT PRIMARY KEY,
            full_name VARCHAR(120) NOT NULL,
            email VARCHAR(120) NOT NULL,
            phone VARCHAR(20) NOT NULL,
            dob DATE NOT NULL,
            city VARCHAR(80) NOT NULL,
            state VARCHAR(80) NOT NULL,
            vehicle_make VARCHAR(80) NOT NULL,
            vehicle_model VARCHAR(80) NOT NULL,
            vehicle_year INT NOT NULL,
            vehicle_value DECIMAL(12,2) NOT NULL,
            fuel_type VARCHAR(20) NOT NULL,
            usage_type VARCHAR(20) NOT NULL,
            annual_km INT NOT NULL,
            prior_claims INT NOT NULL DEFAULT 0,
            accidents_last_5y INT NOT NULL DEFAULT 0,
            coverage_type VARCHAR(30) NOT NULL,
            add_ons VARCHAR(255),
            deductible_amount DECIMAL(10,2) NOT NULL,
            estimated_premium DECIMAL(10,2) NOT NULL,
            application_status VARCHAR(30) NOT NULL DEFAULT 'Pending Review',
            policy_number VARCHAR(40),
            approved_at DATETIME NULL,
            approved_by INT NULL,
            notification_email_sent TINYINT(1) NOT NULL DEFAULT 0,
            notification_sms_sent TINYINT(1) NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    app_cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(80) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(30) NOT NULL,
            full_name VARCHAR(120) NOT NULL,
            email VARCHAR(120),
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    ensure_column_exists(app_cursor, "insurance_applications", "policy_number", "VARCHAR(40) NULL")
    ensure_column_exists(app_cursor, "insurance_applications", "approved_at", "DATETIME NULL")
    ensure_column_exists(app_cursor, "insurance_applications", "approved_by", "INT NULL")
    ensure_column_exists(
        app_cursor,
        "insurance_applications",
        "notification_email_sent",
        "TINYINT(1) NOT NULL DEFAULT 0",
    )
    ensure_column_exists(
        app_cursor,
        "insurance_applications",
        "notification_sms_sent",
        "TINYINT(1) NOT NULL DEFAULT 0",
    )
    ensure_index_exists(
        app_cursor,
        "insurance_applications",
        "idx_policy_number",
        "UNIQUE INDEX idx_policy_number (policy_number)",
    )

    ensure_default_users(app_cursor)

    app_conn.commit()
    app_cursor.close()
    app_conn.close()


def parse_dob(dob_text):
    """Parse a date string in YYYY-MM-DD format."""
    return datetime.strptime(dob_text, "%Y-%m-%d").date()


def calculate_age(dob):
    """Calculate current age from date of birth."""
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def calculate_estimated_premium(
    vehicle_value,
    coverage_type,
    vehicle_year,
    prior_claims,
    accidents_last_5y,
    usage_type,
    add_ons,
    deductible_amount,
    dob,
):
    """Estimate annual premium using straightforward underwriting factors."""
    base_rate_by_coverage = {
        "Third Party": 0.018,
        "Comprehensive": 0.045,
        "Zero Depreciation": 0.060,
    }
    add_on_cost_map = {
        "Roadside Assistance": 900,
        "Engine Protect": 1800,
        "Return To Invoice": 2500,
        "Consumables Cover": 1200,
    }

    base_rate = base_rate_by_coverage.get(coverage_type, 0.045)
    premium = float(vehicle_value) * base_rate

    driver_age = calculate_age(dob)
    if driver_age < 25:
        premium *= 1.18
    elif driver_age > 60:
        premium *= 1.10

    vehicle_age = max(date.today().year - vehicle_year, 0)
    if vehicle_age >= 10:
        premium *= 1.15
    elif vehicle_age <= 3:
        premium *= 0.95

    if usage_type == "Commercial":
        premium *= 1.22

    premium *= 1 + min(prior_claims * 0.07, 0.35)
    premium *= 1 + min(accidents_last_5y * 0.05, 0.25)

    for add_on in add_ons:
        premium += add_on_cost_map.get(add_on, 0)

    deductible_discount = min(float(deductible_amount) * 0.08, premium * 0.20)
    premium -= deductible_discount

    return round(max(premium, 2500.0), 2)


def parse_bool_env(name, default=False):
    """Read a boolean-like environment variable value."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_phone(phone):
    """Normalize phone number to international format for SMS providers."""
    phone = phone.strip()
    if phone.startswith("+"):
        return phone

    digits_only = "".join(ch for ch in phone if ch.isdigit())
    if not digits_only:
        return phone

    if len(digits_only) == 10:
        country_code = os.environ.get("DEFAULT_SMS_COUNTRY_CODE", "+91")
        return f"{country_code}{digits_only}"

    return f"+{digits_only}"


def send_submission_email_ack(full_name, email, application_id, premium):
    """Send acknowledgement email using SMTP settings when configured."""
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_from = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_use_tls = parse_bool_env("SMTP_USE_TLS", default=True)

    if not smtp_host or not smtp_from or not email:
        return False, "SMTP is not fully configured."

    subject = f"NovaDrive Insurance Application #{application_id} Received"
    body = (
        f"Dear {full_name},\n\n"
        f"Thank you for submitting your motor insurance application.\n"
        f"Application ID: {application_id}\n"
        f"Estimated annual premium: INR {premium:,.2f}\n\n"
        "Our underwriting team will review your request and contact you shortly.\n\n"
        "Regards,\nNovaDrive Insurance"
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp_from
    message["To"] = email
    message.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=12) as smtp_server:
            if smtp_use_tls:
                smtp_server.starttls()
            if smtp_user and smtp_password:
                smtp_server.login(smtp_user, smtp_password)
            smtp_server.send_message(message)
        return True, "Email acknowledgement sent."
    except (smtplib.SMTPException, OSError) as err:
        return False, f"Email acknowledgement failed: {err}"


def send_submission_sms_ack(full_name, phone, application_id, premium):
    """Send acknowledgement SMS through Twilio REST API when configured."""
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")
    to_number = normalize_phone(phone)

    if not sid or not token or not from_number:
        return False, "Twilio is not configured."

    body = (
        f"NovaDrive: Application #{application_id} received for {full_name}. "
        f"Estimated premium INR {premium:,.0f}."
    )

    payload = urlencode({"To": to_number, "From": from_number, "Body": body}).encode("utf-8")
    request_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    auth_token = base64.b64encode(f"{sid}:{token}".encode("utf-8")).decode("utf-8")

    req = Request(request_url, data=payload)
    req.add_header("Authorization", f"Basic {auth_token}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urlopen(req, timeout=12) as response:
            if 200 <= response.status < 300:
                return True, "SMS acknowledgement sent."
        return False, "SMS provider returned a non-success response."
    except (HTTPError, URLError, OSError) as err:
        return False, f"SMS acknowledgement failed: {err}"


def store_notification_flags(application_id, email_sent, sms_sent):
    """Persist acknowledgement delivery flags for tracking."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE insurance_applications
        SET notification_email_sent = %s,
            notification_sms_sent = %s
        WHERE application_id = %s
        """,
        (1 if email_sent else 0, 1 if sms_sent else 0, application_id),
    )
    conn.commit()
    cursor.close()
    conn.close()


def send_submission_acknowledgements(application_id, full_name, email, phone, premium):
    """Send email/SMS acknowledgements while keeping submission flow resilient."""
    email_sent, email_message = send_submission_email_ack(full_name, email, application_id, premium)
    sms_sent, sms_message = send_submission_sms_ack(full_name, phone, application_id, premium)

    try:
        store_notification_flags(application_id, email_sent, sms_sent)
    except Error as db_err:
        print(f"Warning: failed to store notification flags for #{application_id}: {db_err}")

    return {
        "email_sent": email_sent,
        "sms_sent": sms_sent,
        "email_message": email_message,
        "sms_message": sms_message,
    }


def login_required(view_func):
    """Require authenticated session for protected views."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user" not in session:
            flash("Please sign in to continue.", "error")
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)

    return wrapped


def roles_required(*roles):
    """Require one of the listed roles for protected views."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            user = session.get("user")
            if not user:
                flash("Please sign in to continue.", "error")
                return redirect(url_for("login", next=request.path))
            if user.get("role") not in roles:
                flash("You do not have permission for this action.", "error")
                return redirect(url_for("admin_dashboard"))
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def generate_policy_number(application_id):
    """Generate a deterministic policy number for approved applications."""
    return f"POL-{date.today():%Y%m%d}-{application_id:06d}"


def fetch_application_for_policy(application_id):
    """Fetch a single application record for policy rendering."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            ia.*,
            DATE_FORMAT(ia.created_at, '%%d-%%b-%%Y %%H:%%i') AS created_at_display,
            DATE_FORMAT(ia.approved_at, '%%d-%%b-%%Y %%H:%%i') AS approved_at_display,
            u.full_name AS approver_name
        FROM insurance_applications ia
        LEFT JOIN users u ON u.user_id = ia.approved_by
        WHERE ia.application_id = %s
        """,
        (application_id,),
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row


def create_policy_pdf(application):
    """Generate PDF document for an approved policy and return file path."""
    if not PDF_ENGINE_AVAILABLE:
        raise RuntimeError("ReportLab is not installed. Install dependencies and retry.")

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError as err:
        raise RuntimeError("ReportLab imports failed in the active environment.") from err

    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = POLICY_DIR / f"{application['policy_number']}.pdf"

    pdf = canvas.Canvas(str(pdf_path), pagesize=A4)
    _, height = A4
    y = height - 60

    pdf.setTitle(f"Policy {application['policy_number']}")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(40, y, "NovaDrive Insurance - Motor Policy")
    y -= 26
    pdf.setFont("Helvetica", 11)
    pdf.drawString(40, y, f"Policy Number: {application['policy_number']}")
    y -= 18
    pdf.drawString(40, y, f"Application ID: {application['application_id']}")
    y -= 18
    pdf.drawString(40, y, f"Approved On: {application.get('approved_at_display') or '-'}")
    y -= 18
    pdf.drawString(40, y, f"Approved By: {application.get('approver_name') or 'System'}")

    y -= 30
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(40, y, "Policy Holder")
    y -= 18
    pdf.setFont("Helvetica", 11)
    pdf.drawString(40, y, f"Name: {application['full_name']}")
    y -= 16
    pdf.drawString(40, y, f"Email: {application['email']}")
    y -= 16
    pdf.drawString(40, y, f"Phone: {application['phone']}")
    y -= 16
    pdf.drawString(40, y, f"Location: {application['city']}, {application['state']}")

    y -= 28
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(40, y, "Vehicle & Coverage")
    y -= 18
    pdf.setFont("Helvetica", 11)
    pdf.drawString(40, y, f"Vehicle: {application['vehicle_make']} {application['vehicle_model']} ({application['vehicle_year']})")
    y -= 16
    pdf.drawString(40, y, f"Fuel/Usage: {application['fuel_type']} / {application['usage_type']}")
    y -= 16
    pdf.drawString(40, y, f"Coverage: {application['coverage_type']}")
    y -= 16
    pdf.drawString(40, y, f"Add-ons: {application.get('add_ons') or 'None'}")
    y -= 16
    pdf.drawString(40, y, f"Deductible: INR {float(application['deductible_amount']):,.2f}")
    y -= 16
    pdf.drawString(40, y, f"Annual Premium: INR {float(application['estimated_premium']):,.2f}")

    y -= 32
    pdf.setFont("Helvetica-Oblique", 10)
    pdf.drawString(
        40,
        y,
        "This is a system-generated policy document for local demo and workflow purposes.",
    )

    pdf.showPage()
    pdf.save()
    return pdf_path


@app.context_processor
def inject_session_context():
    """Expose current user session to all templates."""
    return {"current_user": session.get("user")}


@app.route("/")
def index():
    """Render public insurance application form."""
    db_error = None
    try:
        ensure_database_and_tables()
    except Error as err:
        db_error = f"Database unavailable right now: {err}"

    return render_template(
        "index.html",
        db_error=db_error,
        current_year=date.today().year,
    )


@app.route("/apply", methods=["POST"])
def submit_application():
    """Validate and store a new insurance application, then trigger acknowledgements."""
    required_fields = [
        "full_name",
        "email",
        "phone",
        "dob",
        "city",
        "state",
        "vehicle_make",
        "vehicle_model",
        "vehicle_year",
        "vehicle_value",
        "fuel_type",
        "usage_type",
        "annual_km",
        "coverage_type",
        "deductible_amount",
    ]

    missing = [field for field in required_fields if not request.form.get(field)]
    if missing:
        flash("Please complete all mandatory fields before submitting.", "error")
        return redirect(url_for("index"))

    try:
        full_name = request.form["full_name"].strip()
        email = request.form["email"].strip()
        phone = request.form["phone"].strip()
        dob = parse_dob(request.form["dob"])
        city = request.form["city"].strip()
        state = request.form["state"].strip()

        vehicle_make = request.form["vehicle_make"].strip()
        vehicle_model = request.form["vehicle_model"].strip()
        vehicle_year = int(request.form["vehicle_year"])
        vehicle_value = float(request.form["vehicle_value"])
        fuel_type = request.form["fuel_type"].strip()
        usage_type = request.form["usage_type"].strip()
        annual_km = int(request.form["annual_km"])
        prior_claims = int(request.form.get("prior_claims", 0) or 0)
        accidents_last_5y = int(request.form.get("accidents_last_5y", 0) or 0)
        coverage_type = request.form["coverage_type"].strip()
        add_ons = request.form.getlist("add_ons")
        deductible_amount = float(request.form["deductible_amount"])

        if vehicle_year < 1980 or vehicle_year > date.today().year + 1:
            raise ValueError("Vehicle year is outside valid range.")
        if vehicle_value <= 0 or annual_km <= 0:
            raise ValueError("Vehicle value and annual kilometers must be positive.")
        if prior_claims < 0 or accidents_last_5y < 0:
            raise ValueError("Claims and accidents cannot be negative.")
        if deductible_amount < 0:
            raise ValueError("Deductible cannot be negative.")

        estimated_premium = calculate_estimated_premium(
            vehicle_value=vehicle_value,
            coverage_type=coverage_type,
            vehicle_year=vehicle_year,
            prior_claims=prior_claims,
            accidents_last_5y=accidents_last_5y,
            usage_type=usage_type,
            add_ons=add_ons,
            deductible_amount=deductible_amount,
            dob=dob,
        )

        ensure_database_and_tables()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO insurance_applications (
                full_name,
                email,
                phone,
                dob,
                city,
                state,
                vehicle_make,
                vehicle_model,
                vehicle_year,
                vehicle_value,
                fuel_type,
                usage_type,
                annual_km,
                prior_claims,
                accidents_last_5y,
                coverage_type,
                add_ons,
                deductible_amount,
                estimated_premium
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                full_name,
                email,
                phone,
                dob,
                city,
                state,
                vehicle_make,
                vehicle_model,
                vehicle_year,
                vehicle_value,
                fuel_type,
                usage_type,
                annual_km,
                prior_claims,
                accidents_last_5y,
                coverage_type,
                ", ".join(add_ons),
                deductible_amount,
                estimated_premium,
            ),
        )
        conn.commit()
        new_application_id = cursor.lastrowid
        cursor.close()
        conn.close()

        ack_result = send_submission_acknowledgements(
            application_id=new_application_id,
            full_name=full_name,
            email=email,
            phone=phone,
            premium=estimated_premium,
        )

        flash(
            (
                f"Application #{new_application_id} submitted successfully. "
                f"Estimated annual premium: INR {estimated_premium:,.2f}."
            ),
            "success",
        )

        if ack_result["email_sent"] or ack_result["sms_sent"]:
            flash("Acknowledgement sent via configured channels.", "success")
        else:
            flash(
                (
                    "Application saved, but acknowledgement channels are not fully configured "
                    "for this environment."
                ),
                "error",
            )
    except ValueError as err:
        flash(f"Validation error: {err}", "error")
    except Error as err:
        flash(f"Database error: {err}", "error")

    return redirect(url_for("index"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate admin/reviewer users for dashboard access."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "error")
            return render_template("login.html")

        try:
            ensure_database_and_tables()
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT user_id, username, password_hash, role, full_name, is_active
                FROM users
                WHERE username = %s
                """,
                (username,),
            )
            user = cursor.fetchone()
            cursor.close()
            conn.close()
        except Error as err:
            flash(f"Login unavailable: {err}", "error")
            return render_template("login.html")

        if not user or not user["is_active"]:
            flash("Invalid username or password.", "error")
            return render_template("login.html")

        if not check_password_hash(user["password_hash"], password):
            flash("Invalid username or password.", "error")
            return render_template("login.html")

        if user["role"] not in ALLOWED_DASHBOARD_ROLES:
            flash("This account has no dashboard role assigned.", "error")
            return render_template("login.html")

        session["user"] = {
            "user_id": user["user_id"],
            "username": user["username"],
            "role": user["role"],
            "full_name": user["full_name"],
        }
        flash(f"Welcome back, {user['full_name']}.", "success")

        next_url = request.args.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("admin_dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    """Log out current session."""
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))


def fetch_dashboard_counts(cursor):
    """Fetch summary status counts for dashboard cards."""
    cursor.execute(
        """
        SELECT
            COUNT(*) AS total_count,
            SUM(application_status = 'Pending Review') AS pending_count,
            SUM(application_status = 'Under Review') AS under_review_count,
            SUM(application_status = 'Approved') AS approved_count,
            SUM(application_status = 'Rejected') AS rejected_count
        FROM insurance_applications
        """
    )
    return cursor.fetchone()


@app.route("/admin/dashboard")
@roles_required("admin", "reviewer")
def admin_dashboard():
    """Render role-based dashboard with application management controls."""
    status_filter = request.args.get("status", "all")
    allowed_filters = {"all", "Pending Review", "Under Review", "Approved", "Rejected"}
    if status_filter not in allowed_filters:
        status_filter = "all"

    try:
        ensure_database_and_tables()
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        counts = fetch_dashboard_counts(cursor)

        where_clause = ""
        params = []
        if status_filter != "all":
            where_clause = "WHERE ia.application_status = %s"
            params.append(status_filter)

        cursor.execute(
            f"""
            SELECT
                ia.application_id,
                ia.full_name,
                ia.email,
                ia.phone,
                ia.vehicle_make,
                ia.vehicle_model,
                ia.coverage_type,
                ia.estimated_premium,
                ia.application_status,
                ia.policy_number,
                ia.notification_email_sent,
                ia.notification_sms_sent,
                DATE_FORMAT(ia.created_at, '%%d-%%b-%%Y %%H:%%i') AS created_at_display,
                u.full_name AS approver_name
            FROM insurance_applications ia
            LEFT JOIN users u ON u.user_id = ia.approved_by
            {where_clause}
            ORDER BY ia.created_at DESC
            LIMIT 300
            """,
            params,
        )
        applications = cursor.fetchall()

        cursor.close()
        conn.close()
    except Error as err:
        flash(f"Dashboard unavailable: {err}", "error")
        counts = {
            "total_count": 0,
            "pending_count": 0,
            "under_review_count": 0,
            "approved_count": 0,
            "rejected_count": 0,
        }
        applications = []

    return render_template(
        "dashboard.html",
        applications=applications,
        status_filter=status_filter,
        counts=counts,
    )


@app.route("/admin/applications/<int:application_id>/review", methods=["POST"])
@roles_required("admin", "reviewer")
def mark_under_review(application_id):
    """Move application to Under Review state."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE insurance_applications
            SET application_status = 'Under Review'
            WHERE application_id = %s
              AND application_status IN ('Pending Review', 'Under Review')
            """,
            (application_id,),
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"Application #{application_id} moved to Under Review.", "success")
    except Error as err:
        flash(f"Could not update application #{application_id}: {err}", "error")

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/applications/<int:application_id>/approve", methods=["POST"])
@roles_required("admin")
def approve_application(application_id):
    """Approve application and generate policy number/PDF."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT application_id, application_status, policy_number
            FROM insurance_applications
            WHERE application_id = %s
            """,
            (application_id,),
        )
        row = cursor.fetchone()

        if row is None:
            cursor.close()
            conn.close()
            flash(f"Application #{application_id} not found.", "error")
            return redirect(url_for("admin_dashboard"))

        policy_number = row["policy_number"] or generate_policy_number(application_id)

        cursor.execute(
            """
            UPDATE insurance_applications
            SET application_status = 'Approved',
                policy_number = %s,
                approved_at = NOW(),
                approved_by = %s
            WHERE application_id = %s
            """,
            (policy_number, session["user"]["user_id"], application_id),
        )
        conn.commit()
        cursor.close()
        conn.close()

        application = fetch_application_for_policy(application_id)
        create_policy_pdf(application)
        flash(
            (
                f"Application #{application_id} approved. "
                f"Policy {policy_number} generated successfully."
            ),
            "success",
        )
    except (Error, RuntimeError) as err:
        flash(f"Approval completed but policy PDF could not be created: {err}", "error")

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/applications/<int:application_id>/reject", methods=["POST"])
@roles_required("admin")
def reject_application(application_id):
    """Reject an application."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE insurance_applications
            SET application_status = 'Rejected'
            WHERE application_id = %s
            """,
            (application_id,),
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"Application #{application_id} rejected.", "success")
    except Error as err:
        flash(f"Could not reject application #{application_id}: {err}", "error")

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/policies/<int:application_id>/pdf")
@roles_required("admin", "reviewer")
def download_policy_pdf(application_id):
    """Download generated policy PDF for approved applications."""
    try:
        application = fetch_application_for_policy(application_id)
        if not application:
            flash("Application not found.", "error")
            return redirect(url_for("admin_dashboard"))

        if application["application_status"] != "Approved":
            flash("Policy PDF is available only for approved applications.", "error")
            return redirect(url_for("admin_dashboard"))

        if not application.get("policy_number"):
            policy_number = generate_policy_number(application_id)
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE insurance_applications SET policy_number = %s WHERE application_id = %s",
                (policy_number, application_id),
            )
            conn.commit()
            cursor.close()
            conn.close()
            application["policy_number"] = policy_number

        pdf_path = create_policy_pdf(application)
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f"{application['policy_number']}.pdf",
            mimetype="application/pdf",
        )
    except (Error, RuntimeError) as err:
        flash(f"Could not generate/download PDF: {err}", "error")
        return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    try:
        ensure_database_and_tables()
    except Error as err:
        print(f"Warning: Could not initialize database at startup: {err}")

    app.run(debug=True)
