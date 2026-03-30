from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
import re
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

def is_valid_email(email):
    """Validates the email format."""
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_regex, email) is not None

def is_valid_phone(phone):
    """Validates that the phone number is exactly 10 digits."""
    phone_regex = r'^\d{10}$'
    return re.match(phone_regex, phone) is not None

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
    plans = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Fetch all services to display on the homepage
        cursor.execute("SELECT service_id, service_name, category, price, service_type FROM service WHERE service_type != 'premium' ORDER BY service_type ASC, service_name ASC")
        services = cursor.fetchall()
        
        # Fetch subscription plans to display on the home page
        cursor.execute("SELECT * FROM subscription_plan")
        plans = cursor.fetchall()
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error fetching data for homepage: {e}")
    return render_template('index.html', services=services, plans=plans)

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
    next_url = request.args.get('next')
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        next_url = request.form.get('next')

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
                    session['login_next_url'] = next_url
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

    return render_template('login.html', role=role, next=next_url)

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

        if not is_valid_email(email):
            flash('Invalid email format!', 'error')
            return redirect(url_for('register_page'))

        if not is_valid_phone(phone):
            flash('Phone number must be exactly 10 digits!', 'error')
            return redirect(url_for('register_page'))

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

    next_url = session.get('login_next_url')
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
            session.pop('login_next_url', None)
            
            cursor.close()
            conn.close()

            if next_url:
                return redirect(next_url)
                
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

        if not is_valid_email(email):
            flash('Invalid email format!', 'error')
            return redirect(url_for('worker_register'))

        if not is_valid_phone(phone):
            flash('Phone number must be exactly 10 digits!', 'error')
            return redirect(url_for('worker_register'))

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
    if 'loggedin' not in session or session['role'] != 'customer':
        return redirect(url_for('login_page'))
        
    services = []
    active_subscription = None
    credits = []
    credit_lookup = {}
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT service_id, service_name, price, category, service_type FROM service ORDER BY service_type ASC, service_name ASC")
        services = cursor.fetchall()
        
        # Fetch active subscription details
        cursor.execute("""
            SELECT cs.*, sp.plan_name 
            FROM customer_subscription cs
            JOIN subscription_plan sp ON cs.plan_id = sp.plan_id
            WHERE cs.customer_id = (SELECT customer_id FROM customer WHERE login_id = %s)
            AND cs.status = 'active' AND cs.end_date >= CURDATE()
        """, (session['id'],))
        active_subscription = cursor.fetchone()
        
        if active_subscription:
            cursor.execute("""
                SELECT sc.*, s.service_name 
                FROM service_credits sc
                JOIN service s ON sc.service_id = s.service_id
                WHERE sc.subscription_id = %s
            """, (active_subscription['subscription_id'],))
            credits = cursor.fetchall()
            credit_lookup = {c['service_id']: c for c in credits}
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error fetching services: {e}") # For debugging
    return render_template('customer_dashboard.html', services=services, subscription=active_subscription, credits=credits, credit_lookup=credit_lookup, user_id=session['id'])

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
        pass
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
        pass
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
        pass
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
            SELECT b.booking_id, c.cust_name, s.service_name, s.service_type, b.booking_date, b.booking_time, b.booking_status, p.payment_status, p.amount, p.payment_method, b.subscription_id as is_subscription
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

    cursor.execute("SELECT service_id, service_name, price, category, service_type FROM service WHERE service_type != 'premium' ORDER BY service_type ASC, service_name ASC")
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

    # Fetch booking along with service details for calculation
    cursor.execute("""
        SELECT b.*, p.payment_status, p.payment_method, p.amount as current_amount,
               s.service_name, s.service_type, s.category, s.price as base_price,
               c.cust_name, c.phone as cust_phone, c.address as cust_address
        FROM booking b 
        JOIN payment p ON b.booking_id = p.booking_id 
        JOIN service s ON b.service_id = s.service_id
        JOIN customer c ON b.customer_id = c.customer_id
        WHERE b.booking_id = %s AND b.worker_id = %s
    """, (booking_id, worker_id))
    booking = cursor.fetchone()

    if not booking:
        flash("Booking not found or you are not authorized to edit it.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for('worker_dashboard'))

    if request.method == 'POST':
        status = request.form['status']
        payment_method = request.form.get('payment_method', booking['payment_method'])
        
        total_amount = booking['current_amount']
        payment_status = booking['payment_status']

        # Bill calculation and collection logic only applies to non-subscription jobs
        # and ensures we don't recalculate for already completed/cancelled jobs
        if (not booking['subscription_id'] and 
            booking['service_type'] in ['regular', 'emergency'] and 
            status != 'cancelled' and 
            booking['booking_status'] != 'completed'):
            hours = float(request.form.get('hours', 1))
            weight = float(request.form.get('weight', 1))
            dist = float(request.form.get('pickup_distance', 0))
            
            base_rate = float(booking['base_price'])
            units = weight if 'Laundry' in booking['service_name'] else hours
            delivery = max(0, (dist - 5) * 20) if booking['category'] == 'pickup' else 0
            
            total_amount = (base_rate * units) + delivery
            
            # For emergency services, subtract the ₹100 advance already paid
            if booking['service_type'] == 'emergency':
                total_amount = max(0, total_amount - 100)
            
            if payment_method == 'online':
                if status == 'completed' and total_amount > 0:
                    flash("Cannot mark as 'Completed' for Online Payment until the customer pays the balance via their dashboard.", "error")
                    return redirect(url_for('worker_edit_booking', booking_id=booking_id))
                # Reset payment status to pending for customer action if there's a balance
                payment_status = 'pending' if total_amount > 0 else 'completed'
            elif payment_method == 'cash' and status == 'completed':
                payment_status = 'completed'

        # Credit Restoration Logic: If a worker cancels a subscription booking, return the credit
        if status == 'cancelled' and booking['booking_status'] != 'cancelled' and booking['subscription_id']:
            cursor.execute("""
                UPDATE service_credits 
                SET remaining_quantity = remaining_quantity + 1 
                WHERE subscription_id = %s AND service_id = %s AND is_unlimited = 0
            """, (booking['subscription_id'], booking['service_id']))

        # Update Booking Status
        cursor.execute("UPDATE booking SET booking_status = %s WHERE booking_id = %s", (status, booking_id))

        # Update Payment Details
        if status == 'cancelled':
            payment_status = 'cancelled'

        cursor.execute("""
            UPDATE payment 
            SET amount = %s, payment_method = %s, payment_status = %s 
            WHERE booking_id = %s
        """, (total_amount, payment_method, payment_status, booking_id))

        # Commit changes first
        conn.commit()

        # Check transitions for notifications and feedback
        if status != booking['booking_status'] or total_amount != float(booking['current_amount']) or payment_method != booking['payment_method']:
            if status == 'completed' and booking['booking_status'] != 'completed':
                if payment_method == 'cash':
                    flash('Job and cash payment marked as completed.', 'success')
                pass

                # Notify Customer of completion
                cursor.execute("SELECT c.email, c.cust_name, s.service_name FROM booking b JOIN customer c ON b.customer_id = c.customer_id JOIN service s ON b.service_id = s.service_id WHERE b.booking_id = %s", (booking_id,))
                details = cursor.fetchone()
                if details:
                    send_notification_email(details['email'], f"Service Completed - Booking #{booking_id}", f"Hello {details['cust_name']},\n\nYour service '{details['service_name']}' has been marked as completed by the worker.\n\nWe hope you are satisfied with our work. Please log in to your dashboard to provide feedback.\n\nThank you!")
            
            elif status == 'cancelled' and booking['booking_status'] != 'cancelled':
                # Notify Customer of cancellation (Standard message)
                cursor.execute("SELECT c.email, c.cust_name FROM booking b JOIN customer c ON b.customer_id = c.customer_id WHERE b.booking_id = %s", (booking_id,))
                details = cursor.fetchone()
                if details:
                    send_notification_email(details['email'], f"Booking Cancelled - #{booking_id}", f"Hello {details['cust_name']},\n\nYour booking #{booking_id} has been cancelled by the worker.")
                flash(f'Job #{booking_id} has been cancelled.', 'info')
            else:
                flash('Booking details updated successfully.', 'success')
                pass
        else:
            flash('No changes were made to the booking.', 'info')
        
        cursor.close()
        conn.close()
        return redirect(url_for('worker_dashboard'))

    # GET request: Uses the booking data fetched at the start of the function
    cursor.close()
    conn.close()
    return render_template('worker_edit_booking.html', booking=booking)

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
            b.customer_id, b.worker_id, b.subscription_id,
            s.service_name, p.amount, p.payment_status,
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
        SELECT b.booking_id, c.cust_name, w.worker_name, s.service_name, s.service_type, b.booking_date, b.booking_status, p.payment_status, p.payment_method, p.amount,
        b.subscription_id as is_subscription
        FROM booking b
        JOIN customer c ON b.customer_id = c.customer_id
        JOIN service s ON b.service_id = s.service_id
        LEFT JOIN worker w ON b.worker_id = w.worker_id
        LEFT JOIN payment p ON b.booking_id = p.booking_id
        WHERE s.service_type != 'premium'
        ORDER BY b.booking_date DESC
    """)
    bookings = cursor.fetchall()
    cursor.execute("SELECT service_id, service_name, price, category, service_type FROM service WHERE service_type != 'premium' ORDER BY service_type ASC, service_name ASC")
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

        # Fetch current booking state for credit restoration
        cursor.execute("SELECT booking_status, subscription_id, service_id FROM booking WHERE booking_id = %s", (booking_id,))
        current_booking = cursor.fetchone()

        # Prevent setting subscription jobs back to pending
        if current_booking['subscription_id'] and status == 'pending':
            flash("Subscription-based bookings cannot be set to 'Pending'. Please select 'Completed' or 'Cancelled'.", "error")
            return redirect(url_for('edit_booking', booking_id=booking_id))

        if status == 'cancelled' and current_booking['booking_status'] != 'cancelled' and current_booking['subscription_id']:
            cursor.execute("""
                UPDATE service_credits 
                SET remaining_quantity = remaining_quantity + 1 
                WHERE subscription_id = %s AND service_id = %s AND is_unlimited = 0
            """, (current_booking['subscription_id'], current_booking['service_id']))

        # Handle "None" selection for worker
        if worker_id == 'none':
            worker_id = None
            
        cursor.execute("UPDATE booking SET worker_id = %s, booking_status = %s WHERE booking_id = %s", 
                       (worker_id, status, booking_id))
        
        if status == 'completed':
            cursor.execute("SELECT payment_method FROM payment WHERE booking_id = %s", (booking_id,))
            payment = cursor.fetchone()
            if payment and payment['payment_method'] == 'cash':
                cursor.execute("UPDATE payment SET payment_status = 'completed' WHERE booking_id = %s", (booking_id,))
                flash('Booking marked as completed. Cash payment status updated to Paid.', 'success')
        elif status == 'cancelled':
            try:
                cursor.execute("UPDATE payment SET payment_status = 'cancelled' WHERE booking_id = %s", (booking_id,))
            except mysql.connector.Error:
                pass
            
            # Notify Customer of cancellation (Standard message)
            cursor.execute("SELECT c.email, c.cust_name FROM booking b JOIN customer c ON b.customer_id = c.customer_id WHERE b.booking_id = %s", (booking_id,))
            details = cursor.fetchone()
            if details:
                send_notification_email(details['email'], f"Booking Cancelled - #{booking_id}", f"Hello {details['cust_name']},\n\nYour booking #{booking_id} has been cancelled by the admin.")

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
        if worker_id and status not in ['completed', 'cancelled']:
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
        SELECT b.booking_id, b.booking_date, b.booking_status, b.worker_id, b.subscription_id,
               c.cust_name, s.service_name, p.payment_status, p.amount, p.payment_method
        FROM booking b
        JOIN customer c ON b.customer_id = c.customer_id
        JOIN service s ON b.service_id = s.service_id
        LEFT JOIN payment p ON b.booking_id = p.booking_id
        WHERE b.booking_id = %s
    """, (booking_id,))
    booking = cursor.fetchone()

    # Fetch all workers for the dropdown
    cursor.execute("SELECT worker_id, worker_name, rating FROM worker")
    workers = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('edit_booking.html', booking=booking, workers=workers)

@app.route('/admin/refund_message/<int:booking_id>')
def refund_message(booking_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login_page'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT c.email, c.cust_name 
            FROM booking b 
            JOIN customer c ON b.customer_id = c.customer_id 
            WHERE b.booking_id = %s
        """, (booking_id,))
        details = cursor.fetchone()
        
        if details:
            subject = f"Refund Update - Booking #{booking_id}"
            body = f"Hello {details['cust_name']},\n\nyour refund will be done in few days"
            if send_notification_email(details['email'], subject, body):
                flash(f"Refund message sent to {details['cust_name']}.", 'success')
                pass
            else:
                flash('Failed to send email.', 'error')
        
        cursor.close()
        conn.close()
    except Exception as e:
        flash(f'Error: {e}', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/refund_pay/<int:booking_id>')
def refund_pay(booking_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login_page'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT c.email, c.cust_name 
            FROM booking b 
            JOIN customer c ON b.customer_id = c.customer_id 
            WHERE b.booking_id = %s
        """, (booking_id,))
        details = cursor.fetchone()
        
        if details:
            subject = f"Refund Credited - Booking #{booking_id}"
            body = f"Hello {details['cust_name']},\n\nrefund credited to your account for the booking "
            if send_notification_email(details['email'], subject, body):
                cursor.execute("UPDATE payment SET payment_status = 'refunded' WHERE booking_id = %s", (booking_id,))
                conn.commit()
                flash(f"Payment refund confirmation sent to {details['cust_name']}.", 'success')
            else:
                flash('Failed to send email.', 'error')
        
        cursor.close()
        conn.close()
    except Exception as e:
        flash(f'Error: {e}', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/cancel_subscription/<int:subscription_id>')
def admin_cancel_subscription(subscription_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login_page'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE customer_subscription SET status = 'cancelled' WHERE subscription_id = %s", (subscription_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash(f'Subscription #{subscription_id} has been cancelled.', 'info')
    except Exception as e:
        flash(f'Error cancelling subscription: {e}', 'error')
    return redirect(url_for('admin_manage_subscriptions'))

@app.route('/admin/subscription_credits/<int:subscription_id>')
def admin_view_subscription_credits(subscription_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login_page'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Fetch subscription info with customer and plan details
    cursor.execute("""
        SELECT cs.*, c.cust_name, sp.plan_name 
        FROM customer_subscription cs
        JOIN customer c ON cs.customer_id = c.customer_id
        JOIN subscription_plan sp ON cs.plan_id = sp.plan_id
        WHERE cs.subscription_id = %s
    """, (subscription_id,))
    subscription = cursor.fetchone()
    
    if not subscription:
        flash("Subscription not found.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for('admin_manage_subscriptions'))
        
    # Fetch detailed credits for this subscription
    cursor.execute("""
        SELECT sc.*, s.service_name 
        FROM service_credits sc
        JOIN service s ON sc.service_id = s.service_id
        WHERE sc.subscription_id = %s
    """, (subscription_id,))
    credits = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('admin_view_credits.html', subscription=subscription, credits=credits)

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
    conn = None
    credits = None
    region = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True) # Ensure cursor returns dictionaries
        # Fetch service details while ensuring premium services are excluded as requested
        cursor.execute("SELECT * FROM service WHERE service_id = %s AND service_type != 'premium'", (service_id,))
        service = cursor.fetchone()

        if not service:
            flash('Service not found or is currently unavailable.', 'error')
            return redirect(url_for('dashboard'))

        # Fetch all workers including 24/7 status for selection
        cursor.execute("SELECT worker_id, worker_name, rating as avg_rating, is_24_7 FROM worker ORDER BY rating DESC")
        workers = cursor.fetchall()

        # Check workload availability to prevent worker overload (Max 4 pending jobs)
        cursor.execute("""
            SELECT b.worker_id, COUNT(*) as total
            FROM booking b 
            JOIN service s ON b.service_id = s.service_id
            WHERE b.booking_status = 'pending'
            GROUP BY b.worker_id
        """)
        workloads = {row['worker_id']: row for row in cursor.fetchall()}

        for worker in workers:
            load = workloads.get(worker['worker_id'], {'total': 0})
            current_total = load['total']
            
            # Ensure workload efficiency: limit to 4 jobs total
            worker['is_available'] = current_total < 4
            worker['status_msg'] = 'High Workload' if current_total >= 4 else None
            
        # Check for subscription credits
        if session['role'] == 'customer':
            cursor.execute("SELECT region FROM customer WHERE login_id = %s", (session['id'],))
            cust_row = cursor.fetchone()
            if cust_row:
                region = cust_row['region']

            cursor.execute("""
                SELECT sc.* 
                FROM service_credits sc
                JOIN customer_subscription cs ON sc.subscription_id = cs.subscription_id
                WHERE cs.customer_id = (SELECT customer_id FROM customer WHERE login_id = %s) 
                AND sc.service_id = %s AND cs.status = 'active' AND cs.end_date >= CURDATE()
            """, (session['id'], service_id))
            credits = cursor.fetchone()

        return render_template('booking_form.html', service=service, workers=workers, now=now, credits=credits, region=region)

    except Exception as e:
        print(f"Error fetching service details: {e}")
        flash('An error occurred while loading the booking form. Please try again.', 'error')
        return redirect(url_for('dashboard'))
    finally:
        if conn:
            cursor.close()
            conn.close()

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

    # Emergency logic: 24/7 worker assignment, immediate time, and online payment
    is_emergency = service.get('service_type') == 'emergency'
    is_laundry = 'laundry' in service.get('service_name', '').lower()
    urgency_multiplier = 1.0 
    
    subscription_id = None

    # Get the selected worker_id (if any)
    worker_id = request.form.get('worker_id')
    candidates = []  # Initialize to prevent UnboundLocalError

    # For emergency services, user can choose to use subscription credits
    if is_emergency:
        use_subscription = request.form.get('use_subscription') == '1'
        if use_subscription:
            cursor.execute("""
                SELECT sc.credit_id, sc.subscription_id, sc.remaining_quantity, sc.is_unlimited
                FROM service_credits sc
                JOIN customer_subscription cs ON sc.subscription_id = cs.subscription_id
                WHERE cs.customer_id = (SELECT customer_id FROM customer WHERE login_id = %s)
                AND sc.service_id = %s AND cs.status = 'active' AND cs.end_date >= CURDATE()
                AND (sc.remaining_quantity > 0 OR sc.is_unlimited = 1)
            """, (login_id, service_id))
            credit_record = cursor.fetchone()
            
            if credit_record:
                subscription_id = credit_record['subscription_id']
                if not credit_record['is_unlimited']:
                    cursor.execute("UPDATE service_credits SET remaining_quantity = remaining_quantity - 1 WHERE credit_id = %s", 
                                   (credit_record['credit_id'],))
            else:
                flash('No subscription credits available for this service. Booking will proceed with regular billing.', 'warning')
                subscription_id = None
    else:
        # For regular services, user choice
        use_subscription = request.form.get('use_subscription') == '1'
        if use_subscription:
            cursor.execute("""
                SELECT sc.credit_id, sc.subscription_id, sc.remaining_quantity, sc.is_unlimited
                FROM service_credits sc
                JOIN customer_subscription cs ON sc.subscription_id = cs.subscription_id
                WHERE cs.customer_id = (SELECT customer_id FROM customer WHERE login_id = %s)
                AND sc.service_id = %s AND cs.status = 'active' AND cs.end_date >= CURDATE()
                AND (sc.remaining_quantity > 0 OR sc.is_unlimited = 1)
            """, (login_id, service_id))
            credit_record = cursor.fetchone()
            
            if credit_record:
                subscription_id = credit_record['subscription_id']
                if not credit_record['is_unlimited']:
                    cursor.execute("UPDATE service_credits SET remaining_quantity = remaining_quantity - 1 WHERE credit_id = %s", 
                                   (credit_record['credit_id'],))
            else:
                flash('No subscription credits available for this service. Booking will proceed with regular billing.', 'warning')
                subscription_id = None
                use_subscription = False

    # Set booking_date and booking_time for worker check
    if is_emergency:
        booking_date = datetime.now().date()
        booking_time = datetime.now().replace(microsecond=0).time()
    else:
        booking_date = request.form.get('booking_date')
        booking_time = request.form.get('booking_time')
        
        if not booking_date or not booking_time:
            flash('Please select a valid date and time.', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('booking_form', service_id=service_id))
    
    # Worker Assignment Logic
    if worker_id and worker_id != 'none':
        # Check if the selected worker has another booking on the chosen date
        cursor.execute("""
            SELECT 1 FROM booking
            WHERE worker_id = %s
            AND booking_date = %s
            AND booking_status NOT IN ('completed', 'cancelled')
        """, (worker_id, booking_date))
        if cursor.fetchone():
            flash('The selected worker is already assigned to another job on the chosen date. Please choose a different worker or select "No Preference".', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('booking_form', service_id=service_id))
        
        # Check if the selected worker is overloaded
        cursor.execute("""
            SELECT COUNT(b.booking_id) as total
            FROM booking b
            WHERE b.worker_id = %s AND b.booking_status = 'pending'
        """, (worker_id,))
        stats = cursor.fetchone()
        
        current_total = stats['total']
        
        if current_total >= 4:
            flash('The selected worker has just reached their workload limit. Please choose another or select "No Preference".', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('booking_form', service_id=service_id))

    if worker_id == 'none' or not worker_id:
        # Randomly assign a worker who is available on the date/time and not overloaded
        if is_emergency:
            cursor.execute("""
                SELECT worker_id FROM worker 
                WHERE is_24_7 = 1 
                AND NOT EXISTS (
                    SELECT 1 FROM booking 
                    WHERE worker_id = worker.worker_id 
                    AND booking_date = CURDATE() 
                    AND booking_status NOT IN ('completed', 'cancelled')
                )
                AND (SELECT COUNT(*) FROM booking WHERE worker_id = worker.worker_id AND booking_status = 'pending') < 4 
                ORDER BY rating DESC LIMIT 1
            """)
            worker_row = cursor.fetchone()
            if worker_row:
                worker_id = worker_row['worker_id']
            else:
                flash('No 24/7 workers are currently available due to high demand.', 'error')
                cursor.close()
                conn.close()
                return redirect(url_for('booking_form', service_id=service_id))
        else:
            cursor.execute("""
                SELECT w.worker_id 
                FROM worker w 
                JOIN provides p ON w.worker_id = p.worker_id 
                LEFT JOIN (SELECT worker_id, COUNT(*) as total FROM booking WHERE booking_status = 'pending' GROUP BY worker_id) b ON w.worker_id = b.worker_id
                WHERE p.service_id = %s 
                AND (b.total IS NULL OR b.total < 4)
                AND NOT EXISTS (
                    SELECT 1 FROM booking b2 
                    WHERE b2.worker_id = w.worker_id 
                    AND b2.booking_date = %s 
                    AND b2.booking_status NOT IN ('completed', 'cancelled')
                )
            """, (service_id, booking_date, booking_time, booking_time, booking_time, booking_time))
            for row in cursor.fetchall():
                candidates.append(row['worker_id'])
            
            if candidates:
                worker_id = random.choice(candidates)
            else:
                flash('All workers are currently fully booked at the selected time on that date. Please try a different time or date.', 'error')
                cursor.close()
                conn.close()
                return redirect(url_for('booking_form', service_id=service_id))

    # 2. Fetch Customer Details
    cursor.execute("SELECT customer_id, region, email, cust_name FROM customer WHERE login_id = %s", (login_id,))
    customer = cursor.fetchone()

    if customer and service:
        # Time restriction for Regular Services: 9 AM to 6 PM
        if service.get('service_type') == 'regular' and not is_emergency:
            try:
                # Convert booking_time to time object if it's a string
                if isinstance(booking_time, str):
                    fmt = '%H:%M:%S' if len(booking_time.split(':')) == 3 else '%H:%M'
                    selected_time = datetime.strptime(booking_time, fmt).time()
                else:
                    selected_time = booking_time
                    
                # Convert booking_date to date object if it's a string
                if isinstance(booking_date, str):
                    selected_date = datetime.strptime(booking_date, '%Y-%m-%d').date()
                else:
                    selected_date = booking_date
                    
                now = datetime.now()
                start_limit = datetime.strptime('09:00', '%H:%M').time()
                end_limit = datetime.strptime('18:00', '%H:%M').time()

                if selected_time < start_limit or selected_time > end_limit:
                    flash('Regular services can only be booked between 9:00 AM and 6:00 PM.', 'error')
                    cursor.close()
                    conn.close()
                    return redirect(url_for('booking_form', service_id=service_id))

                # Check if booking for today and the time has already passed
                if selected_date == now.date() and selected_time < now.time():
                    flash('For same-day bookings, please select a time in the future.', 'error')
                    cursor.close()
                    conn.close()
                    return redirect(url_for('booking_form', service_id=service_id))
            except ValueError:
                flash('Invalid time format selected. Please use the time picker.', 'error')
                cursor.close()
                conn.close()
                return redirect(url_for('booking_form', service_id=service_id))

        customer_id = customer['customer_id']
        
        # Schema only supports pending/completed/cancelled
        initial_status = 'pending'
        
        # Determine payment method
        if is_emergency or subscription_id:
            payment_method = 'online'
        else:
            payment_method = request.form.get('payment_method', 'cash')

        cursor.execute("INSERT INTO booking (booking_date, booking_time, booking_status, customer_id, service_id, worker_id, subscription_id) VALUES (%s, %s, %s, %s, %s, %s, %s)", 
                       (booking_date, booking_time, initial_status, customer_id, service_id, worker_id, subscription_id))
        booking_id = cursor.lastrowid

        # Handle Payment Entry
        base_rate = float(service['price'])
        units = 1.0
        if any(keyword in service['service_name'] for keyword in ['Cleaning', 'Plumbing', 'Electric', 'Gardening', 'Repair', 'Maintenance']):
            units = float(request.form.get('hours', 1))
        elif 'Laundry' in service['service_name']:
            units = float(request.form.get('weight', 1))
            
        amount = base_rate * units * urgency_multiplier
        
        # Add delivery charge if applicable
        delivery_charge = 0
        if service['category'] == 'pickup':
            pickup_distance = float(request.form.get('pickup_distance', 0))
            delivery_charge += max(0, (pickup_distance - 5) * 20)
        
        if subscription_id:
            total_amount = 0.00
            payment_status = 'completed'
        elif is_emergency:
            # Emergency services pay a flat ₹100 advance upfront
            total_amount = 100.00
            payment_status = 'pending'
        else:
            # Regular service: Amount decided after service by worker metrics
            total_amount = 0.00
            payment_status = 'pending'

        # Insert into payment table
        cursor.execute("INSERT INTO payment (amount, payment_status, payment_method, booking_id, subscription_id) VALUES (%s, %s, %s, %s, %s)",
                       (total_amount, payment_status, payment_method, booking_id, subscription_id))
        
        conn.commit()
        
        # Send Booking Confirmation Email (for Cash payments or initial booking state)
        email_subject = f"EMERGENCY Booking Confirmed - #{booking_id}" if is_emergency else f"Booking Confirmed - #{booking_id}"
        
        if customer.get('email'):
            email_body = f"Hello {customer['cust_name']},\n\nYour {'EMERGENCY ' if is_emergency else ''}booking for {service['service_name']} has been placed successfully.\nBooking ID: {booking_id}\nDate: {booking_date}\nTime: {booking_time}\nTotal Amount: ₹{total_amount}\n\n"
            
            if is_laundry:
                # Regional Laundry Schedule
                schedules = {
                    'North': 'Mondays and Fridays',
                    'South': 'Tuesdays and Saturdays',
                    'East': 'Wednesdays',
                    'West': 'Thursdays'
                }
                pickup_days = schedules.get(customer['region'], 'scheduled days')
                email_body += f"Note for Laundry Service: Based on your region ({customer['region']}), our pickup team visits on {pickup_days}. Please ensure your laundry is ready for collection on the next available day.\n\n"
            
            email_body += "Thank you for choosing My Eazy Day."
            send_notification_email(customer['email'], email_subject, email_body)

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

        if use_subscription:
            cursor.close()
            conn.close()
            return redirect(url_for('my_bookings'))

        # Only redirect to payment simulator for emergency online bookings at time of order
        if is_emergency and payment_method == 'online':
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
            
            # Mark booking as completed for regular services OR emergency balance payments (non-deposit)
            cursor.execute("""
                SELECT s.service_type, p.amount, b.booking_status
                FROM booking b 
                JOIN service s ON b.service_id = s.service_id 
                JOIN payment p ON b.booking_id = p.booking_id
                WHERE b.booking_id = %s
            """, (booking_id,))
            info = cursor.fetchone()
            
            # For emergency: only mark complete if this isn't the initial deposit (detected by amount != 100)
            if info['service_type'] == 'regular' or (info['service_type'] == 'emergency' and float(info['amount']) != 100.0):
                cursor.execute("UPDATE booking SET booking_status = 'completed' WHERE booking_id = %s", (booking_id,))
            
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
                   b.subscription_id as is_subscription,
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

        if not is_valid_email(email):
            flash('Invalid email format!', 'error')
            return redirect(url_for('customer_edit_profile'))

        if not is_valid_phone(phone):
            flash('Phone number must be exactly 10 digits!', 'error')
            return redirect(url_for('customer_edit_profile'))

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
                VALUES (%s, %s, 'email_change', %s)
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

        cursor.execute("SELECT * FROM otp_store WHERE email = %s AND otp = %s AND purpose = 'email_change'", (new_email, otp))
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
            cursor.execute("DELETE FROM otp_store WHERE email = %s AND purpose = 'email_change'", (new_email,))
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
        cursor.execute("UPDATE otp_store SET otp = %s, expires_at = %s WHERE email = %s AND purpose = 'email_change'", 
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
    # Security check: Ensure booking belongs to user, is completed, and hasn't been rated
    cursor.execute("""
        SELECT b.booking_id FROM booking b
        LEFT JOIN feedback f ON b.booking_id = f.booking_id
        WHERE b.booking_id = %s 
        AND b.customer_id = (SELECT customer_id FROM customer WHERE login_id = %s)
        AND b.booking_status = 'completed'
        AND f.feedback_id IS NULL
    """, (booking_id, session['id']))
    
    valid_booking = cursor.fetchone()

    if not valid_booking:
        flash("You are not authorized to rate this booking or it has already been rated.", "error")
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

        if not is_valid_email(email):
            flash('Invalid email format!', 'error')
            return redirect(url_for('add_worker'))

        if not is_valid_phone(phone):
            flash('Phone number must be exactly 10 digits!', 'error')
            return redirect(url_for('add_worker'))

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

        if not is_valid_email(email):
            flash('Invalid email format!', 'error')
            return redirect(url_for('edit_worker', worker_id=worker_id))

        if not is_valid_phone(phone):
            flash('Phone number must be exactly 10 digits!', 'error')
            return redirect(url_for('edit_worker', worker_id=worker_id))

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

@app.route('/admin/manage_subscriptions')
def admin_manage_subscriptions():
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login_page'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT cs.subscription_id, c.cust_name, sp.plan_name, cs.start_date, cs.end_date, cs.status
        FROM customer_subscription cs
        JOIN customer c ON cs.customer_id = c.customer_id
        JOIN subscription_plan sp ON cs.plan_id = sp.plan_id
        ORDER BY cs.start_date DESC
    """)
    subscriptions = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('manage_subscriptions.html', subscriptions=subscriptions)

@app.route('/admin/delete_subscription/<int:subscription_id>')
def delete_subscription(subscription_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login_page'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM customer_subscription WHERE subscription_id = %s", (subscription_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash(f"Subscription #{subscription_id} deleted successfully.", "success")
    return redirect(url_for('admin_manage_subscriptions'))

@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('home'))

@app.route('/subscription/plans')
def subscription_plans():
    if 'loggedin' not in session or session['role'] != 'customer':
        return redirect(url_for('login_page', next=url_for('subscription_plans')))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM subscription_plan")
    plans = cursor.fetchall()

    # Fetch current active or pending subscription
    cursor.execute("""
        SELECT cs.plan_id, cs.status, cs.subscription_id
        FROM customer_subscription cs
        WHERE cs.customer_id = (SELECT customer_id FROM customer WHERE login_id = %s)
        AND cs.status IN ('active', 'pending') AND cs.end_date >= CURDATE()
        ORDER BY cs.subscription_id DESC LIMIT 1
    """, (session['id'],))
    current_sub = cursor.fetchone()

    cursor.close()
    conn.close()
    return render_template('subscription_plans.html', plans=plans, current_sub=current_sub)

@app.route('/subscription/buy/<int:plan_id>', methods=['POST'])
def buy_subscription(plan_id):
    if 'loggedin' not in session or session['role'] != 'customer':
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT * FROM subscription_plan WHERE plan_id = %s", (plan_id,))
        plan = cursor.fetchone()
        if not plan:
            flash("Plan not found.", "error")
            return redirect(url_for('dashboard'))

        cursor.execute("SELECT customer_id FROM customer WHERE login_id = %s", (session['id'],))
        customer = cursor.fetchone()
        customer_id = customer['customer_id']

        # Strict One-Subscription Policy: Physically remove any existing membership 
        # (Active, Pending, or Expired) from the database immediately.
        # This ensures the customer can only proceed with one subscription at a time.
        cursor.execute("DELETE FROM customer_subscription WHERE customer_id = %s", (customer_id,))
        amount_to_pay = plan['price']

        start_date = datetime.now().date()
        end_date = start_date + timedelta(days=plan['duration_months'] * 30)
        
        cursor.execute("""
            INSERT INTO customer_subscription (customer_id, plan_id, start_date, end_date, status)
            VALUES (%s, %s, %s, %s, 'pending')
        """, (customer_id, plan_id, start_date, end_date))
        subscription_id = cursor.lastrowid

        # Create a pending payment record for the subscription
        cursor.execute("""
            INSERT INTO payment (amount, payment_status, payment_method, subscription_id)
            VALUES (%s, 'pending', 'online', %s)
        """, (amount_to_pay, subscription_id))

        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('subscription_payment_simulation', subscription_id=subscription_id))

    except Exception as e:
        print(f"Error buying subscription: {e}")
        conn.rollback()
        flash("An error occurred while purchasing the subscription.", "error")
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('dashboard'))

@app.route('/customer/cancel_subscription/<int:subscription_id>', methods=['GET'])
def customer_cancel_subscription(subscription_id):
    if 'loggedin' not in session or session['role'] != 'customer':
        return redirect(url_for('login_page'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Verify ownership to ensure a customer can only cancel their own subscription
        cursor.execute("""
            SELECT subscription_id FROM customer_subscription 
            WHERE subscription_id = %s AND customer_id = (SELECT customer_id FROM customer WHERE login_id = %s)
        """, (subscription_id, session['id']))
        
        if cursor.fetchone():
            # Delete feedback tied to bookings for the subscription to avoid FK constraint failure
            cursor.execute("""
                DELETE f
                FROM feedback f
                JOIN booking b ON f.booking_id = b.booking_id
                WHERE b.subscription_id = %s
            """, (subscription_id,))

            # Delete payment records tied to these bookings (safe cleanup)
            cursor.execute("""
                DELETE p
                FROM payment p
                JOIN booking b ON p.booking_id = b.booking_id
                WHERE b.subscription_id = %s
            """, (subscription_id,))

            # Delete the subscription; this cascades to booking (and service_credits/payment by subscription_id)
            cursor.execute("DELETE FROM customer_subscription WHERE subscription_id = %s", (subscription_id,))
            conn.commit()
            flash('Your membership has been successfully cancelled and related booking records were removed.', 'info')
        else:
            flash('Subscription not found or unauthorized.', 'error')
            
        cursor.close()
        conn.close()
    except Exception as e:
        flash(f'Error cancelling subscription: {e}', 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/subscription/payment_simulation/<int:subscription_id>')
def subscription_payment_simulation(subscription_id):
    if 'loggedin' not in session:
        return redirect(url_for('login_page'))
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT cs.subscription_id, sp.plan_name, p.amount
        FROM customer_subscription cs
        JOIN subscription_plan sp ON cs.plan_id = sp.plan_id
        JOIN payment p ON cs.subscription_id = p.subscription_id
        WHERE cs.subscription_id = %s
    """, (subscription_id,))
    subscription = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if not subscription:
        flash('Subscription request not found', 'error')
        return redirect(url_for('dashboard'))
    
    return render_template('subscription_payment_simulation.html', 
                         subscription_id=subscription['subscription_id'],
                         plan_name=subscription['plan_name'],
                         amount=subscription['amount'])

@app.route('/process_subscription_payment_simulation', methods=['POST'])
def process_subscription_payment_simulation():
    if 'loggedin' not in session:
        return redirect(url_for('login_page'))
        
    subscription_id = int(request.form['subscription_id'])
    scenario = request.form['scenario']
    amount = float(request.form['amount'])
    
    result = PaymentSimulator.simulate_payment_scenario(scenario, subscription_id, amount)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        if result['status'] == 'completed':
            # 1. Update Payment
            cursor.execute("UPDATE payment SET payment_status = 'completed' WHERE subscription_id = %s", (subscription_id,))
            
            # 2. Activate Subscription
            cursor.execute("UPDATE customer_subscription SET status = 'active' WHERE subscription_id = %s", (subscription_id,))
            
            # Final Cleanup: Ensure any stray memberships are removed.
            # This enforces that the customer_subscription table only ever holds one record per user.
            cursor.execute("SELECT customer_id FROM customer_subscription WHERE subscription_id = %s", (subscription_id,))
            cust_row = cursor.fetchone()
            if cust_row:
                cursor.execute("DELETE FROM customer_subscription WHERE customer_id = %s AND subscription_id <> %s", 
                               (cust_row['customer_id'], subscription_id))

            # 3. Populate Service Credits
            cursor.execute("""
                SELECT sb.* 
                FROM subscription_benefit sb
                JOIN customer_subscription cs ON sb.plan_id = cs.plan_id
                WHERE cs.subscription_id = %s
            """, (subscription_id,))
            benefits = cursor.fetchall()
            
            for b in benefits:
                cursor.execute("""
                    INSERT INTO service_credits (subscription_id, service_id, remaining_quantity, is_unlimited)
                    VALUES (%s, %s, %s, %s)
                """, (subscription_id, b['service_id'], b['quantity'], b['is_unlimited']))
            
            conn.commit()
            
            # Notify Customer
            cursor.execute("""
                SELECT c.email, c.cust_name, sp.plan_name 
                FROM customer_subscription cs 
                JOIN customer c ON cs.customer_id = c.customer_id 
                JOIN subscription_plan sp ON cs.plan_id = sp.plan_id
                WHERE cs.subscription_id = %s
            """, (subscription_id,))
            details = cursor.fetchone()
            if details:
                send_notification_email(details['email'], "Membership Activated", 
                                     f"Hello {details['cust_name']},\n\nYour payment of ₹{amount} for the {details['plan_name']} was successful. Your membership is now active!")

            return render_template('subscription_payment_result.html', status='success', message=result['message'])
            
        elif result['status'] in ['failed', 'timeout']:
            # Clean up pending records on failure
            cursor.execute("DELETE FROM payment WHERE subscription_id = %s", (subscription_id,))
            cursor.execute("DELETE FROM customer_subscription WHERE subscription_id = %s", (subscription_id,))
            conn.commit()
            return render_template('subscription_payment_result.html', status='failed', message=result['message'])
            
        elif result['status'] == 'processing':
            return render_template('subscription_payment_result.html', status='info', message=result['message'])
            
        else:
            return render_template('subscription_payment_result.html', status='failed', message='Invalid payment scenario')
            
    except Exception as e:
        print(f"Subscription payment simulation error: {e}")
        conn.rollback()
        return render_template('subscription_payment_result.html', status='failed', message='An error occurred during payment processing.')
    finally:
        cursor.close()
        conn.close()

@app.route('/setup')
def setup():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # --- 1. Core Service Setup (Must be first for benefits to link) ---
        all_services = {
            'Laundry & Ironing': ('pickup', 100.00, 'regular'),
            'Plumbing Repair': ('onsite', 100.00, 'regular'),
            'Electrical Maintenance': ('onsite', 100.00, 'regular'),
            'Emergency Electric Works': ('onsite', 100.00, 'emergency'),
            'Emergency Plumbing Works': ('onsite', 100.00, 'emergency'),
            'Full House Cleaning': ('onsite', 200.00, 'regular'),
            'Gardening': ('onsite', 200.00, 'regular')
        }

        for name, details in all_services.items():
            cursor.execute("SELECT service_id FROM service WHERE service_name = %s", (name,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO service (service_name, category, price, service_type) VALUES (%s, %s, %s, %s)", 
                               (name, details[0], details[1], details[2]))
            else:
                cursor.execute("UPDATE service SET price = %s, service_type = %s WHERE service_name = %s", (details[1], details[2], name))

        # --- 2. Subscription Plan Setup ---
        plans = [
            {
                'name': '3-Month Basic Membership',
                'price': 1000.00,
                'desc': 'Includes 4 Laundry sessions and 1 Emergency Plumbing session.',
                'benefits': [('Laundry & Ironing', 4, False), ('Emergency Plumbing Works', 1, False)]
            },
            {
                'name': '3-Month Premium Membership',
                'price': 6000.00,
                'desc': 'Includes 12 Laundry sessions, 1 House Cleaning, 1 Gardening, and 3 Emergency Plumbing/Electric sessions.',
                'benefits': [
                    ('Laundry & Ironing', 12, False),
                    ('Full House Cleaning', 1, False),
                    ('Gardening', 1, False),
                    ('Emergency Electric Works', 3, False),
                    ('Emergency Plumbing Works', 3, False)
                ]
            }
        ]

        for p in plans:
            cursor.execute("SELECT plan_id FROM subscription_plan WHERE plan_name = %s", (p['name'],))
            plan_exists = cursor.fetchone()
            
            if not plan_exists:
                cursor.execute("""
                    INSERT INTO subscription_plan (plan_name, price, duration_months, description) 
                    VALUES (%s, %s, %s, %s)
                """, (p['name'], p['price'], 3, p['desc']))
                plan_id = cursor.lastrowid
                
                for s_name, qty, unlimited in p['benefits']:
                    cursor.execute("SELECT service_id FROM service WHERE service_name = %s", (s_name,))
                    svc = cursor.fetchone()
                    if svc:
                        cursor.execute("""
                            INSERT INTO subscription_benefit (plan_id, service_id, quantity, is_unlimited)
                            VALUES (%s, %s, %s, %s)
                        """, (plan_id, svc['service_id'], qty, unlimited))

        msg = "Service prices, subscription plans and benefits updated successfully! "

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
        cursor.execute("SELECT * FROM service WHERE service_id = %s AND service_type != 'premium'", (service_id,))
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