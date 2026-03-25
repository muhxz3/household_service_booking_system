from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from datetime import datetime, timedelta
from config import (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, 
                    MAIL_SERVER, MAIL_PORT, MAIL_USERNAME,
                    MAIL_PASSWORD, MAIL_USE_TLS, MAIL_SENDER,
                    SECRET_KEY)
from flask_mail import Mail, Message
import random
import json
from payment_simulator import PaymentSimulator

app = Flask(__name__)
app.secret_key = SECRET_KEY # Required for session management

# --- Flask-Mail Configuration ---
# IMPORTANT: Add MAIL_SERVER, MAIL_PORT, etc. to your config.py file
app.config['MAIL_SERVER'] = MAIL_SERVER
app.config['MAIL_PORT'] = MAIL_PORT
app.config['MAIL_USERNAME'] = MAIL_USERNAME
app.config['MAIL_PASSWORD'] = MAIL_PASSWORD
app.config['MAIL_USE_TLS'] = MAIL_USE_TLS
app.config['MAIL_USE_SSL'] = False

mail = Mail(app)

# --- Database Connection Function ---
def get_db_connection():
    """
    Establishes a connection to the MySQL database.
    Returns the connection object.
    """
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    return conn

# --- Helper Functions ---
def generate_otp():
    """Generates a 6-digit random OTP."""
    return str(random.randint(100000, 999999))

def send_otp_email(email, otp, purpose='registration'):
    """Sends an email with the OTP for a given purpose."""
    if purpose == 'registration':
        subject = 'Your My Eazy Day Registration OTP'
        body = f'Your One-Time Password (OTP) for registration is: {otp}\nThis code is valid for 10 minutes.'
    elif purpose == 'login':
        subject = 'Your My Eazy Day Login OTP'
        body = f'Your One-Time Password (OTP) for logging in is: {otp}\nThis code is valid for 10 minutes.'
    elif purpose == 'password_reset':
        subject = 'Your My Eazy Day Password Reset OTP'
        body = f'Your One-Time Password (OTP) to reset your password is: {otp}\nThis code is valid for 10 minutes.'
    elif purpose == 'email_change':
        subject = 'Verify Your New Email Address'
        body = f'Your One-Time Password (OTP) to verify your new email address is: {otp}\nThis code is valid for 10 minutes.'
    else:
        subject = 'Your My Eazy Day OTP'
        body = f'Your One-Time Password (OTP) is: {otp}\nThis code is valid for 10 minutes.'

    msg = Message(subject,
                  sender=MAIL_SENDER,
                  recipients=[email])
    msg.body = body
    try:
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_notification_email(to_email, subject, body):
    """Sends a general notification email."""
    msg = Message(subject,
                  sender=MAIL_SENDER,
                  recipients=[to_email])
    msg.body = body
    try:
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending notification email: {e}")
        return False

# --- Routes (The Menu) ---
@app.route('/')
@app.route('/index.html')
def home():
    services = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Fetch all services to display on the homepage
        cursor.execute("SELECT service_id, service_name, category, price, service_type FROM service ORDER BY service_type DESC, service_name ASC")
        services = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error fetching services for homepage: {e}")
    return render_template('index.html', services=services)

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT * FROM login WHERE username = %s", (username,))
        account = cursor.fetchone()

        user_email = None
        if account:
            # Admin password cannot be reset this way
            if account['role'] == 'admin':
                flash('Admin password reset is not supported via this form.', 'error')
                cursor.close()
                conn.close()
                return redirect(url_for('forgot_password'))

            role = account['role']
            login_id = account['login_id']

            if role == 'customer':
                cursor.execute("SELECT email FROM customer WHERE login_id = %s", (login_id,))
                user_record = cursor.fetchone()
                if user_record:
                    user_email = user_record['email']
            elif role == 'worker':
                cursor.execute("SELECT email FROM worker WHERE login_id = %s", (login_id,))
                user_record = cursor.fetchone()
                if user_record:
                    user_email = user_record['email']
            
            if user_email and user_email.lower() == email.lower():
                otp = generate_otp()
                expires_at = datetime.now() + timedelta(minutes=10)
                
                cursor.execute("""
                    INSERT INTO otp_store (email, otp, purpose, expires_at)
                    VALUES (%s, %s, 'password_reset', %s)
                    ON DUPLICATE KEY UPDATE otp = VALUES(otp), expires_at = VALUES(expires_at)
                """, (email, otp, expires_at))
                conn.commit()

                if send_otp_email(email, otp, purpose='password_reset'):
                    session['reset_email'] = email
                    flash('An OTP has been sent to your email.', 'success')
                    cursor.close()
                    conn.close()
                    return redirect(url_for('reset_password'))
                else:
                    flash('Failed to send OTP email. Please try again.', 'error')
            else:
                flash('Username and email do not match.', 'error')
        else:
            flash('Username not found.', 'error')

        cursor.close()
        conn.close()
        return redirect(url_for('forgot_password'))

    return render_template('forgot_password.html')

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if 'reset_email' not in session:
        flash('Session expired. Please start the password reset process again.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        email = session['reset_email']
        otp = request.form['otp']
        new_password = request.form['new_password']

        if len(new_password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return redirect(url_for('reset_password'))

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM otp_store WHERE email = %s AND otp = %s AND purpose = 'password_reset'", (email, otp))
        otp_record = cursor.fetchone()

        if otp_record and datetime.now() < otp_record['expires_at']:
            # OTP is valid. Find login_id from email.
            login_id = None
            cursor.execute("SELECT login_id FROM customer WHERE email = %s", (email,))
            user = cursor.fetchone()
            if user:
                login_id = user['login_id']
            else:
                cursor.execute("SELECT login_id FROM worker WHERE email = %s", (email,))
                user = cursor.fetchone()
                if user:
                    login_id = user['login_id']
            
            if login_id:
                cursor.execute("UPDATE login SET password = %s WHERE login_id = %s", (new_password, login_id))
                cursor.execute("DELETE FROM otp_store WHERE email = %s AND purpose = 'password_reset'", (email,))
                conn.commit()
                session.pop('reset_email', None)
                flash('Password has been reset successfully. Please log in.', 'success')
                return redirect(url_for('login_page'))
            else:
                 flash('An unexpected error occurred. Could not find user.', 'error')
        else:
            flash('Invalid or expired OTP.', 'error')
        
        cursor.close()
        conn.close()
        return redirect(url_for('reset_password'))

    return render_template('reset_password.html')

@app.route('/login', methods=['GET', 'POST'])
@app.route('/login/<role>', methods=['GET', 'POST'])
def login_page(role=None):
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Check username and role first
        cursor.execute('SELECT * FROM login WHERE username = %s AND role = %s', (username, role))
        account = cursor.fetchone()

        if account and account['password'] == password:
            # Admin logs in directly without OTP
            if role == 'admin':
                session['loggedin'] = True
                session['id'] = account['login_id']
                session['username'] = account['username']
                session['role'] = account['role']
                cursor.close()
                conn.close()
                return redirect(url_for('admin_dashboard'))
            
            # Customer and Worker require OTP
            login_id = account['login_id']
            user_email = None
            if role == 'customer':
                cursor.execute("SELECT email FROM customer WHERE login_id = %s", (login_id,))
                user_record = cursor.fetchone()
                if user_record:
                    user_email = user_record['email']
            elif role == 'worker':
                cursor.execute("SELECT email FROM worker WHERE login_id = %s", (login_id,))
                user_record = cursor.fetchone()
                if user_record:
                    user_email = user_record['email']

            if user_email:
                otp = generate_otp()
                expires_at = datetime.now() + timedelta(minutes=10)
                
                cursor.execute("""
                    INSERT INTO otp_store (email, otp, purpose, expires_at)
                    VALUES (%s, %s, 'login', %s)
                    ON DUPLICATE KEY UPDATE otp = VALUES(otp), expires_at = VALUES(expires_at)
                """, (user_email, otp, expires_at))
                conn.commit()

                if send_otp_email(user_email, otp, purpose='login'):
                    session['pending_login_email'] = user_email
                    session['pending_login_account'] = account # Store the whole account dict
                    flash('An OTP has been sent to your email for verification.', 'success')
                    cursor.close()
                    conn.close()
                    return redirect(url_for('verify_login'))
                else:
                    flash('Failed to send OTP email. Please try again.', 'error')
            else:
                flash('Could not find user email to send OTP.', 'error')
        else:
            flash('Incorrect username, password, or role!', 'error')
        
        cursor.close()
        conn.close()
        # Redirect back to login page on failure to show flash message
        return redirect(url_for('login_page', role=role))

    return render_template('login.html', role=role)

@app.route('/register', methods=['GET', 'POST'])
def register_page():
    msg = ''
    if request.method == 'POST':
        cust_name = request.form['cust_name']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']
        region = request.form['region']
        username = request.form['username']
        password = request.form['password']

        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return redirect(url_for('register_page'))

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Check if username or email already exists
        cursor.execute("SELECT login_id FROM login WHERE username = %s", (username,))
        if cursor.fetchone():
            flash('Username already exists!', 'error')
            return redirect(url_for('register_page'))
        
        cursor.execute("SELECT * FROM customer WHERE email = %s OR phone = %s", (email, phone))
        if cursor.fetchone():
            flash('Email or phone number is already registered!', 'error')
            return redirect(url_for('register_page'))

        # Store data temporarily for OTP verification
        otp = generate_otp()
        
        user_data = {
            'cust_name': cust_name, 'email': email, 'phone': phone, 
            'address': address, 'region': region, 'username': username, 
            'password': password
        }
        
        expires_at = datetime.now() + timedelta(minutes=10)

        # Use INSERT ... ON DUPLICATE KEY UPDATE to handle resends
        cursor.execute("""
            INSERT INTO pending_registrations (email, user_data, otp, role, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            user_data = VALUES(user_data), otp = VALUES(otp), expires_at = VALUES(expires_at)
        """, (email, json.dumps(user_data), otp, 'customer', expires_at))
        
        conn.commit()
        cursor.close()
        conn.close()

        # Send OTP email
        if send_otp_email(email, otp, purpose='registration'):
            session['pending_email'] = email
            return redirect(url_for('verify_email'))
        else:
            flash('Failed to send OTP email. Please try again.', 'error')
            return redirect(url_for('register_page'))

    return render_template('register.html', msg=msg)

@app.route('/verify_email', methods=['GET', 'POST'])
def verify_email():
    if 'pending_email' not in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        submitted_otp = request.form['otp']
        email = session['pending_email']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT * FROM pending_registrations WHERE email = %s", (email,))
        pending_user = cursor.fetchone()

        if not pending_user:
            flash('Verification session expired. Please register again.', 'error')
            return redirect(url_for('register_page'))

        if pending_user['otp'] == submitted_otp and datetime.now() < pending_user['expires_at']:
            # OTP is correct and not expired
            user_data = json.loads(pending_user['user_data'])
            
            if pending_user['role'] == 'customer':
                # Finalize customer registration
                cursor.execute('INSERT INTO login (username, password, role) VALUES (%s, %s, %s)', 
                               (user_data['username'], user_data['password'], 'customer'))
                login_id = cursor.lastrowid
                cursor.execute('INSERT INTO customer (cust_name, email, phone, address, region, login_id) VALUES (%s, %s, %s, %s, %s, %s)', 
                               (user_data['cust_name'], user_data['email'], user_data['phone'], user_data['address'], user_data['region'], login_id))
            
            elif pending_user['role'] == 'worker':
                # Move worker to pending table for admin approval
                cursor.execute("""
                    INSERT INTO worker_pending (worker_name, phone, email, address, skills, username, password, is_24_7)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_data['worker_name'], user_data['phone'], user_data['email'], user_data['address'], user_data['skills'], user_data['username'], user_data['password'], user_data.get('is_24_7', 0)))

            # Clean up
            cursor.execute("DELETE FROM pending_registrations WHERE email = %s", (email,))
            conn.commit()
            cursor.close()
            conn.close()
            session.pop('pending_email', None)

            if pending_user['role'] == 'customer':
                flash('Verification successful! You can now log in.', 'success')
                return redirect(url_for('login_page', role='customer'))
            else: # Worker
                flash('Verification successful! Your application has been submitted for admin review.', 'success')
                return redirect(url_for('home'))
        else:
            flash('Invalid or expired OTP. Please try again.', 'error')

    return render_template('verify_email.html')

@app.route('/verify_login', methods=['GET', 'POST'])
def verify_login():
    if 'pending_login_email' not in session:
        return redirect(url_for('login_page'))

    if request.method == 'POST':
        submitted_otp = request.form['otp']
        email = session['pending_login_email']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM otp_store WHERE email = %s AND otp = %s AND purpose = 'login'", (email, submitted_otp))
        otp_record = cursor.fetchone()

        if otp_record and datetime.now() < otp_record['expires_at']:
            # OTP is correct, log the user in
            account = session['pending_login_account']
            session['loggedin'] = True
            session['id'] = account['login_id']
            session['username'] = account['username']
            session['role'] = account['role']

            # Clean up
            cursor.execute("DELETE FROM otp_store WHERE email = %s AND purpose = 'login'", (email,))
            conn.commit()
            session.pop('pending_login_email', None)
            session.pop('pending_login_account', None)
            
            cursor.close()
            conn.close()

            if account['role'] == 'customer':
                return redirect(url_for('dashboard'))
            elif account['role'] == 'worker':
                return redirect(url_for('worker_dashboard'))
        else:
            flash('Invalid or expired OTP.', 'error')
            return redirect(url_for('verify_login'))

    return render_template('verify_login.html')

@app.route('/worker/register', methods=['GET', 'POST'])
def worker_register():
    msg = ''
    services = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT service_id, service_name FROM service ORDER BY service_name")
        services = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching services for worker registration: {e}")

    if request.method == 'POST':
        worker_name = request.form['worker_name']
        phone = request.form['phone']
        email = request.form['email']
        address = request.form['address']
        skills = request.form['skills']
        username = request.form['username']
        password = request.form['password']
        is_24_7 = 1 if 'is_24_7' in request.form else 0

        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return redirect(url_for('worker_register'))

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Comprehensive check for existing credentials
        cursor.execute("SELECT login_id FROM login WHERE username = %s", (username,))
        if cursor.fetchone():
            flash('Username already exists!', 'error')
            return redirect(url_for('worker_register'))

        cursor.execute("SELECT username FROM worker_pending WHERE username = %s", (username,))
        if cursor.fetchone():
            flash('Username is already pending approval!', 'error')
            return redirect(url_for('worker_register'))

        cursor.execute("SELECT email FROM worker WHERE email = %s OR phone = %s", (email, phone))
        if cursor.fetchone():
            flash('Email or Phone number is already registered!', 'error')
            return redirect(url_for('worker_register'))

        cursor.execute("SELECT email FROM customer WHERE email = %s OR phone = %s", (email, phone))
        if cursor.fetchone():
            flash('Email or Phone number is already registered!', 'error')
            return redirect(url_for('worker_register'))

        cursor.execute("SELECT email FROM worker_pending WHERE email = %s OR phone = %s", (email, phone))
        if cursor.fetchone():
            flash('Email or Phone number is already pending approval!', 'error')
            return redirect(url_for('worker_register'))

        # Store data temporarily for OTP verification
        otp = generate_otp()
        
        user_data = {
            'worker_name': worker_name, 'phone': phone, 'email': email, 
            'address': address, 'skills': skills, 'username': username, 
            'password': password, 'is_24_7': is_24_7
        }
        
        expires_at = datetime.now() + timedelta(minutes=10)

        cursor.execute("""
            INSERT INTO pending_registrations (email, user_data, otp, role, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            user_data = VALUES(user_data), otp = VALUES(otp), expires_at = VALUES(expires_at)
        """, (email, json.dumps(user_data), otp, 'worker', expires_at))
        
        conn.commit()
        cursor.close()
        conn.close()

        # Send OTP email
        if send_otp_email(email, otp, purpose='registration'):
            session['pending_email'] = email
            return redirect(url_for('verify_email'))
        else:
            flash('Failed to send OTP email. Please try again.', 'error')
            return redirect(url_for('worker_register'))

    return render_template('worker_register.html', services=services)


@app.route('/dashboard')
def dashboard():
    services = []
    try:
        conn = get_db_connection()
        # dictionary=True lets us access columns by name (e.g., service['service_name'])
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT service_id, service_name, price, category, service_type FROM service ORDER BY service_type DESC, service_name ASC")
        services = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error fetching services: {e}") # For debugging
    return render_template('customer_dashboard.html', services=services)

@app.route('/resend_otp')
def resend_otp():
    if 'pending_email' not in session:
        return redirect(url_for('home'))

    email = session['pending_email']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM pending_registrations WHERE email = %s", (email,))
    pending_user = cursor.fetchone()

    if not pending_user:
        flash('Verification session expired. Please register again.', 'error')
        session.pop('pending_email', None)
        return redirect(url_for('register_page'))

    # Generate and send a new OTP
    new_otp = generate_otp()
    expires_at = datetime.now() + timedelta(minutes=10)
    cursor.execute("UPDATE pending_registrations SET otp = %s, expires_at = %s WHERE email = %s", 
                   (new_otp, expires_at, email))
    conn.commit()
    cursor.close()
    conn.close()

    if send_otp_email(email, new_otp, purpose='registration'):
        flash('A new OTP has been sent to your email.', 'success')
    else:
        flash('Failed to resend OTP. Please try again in a moment.', 'error')

    return redirect(url_for('verify_email'))

@app.route('/resend_login_otp')
def resend_login_otp():
    if 'pending_login_email' not in session:
        return redirect(url_for('login_page'))

    email = session['pending_login_email']
    conn = get_db_connection()
    cursor = conn.cursor()

    new_otp = generate_otp()
    expires_at = datetime.now() + timedelta(minutes=10)
    cursor.execute("""
        UPDATE otp_store SET otp = %s, expires_at = %s 
        WHERE email = %s AND purpose = 'login'
    """, (new_otp, expires_at, email))
    conn.commit()
    cursor.close()
    conn.close()

    if send_otp_email(email, new_otp, purpose='login'):
        flash('A new OTP has been sent to your email.', 'success')
    else:
        flash('Failed to resend OTP. Please try again in a moment.', 'error')

    return redirect(url_for('verify_login'))

@app.route('/resend_password_otp')
def resend_password_otp():
    if 'reset_email' not in session:
        return redirect(url_for('forgot_password'))

    email = session['reset_email']
    conn = get_db_connection()
    cursor = conn.cursor()

    new_otp = generate_otp()
    expires_at = datetime.now() + timedelta(minutes=10)
    cursor.execute("""
        UPDATE otp_store SET otp = %s, expires_at = %s 
        WHERE email = %s AND purpose = 'password_reset'
    """, (new_otp, expires_at, email))
    conn.commit()
    cursor.close()
    conn.close()

    if send_otp_email(email, new_otp, purpose='password_reset'):
        flash('A new OTP has been sent to your email.', 'success')
    else:
        flash('Failed to resend OTP. Please try again.', 'error')

    return redirect(url_for('reset_password'))

@app.route('/worker/dashboard')
def worker_dashboard():
    if 'loggedin' not in session or session['role'] != 'worker':
        return redirect(url_for('login_page'))

    login_id = session['id']
    jobs = []
    worker_rating = 0

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Find the worker_id associated with this login
    cursor.execute("SELECT worker_id FROM worker WHERE login_id = %s", (login_id,))
    worker = cursor.fetchone()

    if worker:
        worker_id = worker['worker_id']
        # Fetch jobs assigned to this worker
        cursor.execute("""
            SELECT b.booking_id, c.cust_name, s.service_name, s.service_type, b.booking_date, b.booking_time, b.booking_status, p.payment_status, p.amount
            FROM booking b
            JOIN customer c ON b.customer_id = c.customer_id
            JOIN service s ON b.service_id = s.service_id
            LEFT JOIN payment p ON b.booking_id = p.booking_id
            WHERE b.worker_id = %s
            ORDER BY b.booking_date ASC
        """, (worker_id,))
        jobs = cursor.fetchall()
        
        # Fetch rating from worker table
        cursor.execute("SELECT rating FROM worker WHERE worker_id = %s", (worker_id,))
        result = cursor.fetchone()
        if result and result['rating']:
            worker_rating = result['rating']

    cursor.execute("SELECT service_id, service_name, price, category, service_type FROM service ORDER BY service_type DESC, service_name ASC")
    services = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('worker_dashboard.html', jobs=jobs, services=services, worker_rating=worker_rating)

@app.route('/worker/assigned_jobs')
def worker_assigned_jobs():
    return redirect(url_for('worker_dashboard'))

@app.route('/worker/edit_booking/<int:booking_id>', methods=['GET', 'POST'])
def worker_edit_booking(booking_id):
    if 'loggedin' not in session or session['role'] != 'worker':
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Authorization: Check if this booking belongs to the logged-in worker
    cursor.execute("SELECT worker_id FROM worker WHERE login_id = %s", (session['id'],))
    worker = cursor.fetchone()
    if not worker:
        flash("Worker profile not found.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for('worker_dashboard'))
    
    worker_id = worker['worker_id']

    cursor.execute("SELECT * FROM booking WHERE booking_id = %s AND worker_id = %s", (booking_id, worker_id))
    booking = cursor.fetchone()

    if not booking:
        flash("Booking not found or you are not authorized to edit it.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for('worker_dashboard'))

    if request.method == 'POST':
        status = request.form['status']
        
        # Logic Fix: If status is already the same, don't update and don't error
        if booking['booking_status'] == status:
            flash(f'Status is already {status.title()}.', 'info')
            cursor.close()
            conn.close()
            return redirect(url_for('worker_dashboard'))

        cursor.execute("UPDATE booking SET booking_status = %s WHERE booking_id = %s AND worker_id = %s",
                       (status, booking_id, worker_id))

        if cursor.rowcount > 0:
            if status == 'completed':
                cursor.execute("SELECT payment_method FROM payment WHERE booking_id = %s", (booking_id,))
                payment = cursor.fetchone()
                if payment and payment['payment_method'] == 'cash':
                    cursor.execute("UPDATE payment SET payment_status = 'completed' WHERE booking_id = %s", (booking_id,))
                    flash('Job and cash payment marked as completed.', 'info')
                
                # Notify Customer of completion
                cursor.execute("SELECT c.email, c.cust_name, s.service_name FROM booking b JOIN customer c ON b.customer_id = c.customer_id JOIN service s ON b.service_id = s.service_id WHERE b.booking_id = %s", (booking_id,))
                details = cursor.fetchone()
                if details:
                    send_notification_email(details['email'], f"Service Completed - Booking #{booking_id}", f"Hello {details['cust_name']},\n\nYour service '{details['service_name']}' has been marked as completed by the worker.\n\nWe hope you are satisfied with our work. Please log in to your dashboard to provide feedback.\n\nThank you!")
                else:
                    flash('Job marked as completed.', 'info')
            elif status == 'cancelled':
                # Attempt to update payment status, ignore if schema doesn't support it (avoids crash)
                try:
                    cursor.execute("UPDATE payment SET payment_status = 'cancelled' WHERE booking_id = %s", (booking_id,))
                except mysql.connector.Error:
                    pass # Payment status stays as is if 'cancelled' isn't in ENUM
                flash(f'Job #{booking_id} has been cancelled.', 'info')
            else:
                flash(f'Job #{booking_id} status updated to {status.replace("_", " ")}.', 'info')
            conn.commit()
        else:
            flash('Could not update status.', 'error')
        
        cursor.close()
        conn.close()
        return redirect(url_for('worker_dashboard'))

    # GET request: Fetch full details for the edit page
    cursor.execute("""
        SELECT b.booking_id, b.booking_date, b.booking_status,
               c.cust_name, s.service_name
        FROM booking b
        JOIN customer c ON b.customer_id = c.customer_id
        JOIN service s ON b.service_id = s.service_id
        WHERE b.booking_id = %s
    """, (booking_id,))
    booking_details = cursor.fetchone()

    cursor.close()
    conn.close()
    return render_template('worker_edit_booking.html', booking=booking_details)

@app.route('/booking/details/<int:booking_id>')
def booking_details(booking_id):
    if 'loggedin' not in session:
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch all details for the booking
    cursor.execute("""
        SELECT 
            b.booking_id, b.booking_date, b.booking_time, b.booking_status,
            b.customer_id, b.worker_id,
            s.service_name, p.amount,
            c.cust_name, c.phone as cust_phone, c.address as cust_address,
            w.worker_name
        FROM booking b
        JOIN customer c ON b.customer_id = c.customer_id
        JOIN service s ON b.service_id = s.service_id
        JOIN payment p ON b.booking_id = p.booking_id
        LEFT JOIN worker w ON b.worker_id = w.worker_id
        WHERE b.booking_id = %s
    """, (booking_id,))
    booking = cursor.fetchone()

    # Authorization check to ensure users can only see their own/relevant bookings
    authorized = False
    if booking:
        if session['role'] == 'admin':
            authorized = True
        elif session['role'] == 'customer':
            cursor.execute("SELECT customer_id FROM customer WHERE login_id = %s", (session['id'],))
            user = cursor.fetchone()
            if user and user['customer_id'] == booking['customer_id']:
                authorized = True
        elif session['role'] == 'worker':
            cursor.execute("SELECT worker_id FROM worker WHERE login_id = %s", (session['id'],))
            user = cursor.fetchone()
            if user and user['worker_id'] == booking['worker_id']:
                authorized = True
    
    services = []
    if authorized:
        # Fetch all services to display on the page
        cursor.execute("SELECT service_id, service_name, price, category FROM service")
        services = cursor.fetchall()

    cursor.close()
    conn.close()

    if not authorized:
        return "Booking not found or you are not authorized to view it.", 404

    return render_template('booking_details.html', booking=booking, services=services)

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login_page'))

    bookings = []
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    # Fetch all bookings for the admin view
    cursor.execute("""
        SELECT b.booking_id, c.cust_name, w.worker_name, s.service_name, s.service_type, b.booking_date, b.booking_status
        FROM booking b
        JOIN customer c ON b.customer_id = c.customer_id
        JOIN service s ON b.service_id = s.service_id
        LEFT JOIN worker w ON b.worker_id = w.worker_id
        ORDER BY b.booking_date DESC
    """)
    bookings = cursor.fetchall()
    cursor.execute("SELECT service_id, service_name, price, category, service_type FROM service")
    services = cursor.fetchall()

    # Fetch pending worker registrations
    cursor.execute("SELECT * FROM worker_pending ORDER BY registration_date ASC")
    pending_workers = cursor.fetchall()

    # Fetch best performing worker
    cursor.execute("SELECT * FROM worker ORDER BY rating DESC LIMIT 1")
    best_worker = cursor.fetchone()

    cursor.close()
    conn.close()
    return render_template('admin_dashboard.html', bookings=bookings, services=services, pending_workers=pending_workers, best_worker=best_worker)

@app.route('/admin/edit_booking/<int:booking_id>', methods=['GET', 'POST'])
def edit_booking(booking_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        worker_id = request.form['worker_id']
        status = request.form['status'].strip()
        # Handle "None" selection for worker
        if worker_id == 'none':
            worker_id = None
            
        cursor.execute("UPDATE booking SET worker_id = %s, booking_status = %s WHERE booking_id = %s", 
                       (worker_id, status, booking_id))
        conn.commit()

        # Send Notification to Customer if status is completed
        if status == 'completed':
            cursor.execute("SELECT c.email, c.cust_name, s.service_name FROM booking b JOIN customer c ON b.customer_id = c.customer_id JOIN service s ON b.service_id = s.service_id WHERE b.booking_id = %s", (booking_id,))
            details = cursor.fetchone()
            if details:
                send_notification_email(
                    details['email'],
                    f"Service Completed - Booking #{booking_id}",
                    f"Hello {details['cust_name']},\n\nYour service '{details['service_name']}' has been marked as completed by the admin.\n\nWe hope you are satisfied with our work. Please log in to your dashboard to provide feedback.\n\nThank you!"
                )

        # Send Notification to Worker if assigned
        if worker_id and status != 'completed':
            cursor.execute("SELECT email, worker_name FROM worker WHERE worker_id = %s", (worker_id,))
            worker_data = cursor.fetchone()
            
            cursor.execute("SELECT s.service_name, b.booking_date, b.booking_time FROM booking b JOIN service s ON b.service_id = s.service_id WHERE b.booking_id = %s", (booking_id,))
            job_details = cursor.fetchone()

            if worker_data and job_details:
                send_notification_email(
                    worker_data['email'],
                    f"Job Assignment Update - Booking #{booking_id}",
                    f"Hello {worker_data['worker_name']},\n\nYou have been assigned to booking #{booking_id}.\nService: {job_details['service_name']}\nDate: {job_details['booking_date']}\nTime: {job_details['booking_time']}\n\nPlease check your dashboard for details."
                )

        cursor.close()
        conn.close()
        return redirect(url_for('admin_dashboard'))

    # Fetch booking details
    cursor.execute("""
        SELECT b.booking_id, b.booking_date, b.booking_status, b.worker_id,
               c.cust_name, s.service_name
        FROM booking b
        JOIN customer c ON b.customer_id = c.customer_id
        JOIN service s ON b.service_id = s.service_id
        WHERE b.booking_id = %s
    """, (booking_id,))
    booking = cursor.fetchone()

    # Fetch all workers for the dropdown
    cursor.execute("SELECT worker_id, worker_name, rating FROM worker")
    workers = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('edit_booking.html', booking=booking, workers=workers)

@app.route('/admin/delete_booking/<int:booking_id>')
def delete_booking(booking_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Delete related records to satisfy foreign key constraints
        cursor.execute("DELETE FROM payment WHERE booking_id = %s", (booking_id,))
        cursor.execute("DELETE FROM feedback WHERE booking_id = %s", (booking_id,))
        cursor.execute("DELETE FROM booking WHERE booking_id = %s", (booking_id,))
        conn.commit()
    except Exception as e:
        print(f"Error deleting booking: {e}")

    cursor.close()
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/book/<int:service_id>')
def booking_form(service_id):
    if 'loggedin' not in session:
        return redirect(url_for('login_page'))

    if session.get('role') == 'worker':
        return redirect(url_for('worker_dashboard'))

    now = datetime.now()
    service = None
    workers = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT service_id, service_name, category, service_type FROM service WHERE service_id = %s", (service_id,))
        service = cursor.fetchone()
        
        if service:

            # Fetch all workers including 24/7 status
            cursor.execute("SELECT worker_id, worker_name, rating as avg_rating, is_24_7 FROM worker ORDER BY rating DESC")
            workers = cursor.fetchall()
            
            # Check workload availability
            cursor.execute("""
                SELECT b.worker_id, COUNT(*) as total, 
                       SUM(CASE WHEN s.service_type = 'premium' THEN 1 ELSE 0 END) as premium_count
                FROM booking b 
                JOIN service s ON b.service_id = s.service_id
                WHERE b.booking_status = 'pending'
                GROUP BY b.worker_id
            """)
            workloads = {row['worker_id']: row for row in cursor.fetchall()}

            for worker in workers:
                load = workloads.get(worker['worker_id'], {'total': 0, 'premium_count': 0})
                current_total = load['total']
                current_premium = load['premium_count'] if load['premium_count'] else 0
                
                worker['is_available'] = current_total < 4 and not (service['service_type'] == 'premium' and current_premium >= 2)
                worker['status_msg'] = 'High Workload' if current_total >= 4 else ('Premium Limit Reached' if not worker['is_available'] else '')

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error fetching service details: {e}")

    return render_template('booking_form.html', service=service, workers=workers, now=now)

@app.route('/book_service', methods=['POST'])
def book_service():
    if 'loggedin' not in session:
        return redirect(url_for('login_page'))

    if session.get('role') == 'worker':
        return redirect(url_for('worker_dashboard'))

    service_id = request.form['service_id']
    login_id = session['id']
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 1. Fetch Service Details (Moved up to check category/type for worker assignment)
    cursor.execute("SELECT * FROM service WHERE service_id = %s", (service_id,))
    service = cursor.fetchone()

    if not service:
        cursor.close()
        conn.close()
        flash('Service not found.', 'error')
        return redirect(url_for('home'))

    # Check Urgency Mode (Validated against service type)
    is_urgent = False
    urgency_mode = request.form.get('urgency_mode')
    if urgency_mode == '1' and service.get('service_type') == 'premium':
        is_urgent = True
        
    urgency_multiplier = 1.5 if is_urgent else 1.0

    # Get the selected worker_id (if any)
    worker_id = request.form.get('worker_id')
    
    # Override for Urgency Mode: Force random assignment
    if is_urgent:
        worker_id = 'none'
    
    # 1.5. Validate Specific Worker Availability (Re-check workload on submission)
    if worker_id and worker_id != 'none':
        cursor.execute("""
            SELECT COUNT(*) as total, 
                   SUM(CASE WHEN s.service_type = 'premium' THEN 1 ELSE 0 END) as premium_count
            FROM booking b 
            JOIN service s ON b.service_id = s.service_id
            WHERE b.worker_id = %s AND b.booking_status = 'pending'
        """, (worker_id,))
        stats = cursor.fetchone()
        
        current_total = stats['total']
        current_premium = stats['premium_count'] if stats['premium_count'] else 0
        
        if current_total >= 4 or (service['service_type'] == 'premium' and current_premium >= 2):
            flash('The selected worker has just reached their workload limit. Please choose another or select "No Preference".', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('booking_form', service_id=service_id))

    if worker_id == 'none' or not worker_id:
        # Randomly assign a worker who is NOT overloaded
        query = """
            SELECT w.worker_id, w.is_24_7, COUNT(b.booking_id) as total,
                   SUM(CASE WHEN s.service_type = 'premium' AND b.booking_status = 'pending' THEN 1 ELSE 0 END) as premium_count
            FROM worker w
            LEFT JOIN booking b ON w.worker_id = b.worker_id AND b.booking_status = 'pending'
            LEFT JOIN service s ON b.service_id = s.service_id
            WHERE 1=1
        """
        if is_urgent:
            query += " AND w.is_24_7 = 1 "
            
        query += " GROUP BY w.worker_id"
        cursor.execute(query)
        all_stats = cursor.fetchall()
        
        # Filter available workers based on constraints
        candidates = []
        for stat in all_stats:
            p_count = stat['premium_count'] if stat['premium_count'] else 0
            if stat['total'] < 4:
                if service['service_type'] != 'premium' or p_count < 2:
                    candidates.append(stat['worker_id'])
        
        if candidates:
            worker_id = random.choice(candidates)
        else:
            msg = 'No 24/7 workers are currently available due to high demand.' if is_urgent else 'All workers are currently fully booked. Please try again later.'
            flash(msg, 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('booking_form', service_id=service_id))

    # 2. Fetch Customer Details
    cursor.execute("SELECT customer_id, region, email, cust_name FROM customer WHERE login_id = %s", (login_id,))
    customer = cursor.fetchone()

    if customer and service:
        if is_urgent:
            booking_date = datetime.now().date()
            booking_time = datetime.now().replace(microsecond=0).time()
        elif service.get('service_type') == 'premium':
            booking_date = request.form.get('booking_date')
            booking_time = request.form.get('booking_time')

            if not booking_date or not booking_time:
                flash('Please select a valid date and time for premium services.', 'error')
                cursor.close()
                conn.close()
                return redirect(url_for('booking_form', service_id=service_id))
        else:
            booking_date = datetime.now().date()
            booking_time = datetime.now().replace(microsecond=0).time()

        customer_id = customer['customer_id']
        
        # Schema only supports pending/completed/cancelled
        initial_status = 'pending'
        
        # Determine payment method based on urgency
        if is_urgent:
            payment_method = 'online'
        else:
            payment_method = request.form.get('payment_method', 'cash')

        cursor.execute("INSERT INTO booking (booking_date, booking_time, booking_status, customer_id, service_id, worker_id) VALUES (%s, %s, %s, %s, %s, %s)", 
                       (booking_date, booking_time, initial_status, customer_id, service_id, worker_id))
        booking_id = cursor.lastrowid

        # Handle Payment Entry
        amount = float(service['price']) * urgency_multiplier
        
        # Add delivery charge if applicable
        delivery_charge = 0
        if service['category'] == 'pickup':
            pickup_distance = float(request.form.get('pickup_distance', 0))
            delivery_charge += max(0, (pickup_distance - 5) * 20)
        
        total_amount = amount + delivery_charge

        # Insert into payment table (status is pending initially)
        cursor.execute("INSERT INTO payment (amount, payment_status, payment_method, booking_id) VALUES (%s, 'pending', %s, %s)",
                       (total_amount, payment_method, booking_id))
        
        conn.commit()
        
        # Send Booking Confirmation Email (for Cash payments or initial booking state)
        if customer.get('email'):
            send_notification_email(customer['email'], f"Booking Confirmed - #{booking_id}", f"Hello {customer['cust_name']},\n\nYour booking for {service['service_name']} has been placed successfully.\nBooking ID: {booking_id}\nDate: {booking_date}\nTime: {booking_time}\n\nThank you for choosing My Eazy Day.")

        # Send Notification to Worker
        if worker_id:
            cursor.execute("SELECT email, worker_name FROM worker WHERE worker_id = %s", (worker_id,))
            worker_data = cursor.fetchone()
            if worker_data:
                 send_notification_email(
                    worker_data['email'],
                    f"New Job Assigned - Booking #{booking_id}",
                    f"Hello {worker_data['worker_name']},\n\nYou have been assigned a new job.\nService: {service['service_name']}\nDate: {booking_date}\nTime: {booking_time}\n\nPlease check your dashboard for details."
                )

        # If online payment is selected, redirect to payment page
        if payment_method == 'online':
            cursor.close()
            conn.close()
            return redirect(url_for('payment_page', booking_id=booking_id))

    cursor.close()
    conn.close()
    return redirect(url_for('my_bookings'))

@app.route('/payment/<int:booking_id>', methods=['GET', 'POST'])
def payment_page(booking_id):
    if 'loggedin' not in session:
        return redirect(url_for('login_page'))
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        # Simulate successful payment
        cursor.execute("UPDATE payment SET payment_status = 'completed' WHERE booking_id = %s", (booking_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('my_bookings'))

    # Fetch booking details for the payment page
    cursor.execute("""
        SELECT b.booking_id, s.service_name, p.amount
        FROM booking b
        JOIN service s ON b.service_id = s.service_id
        JOIN payment p ON b.booking_id = p.booking_id
        WHERE b.booking_id = %s
    """, (booking_id,))
    booking = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    # Redirect to payment simulation instead of showing payment.html
    return redirect(url_for('payment_simulation', booking_id=booking_id))

@app.route('/payment_simulation/<int:booking_id>')
def payment_simulation(booking_id):
    if 'loggedin' not in session:
        return redirect(url_for('login_page'))
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch booking details for the simulation page
    cursor.execute("""
        SELECT b.booking_id, s.service_name, p.amount
        FROM booking b
        JOIN service s ON b.service_id = s.service_id
        JOIN payment p ON b.booking_id = p.booking_id
        WHERE b.booking_id = %s
    """, (booking_id,))
    booking = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if not booking:
        flash('Booking not found', 'error')
        return redirect(url_for('my_bookings'))
    
    return render_template('payment_simulation.html', 
                         booking_id=booking['booking_id'],
                         service_name=booking['service_name'],
                         amount=booking['amount'])

@app.route('/process_payment_simulation', methods=['POST'])
def process_payment_simulation():
    if 'loggedin' not in session:
        return redirect(url_for('login_page'))
        
    booking_id = int(request.form['booking_id'])
    scenario = request.form['scenario']
    amount = float(request.form['amount'])
    
    # Use the payment simulator
    result = PaymentSimulator.simulate_payment_scenario(scenario, booking_id, amount)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        if result['status'] == 'completed':
            # Payment successful
            cursor.execute("UPDATE payment SET payment_status = 'completed' WHERE booking_id = %s", (booking_id,))
            # Schema limitation: booking_status stays 'pending' until worker completes it
            conn.commit()
            
            # Notify Customer of successful payment
            cursor.execute("SELECT c.email, c.cust_name, s.service_name FROM booking b JOIN customer c ON b.customer_id = c.customer_id JOIN service s ON b.service_id = s.service_id WHERE b.booking_id = %s", (booking_id,))
            details = cursor.fetchone()
            if details:
                send_notification_email(details['email'], f"Payment Successful - Booking #{booking_id}", f"Hello {details['cust_name']},\n\nWe have received your payment of ₹{amount} for booking #{booking_id} ({details['service_name']}).\n\nYour booking is now confirmed.")

            return render_template('payment_result.html', status='success', message=result['message'], booking_id=booking_id)
            
        elif result['status'] == 'failed' or result['status'] == 'timeout':
            # Payment failed - Delete booking as per requirement
            cursor.execute("DELETE FROM payment WHERE booking_id = %s", (booking_id,))
            cursor.execute("DELETE FROM booking WHERE booking_id = %s", (booking_id,))
            conn.commit()
            return render_template('payment_result.html', status='failed', message=result['message'])
            
        elif result['status'] == 'processing':
            # Payment processing - stays in pending state (Map 'processing' to 'pending')
            cursor.execute("UPDATE payment SET payment_status = 'pending' WHERE booking_id = %s", (booking_id,))
            conn.commit()
            return render_template('payment_result.html', status='info', message=result['message'], booking_id=booking_id)
            
        else:
            return render_template('payment_result.html', status='failed', message='Invalid payment scenario')
            
    except Exception as e:
        print(f"Payment simulation error: {e}")
        return render_template('payment_result.html', status='failed', message='An error occurred during payment processing.')
    finally:
        cursor.close()
        conn.close()

@app.route('/my_bookings')
def my_bookings():
    if 'loggedin' not in session:
        return redirect(url_for('login_page'))

    login_id = session['id']
    bookings = []

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get customer_id and then their bookings
    cursor.execute("SELECT customer_id FROM customer WHERE login_id = %s", (login_id,))
    customer = cursor.fetchone()

    if customer:
        customer_id = customer['customer_id']
        cursor.execute("""
            SELECT b.booking_id, s.service_name, b.booking_date, b.booking_time, b.booking_status, w.worker_name,
                   p.payment_status, p.payment_method, p.amount,
                   f.rating
            FROM booking b
            JOIN service s ON b.service_id = s.service_id
            LEFT JOIN worker w ON b.worker_id = w.worker_id
            LEFT JOIN payment p ON b.booking_id = p.booking_id
            LEFT JOIN feedback f ON b.booking_id = f.booking_id
            WHERE b.customer_id = %s
            ORDER BY b.booking_date DESC
        """, (customer_id,))
        bookings = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('my_bookings.html', bookings=bookings)

@app.route('/customer/profile')
def customer_profile():
    if 'loggedin' not in session or session['role'] != 'customer':
        return redirect(url_for('login_page'))
    
    login_id = session['id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT c.*, l.username FROM customer c JOIN login l ON c.login_id = l.login_id WHERE l.login_id = %s", (login_id,))
    customer = cursor.fetchone()
    
    cursor.close()
    conn.close()

    # Mask confidential info for display
    if customer:
        # Mask Email
        if '@' in customer['email']:
            parts = customer['email'].split('@')
            if len(parts[0]) > 2:
                customer['email'] = parts[0][:2] + "****@" + parts[1]
            else:
                customer['email'] = "****@" + parts[1]
        
        # Mask Phone
        if len(customer['phone']) > 4:
            customer['phone'] = "******" + customer['phone'][-4:]

    return render_template('customer_profile.html', customer=customer)

@app.route('/customer/profile/edit', methods=['GET', 'POST'])
def customer_edit_profile():
    if 'loggedin' not in session or session['role'] != 'customer':
        return redirect(url_for('login_page'))
    
    login_id = session['id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        cust_name = request.form['cust_name']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']
        region = request.form['region']
        username = request.form['username']
        new_password = request.form['password']

        if new_password and len(new_password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return redirect(url_for('customer_edit_profile'))

        # Check for uniqueness conflicts (excluding current user)
        cursor.execute("SELECT customer_id FROM customer WHERE phone = %s AND login_id != %s", (phone, login_id))
        if cursor.fetchone():
            flash('Phone number is already associated with another account.', 'error')
            return redirect(url_for('customer_edit_profile'))

        cursor.execute("SELECT login_id FROM login WHERE username = %s AND login_id != %s", (username, login_id))
        if cursor.fetchone():
            flash('Username is already taken.', 'error')
            return redirect(url_for('customer_edit_profile'))

        # Get current email to check for changes
        cursor.execute("SELECT email FROM customer WHERE login_id = %s", (login_id,))
        current_email = cursor.fetchone()['email']

        if email != current_email:
            # Email has changed, verify uniqueness
            cursor.execute("SELECT email FROM customer WHERE email = %s", (email,))
            if cursor.fetchone():
                flash('This email is already registered.', 'error')
                return redirect(url_for('customer_edit_profile'))
            
            cursor.execute("SELECT email FROM worker WHERE email = %s", (email,))
            if cursor.fetchone():
                flash('This email is already registered.', 'error')
                return redirect(url_for('customer_edit_profile'))

            # Store pending data in session and initiate OTP
            session['pending_profile_update'] = {
                'cust_name': cust_name, 'email': email, 'phone': phone,
                'address': address, 'region': region, 'username': username,
                'password': new_password
            }
            
            otp = generate_otp()
            expires_at = datetime.now() + timedelta(minutes=10)
            
            cursor.execute("""
                INSERT INTO otp_store (email, otp, purpose, expires_at)
                VALUES (%s, %s, 'login', %s)
                ON DUPLICATE KEY UPDATE otp = VALUES(otp), expires_at = VALUES(expires_at)
            """, (email, otp, expires_at))
            conn.commit()

            if send_otp_email(email, otp, purpose='email_change'):
                flash('An OTP has been sent to your new email address.', 'success')
                cursor.close()
                conn.close()
                return redirect(url_for('verify_profile_email_change'))
            else:
                flash('Failed to send OTP. Please try again.', 'error')
                return redirect(url_for('customer_edit_profile'))

        else:
            # Standard update (no email change)
            cursor.execute("UPDATE customer SET cust_name=%s, phone=%s, address=%s, region=%s WHERE login_id=%s",
                        (cust_name, phone, address, region, login_id))
            
            if new_password:
                cursor.execute("UPDATE login SET username=%s, password=%s WHERE login_id=%s", (username, new_password, login_id))
            else:
                cursor.execute("UPDATE login SET username=%s WHERE login_id=%s", (username, login_id))
                
            conn.commit()
            session['username'] = username
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('customer_profile'))

    cursor.execute("SELECT c.*, l.username FROM customer c JOIN login l ON c.login_id = l.login_id WHERE l.login_id = %s", (login_id,))
    customer = cursor.fetchone()
    
    cursor.close()
    conn.close()
    return render_template('customer_edit_profile.html', customer=customer)

@app.route('/verify_profile_email_change', methods=['GET', 'POST'])
def verify_profile_email_change():
    if 'loggedin' not in session or 'pending_profile_update' not in session:
        return redirect(url_for('customer_edit_profile'))

    new_data = session['pending_profile_update']
    new_email = new_data['email']

    if request.method == 'POST':
        otp = request.form['otp']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM otp_store WHERE email = %s AND otp = %s AND purpose = 'login'", (new_email, otp))
        otp_record = cursor.fetchone()

        if otp_record and datetime.now() < otp_record['expires_at']:
            login_id = session['id']
            
            # Apply all updates
            cursor.execute("UPDATE customer SET cust_name=%s, email=%s, phone=%s, address=%s, region=%s WHERE login_id=%s",
                        (new_data['cust_name'], new_data['email'], new_data['phone'], new_data['address'], new_data['region'], login_id))
            
            if new_data['password']:
                cursor.execute("UPDATE login SET username=%s, password=%s WHERE login_id=%s", (new_data['username'], new_data['password'], login_id))
            else:
                cursor.execute("UPDATE login SET username=%s WHERE login_id=%s", (new_data['username'], login_id))

            # Cleanup
            cursor.execute("DELETE FROM otp_store WHERE email = %s AND purpose = 'login'", (new_email,))
            conn.commit()
            
            session['username'] = new_data['username']
            session.pop('pending_profile_update', None)
            
            flash('Profile and email updated successfully!', 'success')
            cursor.close()
            conn.close()
            return redirect(url_for('customer_profile'))
        else:
            flash('Invalid or expired OTP.', 'error')
            cursor.close()
            conn.close()

    return render_template('verify_email_change.html', email=new_email)

@app.route('/resend_profile_email_otp')
def resend_profile_email_otp():
    if 'pending_profile_update' in session:
        email = session['pending_profile_update']['email']
        otp = generate_otp()
        # Re-use existing OTP logic or direct update
        # For simplicity, redirecting to edit logic which regenerates if posted, 
        # but here we need to regenerate manually.
        conn = get_db_connection()
        cursor = conn.cursor()
        expires_at = datetime.now() + timedelta(minutes=10)
        cursor.execute("UPDATE otp_store SET otp = %s, expires_at = %s WHERE email = %s AND purpose = 'login'", 
                       (otp, expires_at, email))
        conn.commit()
        cursor.close()
        conn.close()
        
        send_otp_email(email, otp, purpose='email_change')
        flash('A new OTP has been sent.', 'success')
        return redirect(url_for('verify_profile_email_change'))
    return redirect(url_for('customer_edit_profile'))

@app.route('/feedback/<int:booking_id>', methods=['GET', 'POST'])
def feedback(booking_id):
    if 'loggedin' not in session:
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Check if feedback already exists for this booking
    cursor.execute("SELECT feedback_id FROM feedback WHERE booking_id = %s", (booking_id,))
    existing_feedback = cursor.fetchone()

    if existing_feedback:
        cursor.close()
        conn.close()
        return redirect(url_for('my_bookings'))
        
    if request.method == 'POST':
        rating = request.form['rating']
        comments = request.form['comments']
        
        cursor.execute("INSERT INTO feedback (booking_id, rating, comments) VALUES (%s, %s, %s)", 
                        (booking_id, rating, comments))
        
        # Update Worker Rating and Notify
        cursor.execute("""
            SELECT w.worker_id, w.email, w.worker_name 
            FROM booking b 
            JOIN worker w ON b.worker_id = w.worker_id 
            WHERE b.booking_id = %s
        """, (booking_id,))
        worker_details = cursor.fetchone()

        if worker_details:
            worker_id = worker_details['worker_id']
            cursor.execute("""
                SELECT AVG(f.rating) as avg_rating 
                FROM feedback f 
                JOIN booking b ON f.booking_id = b.booking_id 
                WHERE b.worker_id = %s
            """, (worker_id,))
            avg_result = cursor.fetchone()
            new_rating = float(avg_result['avg_rating']) if avg_result and avg_result['avg_rating'] else 0.0
            
            cursor.execute("UPDATE worker SET rating = %s WHERE worker_id = %s", (new_rating, worker_id))
            
            send_notification_email(worker_details['email'], f"New Feedback Received - Booking #{booking_id}", f"Hello {worker_details['worker_name']},\n\nYou have received a new rating of {rating}/5 for booking #{booking_id}.\n\nComment: {comments}")

        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('my_bookings'))
        
    cursor.close()
    conn.close()
    return render_template('feedback.html', booking_id=booking_id)

@app.route('/admin/add_worker', methods=['GET', 'POST'])
def add_worker():
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login_page'))

    if request.method == 'POST':
        worker_name = request.form['worker_name']
        phone = request.form['phone']
        email = request.form['email']
        address = request.form['address']
        skills = request.form['skills']
        username = request.form['username']
        password = request.form['password']
        is_24_7 = 1 if 'is_24_7' in request.form else 0

        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return redirect(url_for('add_worker'))

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Create Login
        cursor.execute("INSERT INTO login (username, password, role) VALUES (%s, %s, 'worker')", (username, password))
        login_id = cursor.lastrowid

        # 2. Create Worker with 24/7 preference
        cursor.execute("INSERT INTO worker (worker_name, phone, email, address, skills, login_id, is_24_7) VALUES (%s, %s, %s, %s, %s, %s, %s)", 
                       (worker_name, phone, email, address, skills, login_id, is_24_7))
        
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('manage_workers'))

    return render_template('add_worker.html')

@app.route('/admin/accept_worker/<int:pending_id>', methods=['POST'])
def accept_worker(pending_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1. Get pending worker data
    cursor.execute("SELECT * FROM worker_pending WHERE pending_id = %s", (pending_id,))
    pending_worker = cursor.fetchone()

    if pending_worker:
        # --- Skills Processing ---
        skills_display_str = pending_worker['skills']

        # 2. Create Login entry
        cursor.execute("INSERT INTO login (username, password, role) VALUES (%s, %s, 'worker')", 
                       (pending_worker['username'], pending_worker['password']))
        login_id = cursor.lastrowid

        # 3. Create Worker entry
        cursor.execute("INSERT INTO worker (worker_name, phone, email, address, skills, login_id, is_24_7) VALUES (%s, %s, %s, %s, %s, %s, %s)", 
                       (pending_worker['worker_name'], pending_worker['phone'], pending_worker['email'], pending_worker['address'], skills_display_str, login_id, pending_worker['is_24_7']))
        worker_id = cursor.lastrowid

        # 5. Delete from pending table
        cursor.execute("DELETE FROM worker_pending WHERE pending_id = %s", (pending_id,))
        
        conn.commit()

    cursor.close()
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject_worker/<int:pending_id>', methods=['POST'])
def reject_worker(pending_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login_page'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Delete from pending table
    cursor.execute("DELETE FROM worker_pending WHERE pending_id = %s", (pending_id,))
    conn.commit()
        
    cursor.close()
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_worker/<int:worker_id>', methods=['GET', 'POST'])
def edit_worker(worker_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        worker_name = request.form['worker_name']
        phone = request.form['phone']
        email = request.form['email']
        address = request.form['address']
        skills = request.form['skills']
        cursor.execute("UPDATE worker SET worker_name=%s, phone=%s, email=%s, address=%s, skills=%s WHERE worker_id=%s", 
                       (worker_name, phone, email, address, skills, worker_id))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('manage_workers'))

    cursor.execute("SELECT * FROM worker WHERE worker_id = %s", (worker_id,))
    worker = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template('edit_worker.html', worker=worker)

@app.route('/admin/delete_worker/<int:worker_id>')
def delete_worker(worker_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login_page'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Get login_id to delete login record too
        cursor.execute("SELECT login_id FROM worker WHERE worker_id = %s", (worker_id,))
        result = cursor.fetchone()
        
        # Unassign the worker from any existing bookings to satisfy Foreign Key constraints
        cursor.execute("UPDATE booking SET worker_id = NULL WHERE worker_id = %s", (worker_id,))
        
        cursor.execute("DELETE FROM provides WHERE worker_id = %s", (worker_id,))
        cursor.execute("DELETE FROM worker WHERE worker_id = %s", (worker_id,))
        
        if result:
            cursor.execute("DELETE FROM login WHERE login_id = %s", (result[0],))
            
        conn.commit()
    except Exception as e:
        print(f"Error deleting worker: {e}")
        
    cursor.close()
    conn.close()
    return redirect(url_for('manage_workers'))

@app.route('/admin/manage_workers')
def manage_workers():
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login_page'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM worker")
    workers = cursor.fetchall()
    conn.close()
    return render_template('manage_workers.html', workers=workers)

@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('home'))

@app.route('/setup')
def setup():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # --- Idempotent Service Setup ---
        all_services = {
            # Name: (Category, Price, Service_Type)
            'Laundry & Ironing': ('pickup', 250.00, 'regular'),
            'Plumbing Repair': ('onsite', 450.00, 'regular'),
            'Electrical Maintenance': ('onsite', 450.00, 'regular'),
            'Emergency Electric Works': ('onsite', 900.00, 'premium'),
            'Emergency Plumbing Works': ('onsite', 900.00, 'premium'),
            'Full House Cleaning': ('onsite', 1500.00, 'premium'),
            'Gardening': ('onsite', 800.00, 'premium')
        }

        cursor.execute("SELECT service_name FROM service")
        existing_services = {row['service_name'] for row in cursor.fetchall()}
        
        new_services_to_add = []
        for name, details in all_services.items():
            if name not in existing_services:
                new_services_to_add.append((name, details[0], details[1], details[2]))

        if new_services_to_add:
            cursor.executemany("INSERT INTO service (service_name, category, price, service_type) VALUES (%s, %s, %s, %s)", new_services_to_add)
            msg = f"{len(new_services_to_add)} new services added successfully! "
        else:
            msg = "All services already exist. "


        conn.commit()
        cursor.close()
        conn.close()
        return msg + "<a href='/'>Go Home</a>"
    except Exception as e:
        return f"Error setting up data: {e}"

@app.route('/service/<int:service_id>')
def service_details(service_id):
    service = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM service WHERE service_id = %s", (service_id,))
        service = cursor.fetchone()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error fetching service details: {e}")
    return render_template('service_details.html', service=service)

@app.route('/setup_admin')
def setup_admin():
    """A one-time setup route to create the admin user."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check if admin user already exists
        cursor.execute("SELECT * FROM login WHERE username = 'admin'")
        if cursor.fetchone():
            return "Admin user already exists. <a href='/'>Go Home</a>"

        # Create admin user with a default password 'admin'
        cursor.execute("INSERT INTO login (username, password, role) VALUES (%s, %s, 'admin')", 
                       ('admin', 'admin'))
        conn.commit()
        return "Admin user created successfully with username 'admin' and password 'admin'. <a href=\"/login/admin\">Click here to log in.</a>"
    except Exception as e:
        return f"An error occurred: {e}"

if __name__ == '__main__':
    app.run(debug=True, port=5500)