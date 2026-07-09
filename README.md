# Household Service Booking System

A Flask and MySQL web application for booking household services such as laundry, plumbing, electrical maintenance, house cleaning, gardening, and emergency repairs. The system supports customers, workers, and administrators with role-based dashboards, OTP verification, booking management, subscription plans, feedback, and simulated online payments.

## What This Project Does

The Household Service Booking System helps users request and manage home services from one place.

- Customers can register, verify email with OTP, log in, browse services, book services, pay through a payment simulation flow, manage bookings, buy subscriptions, edit profiles, and submit feedback.
- Workers can register, wait for admin approval, view assigned jobs, update job progress, and complete service bookings.
- Administrators can manage bookings, approve or reject workers, add/edit/delete workers, manage subscriptions, view service credits, create default services, and create the admin account.
- The application includes email notifications through Flask-Mail and Gmail SMTP settings.
- The payment flow is simulated for development and testing, with success, failure, timeout, and processing scenarios.

## Benefits

- Simplifies household service discovery and booking.
- Provides separate dashboards for customers, workers, and admins.
- Supports emergency and regular service workflows.
- Includes membership/subscription plans with service credits.
- Uses OTP-based verification for registration, login, password reset, and email changes.
- Helps admins manage workers, bookings, payments, and customer subscriptions from one interface.
- Allows safe payment testing without using a real payment gateway.

## Tech Stack

- Python
- Flask
- MySQL
- mysql-connector-python
- Flask-Mail
- HTML templates with Jinja2
- CSS and JavaScript

## Project Structure

```text
household_service_booking_system/
+-- app.py                    # Main Flask application and routes
+-- config.py                 # Database, mail, and secret key configuration
+-- payment_simulator.py      # Simulated payment scenarios
+-- schema.sql                # MySQL database tables
+-- README.md                 # Project documentation
+-- static/
|   +-- main.js               # Frontend JavaScript
|   +-- style.css             # Application styles
+-- templates/                # HTML/Jinja templates
```

## Modules Imported by the Application

The project uses the following Python modules:

```python
from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
import re
from datetime import datetime, timedelta
from config import (
    DB_HOST, DB_USER, DB_PASSWORD, DB_NAME,
    MAIL_SERVER, MAIL_PORT, MAIL_USERNAME,
    MAIL_PASSWORD, MAIL_USE_TLS, MAIL_SENDER,
    SECRET_KEY
)
from flask_mail import Mail, Message
import random
import json
from payment_simulator import PaymentSimulator
```

The `payment_simulator.py` file imports:

```python
import time
import random
```

## Prerequisites

Install these before running the project:

- Python 3.10 or later
- MySQL Server
- pip
- A Gmail account or SMTP account for email OTP features

## Step 1: Open the Project Folder

```powershell
cd HOUSEHOLD_SERVICE_BOOKING_SYSTEM
```

## Step 2: Create and Activate a Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Step 3: Install Required Python Modules

```powershell
pip install flask mysql-connector-python flask-mail
```

## Step 4: Configure the Application

Open `config.py` and update the database, email, and secret key values.

```python
DB_HOST = 'localhost'
DB_USER = 'root'
DB_PASSWORD = 'your_mysql_password'
DB_NAME = 'household_service_db'

MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USERNAME = 'your_email@gmail.com'
MAIL_PASSWORD = 'your_gmail_app_password'
MAIL_SENDER = 'your_email@gmail.com'

SECRET_KEY = 'change-this-to-a-secure-random-key'
```

For Gmail, use an App Password instead of your normal Gmail password.

## Step 5: Create the MySQL Database

Log in to MySQL:

```powershell
mysql -u root -p
```

Create the database:

```sql
CREATE DATABASE household_service_db;
EXIT;
```

Import the database tables from `schema.sql`:

```powershell
mysql -u root -p household_service_db < schema.sql
```

This creates the main tables, including:

- `customer`
- `worker`
- `worker_pending`
- `login`
- `service`
- `booking`
- `payment`
- `provides`
- `feedback`
- `pending_registrations`
- `subscription_plan`
- `subscription_benefit`
- `customer_subscription`
- `service_credits`
- `otp_store`

## Step 6: Run the Application

```powershell
python app.py
```

The application runs on:

```text
http://127.0.0.1:5500
```

## Step 7: Seed Services and Subscription Plans

After starting the app, open this URL in your browser:

```text
http://127.0.0.1:5500/setup
```

This inserts or updates the default services:

- Laundry & Ironing
- Plumbing Repair
- Electrical Maintenance
- Emergency Electric Works
- Emergency Plumbing Works
- Full House Cleaning
- Gardening

It also creates the default subscription plans and their service benefits.

## Step 8: Create the Admin User

Open this URL once:

```text
http://127.0.0.1:5500/setup_admin
```

Default admin login:

```text
Username: admin
Password: admin
```

After creating the admin account, log in at:

```text
http://127.0.0.1:5500/login/admin
```

For better security, change the default admin password in the database or through your own password update flow before using the system beyond local testing.

## Main Application Pages

- Home page: `http://127.0.0.1:5500/`
- Customer login/register: `http://127.0.0.1:5500/login`
- Admin login: `http://127.0.0.1:5500/login/admin`
- Worker registration: `http://127.0.0.1:5500/worker/register`
- Customer dashboard: `http://127.0.0.1:5500/dashboard`
- Worker dashboard: `http://127.0.0.1:5500/worker/dashboard`
- Admin dashboard: `http://127.0.0.1:5500/admin/dashboard`
- Subscription plans: `http://127.0.0.1:5500/subscription/plans`

## Payment Simulation

The project uses `payment_simulator.py` instead of a real payment gateway. Available simulation results are:

- `success` - payment completes successfully
- `failure` - payment is declined
- `timeout` - payment gateway timeout
- `processing` - payment remains pending

This is useful for testing booking and subscription payment behavior without external payment services.

## Common Workflow

1. Create the MySQL database.
2. Import `schema.sql`.
3. Update `config.py`.
4. Run `python app.py`.
5. Visit `/setup` to create default services and subscription plans.
6. Visit `/setup_admin` to create the admin account.
7. Register customers and workers.
8. Log in as admin to approve workers and manage bookings.
9. Book services from the customer dashboard.
10. Test payments through the simulation pages.

## Troubleshooting

If the app cannot connect to MySQL, check `DB_HOST`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME` in `config.py`.

If OTP emails are not sent, check your SMTP settings and make sure Gmail App Passwords are enabled.

If tables are missing, run the database import again:

```powershell
mysql -u root -p household_service_db < schema.sql
```

If port `5500` is already in use, change the port at the bottom of `app.py`:

```python
app.run(debug=True, port=5500)
```

## Notes

- This project stores passwords as plain text in the current implementation. For production, use password hashing such as Werkzeug's `generate_password_hash` and `check_password_hash`.
- The payment system is a simulator and should be replaced with a real payment gateway before production use.
- Keep real database passwords, email passwords, and secret keys private.
