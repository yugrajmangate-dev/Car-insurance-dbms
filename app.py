from flask import Flask, render_template, request, redirect, url_for
import mysql.connector

app = Flask(__name__)

# --- Database Connection Setup ---
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="[REDACTED]",  # IMPORTANT: change if different
        database="vehicle_insurance_db"
    )

# --- Home Page Route (Read) ---
@app.route('/')
def index():
    try:
        # Connect to DB and fetch all customers
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Customer")
        customers = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Send the data to our HTML page
        return render_template('index.html', customers_data=customers)
    
    except mysql.connector.Error as err:
        return f"Error connecting to database: {err}"

# --- Add Customer Route (Create) ---
@app.route('/add_customer', methods=['POST'])
def add_customer():
    if request.method == 'POST':
        # 1. Grab data from the HTML form
        cus_id = request.form['cus_id']
        cus_name = request.form['cus_name']
        cus_mobile = request.form['cus_mobile']
        cus_email = request.form['cus_email']
        cus_add = request.form['cus_add']
        cus_pass = "default123"  # A temporary default password for new users

        try:
            # 2. Insert the data into MySQL using parameterized query
            conn = get_db_connection()
            cursor = conn.cursor()
            insert_query = """
                INSERT INTO Customer (cus_id, cus_pass, cus_name, cus_mobile, cus_email, cus_add) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            record_values = (cus_id, cus_pass, cus_name, cus_mobile, cus_email, cus_add)
            cursor.execute(insert_query, record_values)
            conn.commit()  # Commit the transaction to save the data

            cursor.close()
            conn.close()

            # 3. Refresh the page to show the updated table
            return redirect(url_for('index'))

        except mysql.connector.Error as err:
            return f"Error inserting into database: {err}"

if __name__ == '__main__':
    app.run(debug=True)
