import os
import requests
import traceback
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
import pandas as pd
import io

load_dotenv()
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, text
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import escape
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
csrf = CSRFProtect(app)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

def safe_str(val):
    return str(escape(str(val))) if val else val
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'vrs-secret-key-development-only')

basedir = os.path.abspath(os.path.dirname(__file__))

if os.environ.get('DATABASE_URL'):
    # Fix for SQLAlchemy 1.4+ which requires 'postgresql://' instead of 'postgres://'
    db_url = os.environ.get('DATABASE_URL')
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
elif os.environ.get('VERCEL'):
    # Vercel is serverless; SQLite in /tmp is NOT persistent.
    # This is only a fallback to prevent 500 errors if DATABASE_URL is missing.
    print("WARNING: Running on Vercel without DATABASE_URL. Data will NOT persist.")
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/library.db'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'library.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

IST = pytz.timezone('Asia/Kolkata')

# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=True)
    password = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    purpose = db.Column(db.String(100))
    description = db.Column(db.Text)
    profile_photo = db.Column(db.Text, nullable=True) # Store compressed base64
    is_admin = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='pending') # pending, active, frozen
    
    fathers_name = db.Column(db.String(100), nullable=True)
    address = db.Column(db.Text, nullable=True)
    
    # Admin only comments
    admin_note_1 = db.Column(db.Text, nullable=True)
    admin_note_2 = db.Column(db.Text, nullable=True)

    # Relationship with Bookings (Cascade Delete ensures bookings are removed if user is deleted)
    bookings = db.relationship('Booking', backref='user', cascade='all, delete-orphan')

    @property
    def is_active(self):
        return self.status == 'active'

    @is_active.setter
    def is_active(self, value):
        # Allow setting for compatibility, but prioritize status
        if value:
            self.status = 'active'
        elif self.status == 'active':
            self.status = 'frozen'

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)

class Seat(db.Model):
    id = db.Column(db.String(10), primary_key=True)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    seat_id = db.Column(db.String(10), db.ForeignKey('seat.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    shift = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='pending') 
    requested_plan = db.Column(db.String(20), default='1 Month')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    expires_at = db.Column(db.DateTime)
    start_date = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    amount = db.Column(db.Integer, default=0)

    def __init__(self, **kwargs):
        super(Booking, self).__init__(**kwargs)

class WaitingRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    removed_from_seat = db.Column(db.String(10))
    
    # Relationship
    user = db.relationship('User', backref='waiting_room_entry', uselist=False)

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=True)
    
    # Relationship for convenience
    log_user = db.relationship('User', backref='activity_logs')

def log_activity(action, details=None, user_id=None):
    try:
        new_log = ActivityLog(action=action, details=details, user_id=user_id)
        db.session.add(new_log)
        db.session.commit()
    except Exception as e:
        print(f"Logging error: {e}")
        db.session.rollback()

def get_default_amount(shift):
    if shift == 'full':
        return 800
    return 400

def ensure_columns_exist():
    """Simple 'poor man's migration' to ensure all columns exist in Postgres/SQLite."""
    try:
        # User table columns
        user_cols = {
            'fathers_name': 'VARCHAR(100)',
            'address': 'TEXT',
            'status': "VARCHAR(20) DEFAULT 'pending'",
            'admin_note_1': 'TEXT',
            'admin_note_2': 'TEXT',
            'profile_photo': 'TEXT',
            'is_admin': 'BOOLEAN DEFAULT FALSE'
        }
        # Booking table columns
        booking_cols = {
            'amount': 'INTEGER DEFAULT 0',
            'requested_plan': "VARCHAR(20) DEFAULT '1 Month'",
            'start_date': 'TIMESTAMP',
            'expires_at': 'TIMESTAMP',
            'created_at': 'TIMESTAMP'
        }
        
        engine_name = db.engine.name
        is_postgres = engine_name == 'postgresql'
        
        for col, col_type in user_cols.items():
            try:
                table_name = '"user"' if is_postgres else 'user'
                db.session.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {col} {col_type}'))
                db.session.commit()
                print(f"Added column {col} to user table.")
            except Exception:
                db.session.rollback()
                
        for col, col_type in booking_cols.items():
            try:
                db.session.execute(text(f'ALTER TABLE booking ADD COLUMN {col} {col_type}'))
                db.session.commit()
                print(f"Added column {col} to booking table.")
            except Exception:
                db.session.rollback()
    except Exception as e:
        print(f"Migration helper error: {e}")

# Simplified initialization
with app.app_context():
    try:
        # Just create tables if they don't exist
        db.create_all()
        
        # Run our simple migration check
        ensure_columns_exist()
        
        # Attempt to expand password column for existing Postgres databases
        try:
            db.session.execute(text('ALTER TABLE "user" ALTER COLUMN password TYPE VARCHAR(255)'))
            db.session.commit()
        except Exception:
            db.session.rollback()
        
        # Check seats once - use a simpler check
        if Seat.query.limit(1).count() == 0:
            print("Initializing first-time seats...")
            for i in range(1, 66):
                db.session.add(Seat(id=str(i)))
            
            if not User.query.filter_by(is_admin=True).first():
                admin_username = os.environ.get('ADMIN_USER', 'admin')
                admin_password = os.environ.get('ADMIN_PASS', 'admin123')
                hashed_pw = generate_password_hash(admin_password)
                db.session.add(User(
                    username=admin_username, email='admin@vrs.com', 
                    password=hashed_pw, name='VRS Admin', phone='0000000000', 
                    is_active=True, is_admin=True, status='active'
                ))
            db.session.commit()
            print("Database setup complete.")
    except Exception as e:
        print(f"Startup check failed: {e}")
        # In Vercel, we don't want to crash the whole app on startup if DB is momentarily down
        # but we should log it.
        traceback.print_exc()

@app.route('/health')
def health_check():
    try:
        db.session.execute(text('SELECT 1'))
        return jsonify({'status': 'healthy', 'database': 'connected', 'vercel': bool(os.environ.get('VERCEL'))}), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.errorhandler(Exception)
def handle_exception(e):
    # Pass through standard HTTP errors (like 404) without flashing
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException) and e.code == 404:
        return e
        
    # Log the traceback for real crashes
    print("!!! GLOBAL ERROR CAUGHT !!!")
    traceback.print_exc()
    
    # Check if it's an API request
    if request.path.startswith('/api/'):
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
        
    # Standard request - only flash if it's not a standard 404
    flash(f'System Error: {str(e)}', 'danger')
    return redirect(url_for('index'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Admin Dashboard Routes ---
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return redirect(url_for('membership'))
    
    from sqlalchemy import func
    # Consolidate user stats into one query
    user_counts = db.session.query(User.status, func.count(User.id)).filter(User.is_admin == False).group_by(User.status).all()
    user_counts_dict = dict(user_counts)
    
    # Consolidate booking stats into one query
    booking_counts = db.session.query(Booking.status, func.count(Booking.id)).group_by(Booking.status).all()
    booking_counts_dict = dict(booking_counts)
    
    stats = {
        'pending_users': user_counts_dict.get('pending', 0),
        'active_members': user_counts_dict.get('active', 0),
        'frozen_members': user_counts_dict.get('frozen', 0),
        'total_seats': 65, # Hardcoded as it's static
        'pending_bookings': booking_counts_dict.get('pending', 0),
        'active_bookings': booking_counts_dict.get('approved', 0)
    }
    
    pending_users = User.query.filter_by(status='pending', is_admin=False).order_by(User.id.desc()).all()
    
    # Fetch all users and their approved bookings
    # We'll group them in Python to avoid duplicates in the UI
    all_users = User.query.filter_by(is_admin=False).order_by(User.name).all()
    all_approved_bookings = Booking.query.filter_by(status='approved').all()
    
    # Map user_id to their booking for quick lookup
    booking_map = {b.user_id: b for b in all_approved_bookings}
    
    active_users_data = []
    for user in all_users:
        active_booking = booking_map.get(user.id)
        active_users_data.append({
            'id': user.id,
            'name': user.name,
            'username': user.username,
            'phone': user.phone,
            'email': user.email,
            'profile_photo': user.profile_photo,
            'is_active': user.is_active,
            'status': user.status,
            'purpose': user.purpose,
            'start_date': active_booking.start_date.strftime('%d %b %Y') if active_booking and active_booking.start_date else None,
            'expires_at': active_booking.expires_at.strftime('%d %b %Y') if active_booking and active_booking.expires_at else 'No Expiry',
            'amount': active_booking.amount if active_booking else 0,
            'admin_note_1': user.admin_note_1,
            'booking': active_booking.seat_id if active_booking else None,
            'shift': active_booking.shift if active_booking else None
        })

    # Fetch recent logs
    recent_logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(50).all()

    return render_template('admin_dashboard.html', 
                           stats=stats, 
                           pending_users=pending_users, 
                           active_users=active_users_data,
                           logs=recent_logs)

@app.route('/api/admin/export_finance', methods=['GET'])
@login_required
def export_finance():
    if not current_user.is_admin: return jsonify({'success': False}), 403
    
    month_str = request.args.get('month') # Format YYYY-MM or 'all'
    
    try:
        if month_str and month_str != 'all':
            year, month = map(int, month_str.split('-'))
            start_of_month = datetime(year, month, 1)
            if month == 12:
                end_of_month = datetime(year + 1, 1, 1)
            else:
                end_of_month = datetime(year, month + 1, 1)
            
            from sqlalchemy import and_
            # Use a join or similar to get both user and booking info for that month
            bookings = Booking.query.filter(
                and_(Booking.start_date >= start_of_month, Booking.start_date < end_of_month)
            ).all()
            export_title = f"Finance_{month_str}"
            
            data = []
            for b in bookings:
                data.append({
                    'Name': b.user.name,
                    'Username': b.user.username,
                    'Phone': b.user.phone,
                    'Email': b.user.email or 'N/A',
                    'Father\'s Name': b.user.fathers_name or 'N/A',
                    'Address': b.user.address or 'N/A',
                    'Purpose': b.user.purpose or 'N/A',
                    'Seat ID': b.seat_id,
                    'Shift': b.shift.capitalize(),
                    'Fees Paid': b.amount or 0,
                    'Start Date': b.start_date.strftime('%d %b %Y') if b.start_date else 'N/A',
                    'Expiry Date': b.expires_at.strftime('%d %b %Y') if b.expires_at else 'N/A',
                    'Status': b.status.capitalize(),
                    'Note 1': b.user.admin_note_1 or '',
                    'Note 2': b.user.admin_note_2 or ''
                })
        else:
            # Universal Export: Every non-admin user in the system
            users = User.query.filter_by(is_admin=False).all()
            export_title = "Universal_Member_Directory"
            
            data = []
            for u in users:
                # Get their latest booking record if it exists
                b = Booking.query.filter_by(user_id=u.id).order_by(Booking.id.desc()).first()
                data.append({
                    'Name': u.name,
                    'Username': u.username,
                    'Phone': u.phone,
                    'Email': u.email or 'N/A',
                    'Father\'s Name': u.fathers_name or 'N/A',
                    'Address': u.address or 'N/A',
                    'Purpose': u.purpose or 'N/A',
                    'Seat ID': b.seat_id if b else 'None',
                    'Shift': b.shift.capitalize() if b else 'N/A',
                    'Fees Paid': b.amount if b else 0,
                    'Start Date': b.start_date.strftime('%d %b %Y') if b and b.start_date else 'N/A',
                    'Expiry Date': b.expires_at.strftime('%d %b %Y') if b and b.expires_at else 'N/A',
                    'User Status': u.status.capitalize(),
                    'Booking Status': b.status.capitalize() if b else 'None',
                    'Note 1': u.admin_note_1 or '',
                    'Note 2': u.admin_note_2 or ''
                })
        
        if not data:
            return jsonify({'success': False, 'message': 'No data found to export.'}), 404
            
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Member Data')
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f"VRS_{export_title}.xlsx"
        )
    except Exception as e:
        print(f"Export error: {e}")
        return jsonify({'success': False, 'message': 'Internal error during export'}), 500

@app.route('/api/admin/finance')
@login_required
def get_finance_stats():
    if not current_user.is_admin: return jsonify({'success': False}), 403
    
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    now = datetime.now(IST)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Current month revenue (IST comparison)
    current_month_total = db.session.query(func.sum(Booking.amount)).filter(
        Booking.created_at >= start_of_month.replace(tzinfo=None)
    ).scalar() or 0
    
    # Previous month revenue
    end_of_prev_month = start_of_month - timedelta(seconds=1)
    start_of_prev_month = end_of_prev_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    prev_month_total = db.session.query(func.sum(Booking.amount)).filter(
        Booking.created_at >= start_of_prev_month.replace(tzinfo=None),
        Booking.created_at <= end_of_prev_month.replace(tzinfo=None)
    ).scalar() or 0
    
    # Data for the chart (last 6 months)
    history = []
    for i in range(5, -1, -1):
        m_start = (start_of_month - timedelta(days=i*30)).replace(day=1)
        m_end = (m_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
        
        m_total = db.session.query(func.sum(Booking.amount)).filter(
            Booking.created_at >= m_start.replace(tzinfo=None),
            Booking.created_at <= m_end.replace(tzinfo=None)
        ).scalar() or 0
        
        history.append({
            'month': m_start.strftime('%b %Y'),
            'total': m_total
        })
    
    # Fetch all active users for the receipt list (to allow sending receipts to all current members)
    # We join with Booking to get their latest approved seat info
    active_users = User.query.filter_by(status='active').all()
    approved_list = []
    for u in active_users:
        # Get latest approved booking for this user
        b = Booking.query.filter_by(user_id=u.id, status='approved').order_by(Booking.id.desc()).first()
        if b:
            approved_list.append({
                'id': b.id,
                'user_name': safe_str(u.name),
                'phone': safe_str(u.phone),
                'amount': b.amount,
                'seat_id': b.seat_id,
                'shift': b.shift,
                'start_date': b.start_date.strftime('%d %b %Y') if b.start_date else 'N/A',
                'expiry_date': b.expires_at.strftime('%d %b %Y') if b.expires_at else 'N/A'
            })
    
    return jsonify({
        'current_month': current_month_total,
        'prev_month': prev_month_total,
        'history': history,
        'recent_approved': approved_list
    })

@app.route('/api/admin/send_receipt_whatsapp', methods=['POST'])
@login_required
def send_receipt_whatsapp():
    if not current_user.is_admin: return jsonify({'success': False}), 403
    data = request.get_json()
    booking_id = data.get('booking_id')
    booking = Booking.query.get(booking_id)
    if not booking: return jsonify({'success': False, 'message': 'Booking not found'}), 404
    
    # Format a professional receipt message
    message = f"🌟 *VRS DIGITAL LIBRARY - PAYMENT RECEIPT* 🌟\n\n" \
              f"Dear *{booking.user.name}*,\n" \
              f"Your membership allotment is successfully confirmed.\n\n" \
              f"📍 *Seat Number:* {booking.seat_id}\n" \
              f"🕒 *Shift:* {booking.shift.capitalize()}\n" \
              f"📅 *Validity:* {booking.start_date.strftime('%d %b %Y') if booking.start_date else 'Immediate'} to {booking.expires_at.strftime('%d %b %Y') if booking.expires_at else 'Permanent'}\n" \
              f"💰 *Amount Paid:* ₹{booking.amount or 0}\n\n" \
              f"Thank you for choosing VRS Digital Library. You can download your detailed PDF receipt from your dashboard anytime."

    # Process phone number
    phone = "".join(filter(str.isdigit, booking.user.phone))
    if len(phone) == 10: phone = "91" + phone
    
    token = os.environ.get('WHATSAPP_TOKEN')
    phone_id = os.environ.get('WHATSAPP_PHONE_ID')
    if not token or not phone_id:
        return jsonify({'success': False, 'message': 'WhatsApp credentials not configured.'}), 500

    url = f"https://graph.facebook.com/v17.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message}
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': response.json().get('error', {}).get('message', 'WhatsApp Error')}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/send_whatsapp', methods=['POST'])
@login_required
def send_whatsapp():
    if not current_user.is_admin: return jsonify({'success': False}), 403
    data = request.get_json()
    phone = data.get('phone')
    message = data.get('message')
    
    # Clean phone number (must be in international format without + or 00)
    phone = "".join(filter(str.isdigit, phone))
    if len(phone) == 10: phone = "91" + phone # Assume India if 10 digits
    
    token = os.environ.get('WHATSAPP_TOKEN')
    phone_id = os.environ.get('WHATSAPP_PHONE_ID')
    
    if not token or not phone_id:
        return jsonify({'success': False, 'message': 'WhatsApp credentials not configured.'}), 500

    url = f"https://graph.facebook.com/v17.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Note: Using text message. For production, you often need templates for first-time outreach.
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message}
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        res_data = response.json()
        if response.status_code == 200:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': res_data.get('error', {}).get('message', 'Unknown error')}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/approve_user/<int:user_id>')
@login_required
def approve_user(user_id):
    if not current_user.is_admin: return redirect(url_for('index'))
    user = User.query.get(user_id)
    if user:
        user.is_active = True
        user.status = 'active'
        db.session.commit()
        log_activity("User Approved", f"Account for {user.name} was approved by admin.", user_id=user.id)
        flash(f'Account for {user.name} approved successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

# --- Auth Routes ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            # Sanitize optional fields to store NULL instead of empty strings
            email = request.form.get('email', '').strip() or None
            purpose = request.form.get('purpose', '').strip() or 'Library Study'
            description = request.form.get('description', '').strip() or None
            phone = request.form.get('phone', '').strip()

            # Check if username or email (if provided) already exists
            user_query = User.query.filter(User.username == username)
            if email:
                user_query = User.query.filter(or_(User.username == username, User.email == email))
                
            if user_query.first():
                flash('Username or Email already exists.', 'danger')
                return redirect(url_for('register'))
                
            password = request.form.get('password', '').strip()
            hashed_password = generate_password_hash(password) if password else generate_password_hash('vrs123')

            new_user = User(
                username=username, email=email, password=hashed_password, 
                name=request.form.get('name'), phone=phone, 
                purpose=purpose, description=description, 
                status='pending'
            )
            db.session.add(new_user)
            db.session.commit()
            
            log_activity("New Registration", f"New user {new_user.name} (@{new_user.username}) registered.", user_id=new_user.id)
                
            flash('Registration successful! Please wait for admin approval.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error during registration: {str(e)}', 'danger')
            return redirect(url_for('register'))
    return render_template('register.html')

@app.route('/api/upload_photo', methods=['POST'])
@login_required
def upload_photo():
    data = request.get_json()
    user_id = data.get('user_id')
    photo_data = data.get('photo') # Base64 string
    
    if not user_id or not photo_data:
        return jsonify({'success': False, 'message': 'Missing data'}), 400
        
    # Prevent DoS via massive payload (restrict to ~75KB base64 string)
    if len(photo_data) > 100000:
        return jsonify({'success': False, 'message': 'Image payload too large.'}), 413
        
    if not current_user.is_admin and current_user.id != int(user_id):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    user = User.query.get(user_id)
    if user:
        user.profile_photo = photo_data
        db.session.commit()
        log_activity("Profile Updated", f"User {user.name} updated their profile photo.", user_id=user.id)
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'User not found'}), 404

@app.route('/api/user/download_receipt')
@login_required
def download_receipt():
    # Fetch the approved booking for the current user
    booking = Booking.query.filter_by(user_id=current_user.id, status='approved').first()
    if not booking:
        return "No active booking found. You must have an allotted seat to download a receipt.", 404

    from io import BytesIO
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from flask import send_file

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # --- Header Design ---
    p.setStrokeColorRGB(0.26, 0.52, 0.96) # Accent Color
    p.setLineWidth(2)
    p.line(0.5*inch, height - 0.5*inch, width - 0.5*inch, height - 0.5*inch)
    
    p.setFont("Helvetica-Bold", 28)
    p.setFillColorRGB(0.12, 0.16, 0.23) # Dark Blue/Slate
    p.drawCentredString(width/2, height - 1.2*inch, "VRS DIGITAL LIBRARY")
    
    p.setFont("Helvetica", 12)
    p.setFillColorRGB(0.39, 0.44, 0.54) # Muted Text
    p.drawCentredString(width/2, height - 1.5*inch, "Premium Membership Allotment Receipt")
    
    p.setLineWidth(1)
    p.setStrokeColorRGB(0.89, 0.91, 0.94) # Light Border
    p.line(1*inch, height - 1.8*inch, width - 1*inch, height - 1.8*inch)

    # --- Body Content ---
    y_start = height - 2.3*inch
    
    # Member Section Box
    p.setFillColorRGB(0.97, 0.98, 1.0) # Very Light Blue BG
    p.rect(1*inch, y_start - 1.5*inch, width - 2*inch, 1.7*inch, fill=1, stroke=0)
    
    p.setFillColorRGB(0.12, 0.16, 0.23)
    p.setFont("Helvetica-Bold", 14)
    p.drawString(1.2*inch, y_start, "MEMBER INFORMATION")
    
    p.setFont("Helvetica", 11)
    y = y_start - 0.4*inch
    p.drawString(1.4*inch, y, f"Full Name: {current_user.name}")
    y -= 0.25*inch
    p.drawString(1.4*inch, y, f"Username: @{current_user.username}")
    y -= 0.25*inch
    p.drawString(1.4*inch, y, f"Contact: {current_user.phone}")
    y -= 0.25*inch
    p.drawString(1.4*inch, y, f"Address: {current_user.address or 'Contact details on file'}")

    # Allotment Section
    y_start_2 = y - 0.8*inch
    p.setFillColorRGB(0.12, 0.16, 0.23)
    p.setFont("Helvetica-Bold", 14)
    p.drawString(1.2*inch, y_start_2, "ALLOTMENT DETAILS")
    
    # Table Header BG
    p.setFillColorRGB(0.26, 0.52, 0.96)
    p.rect(1.2*inch, y_start_2 - 0.4*inch, width - 2.4*inch, 0.3*inch, fill=1, stroke=0)
    
    p.setFillColorRGB(1, 1, 1)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(1.3*inch, y_start_2 - 0.3*inch, "DESCRIPTION")
    p.drawRightString(width - 1.3*inch, y_start_2 - 0.3*inch, "DETAILS")
    
    p.setFillColorRGB(0.12, 0.16, 0.23)
    p.setFont("Helvetica", 11)
    y = y_start_2 - 0.6*inch
    
    items = [
        ("Seat Assigned", f"Seat Number {booking.seat_id}"),
        ("Shift Selection", f"{booking.shift.capitalize()} Shift"),
        ("Commencement Date", booking.start_date.strftime('%d %b %Y') if booking.start_date else 'Immediate'),
        ("Membership Expiry", booking.expires_at.strftime('%d %b %Y') if booking.expires_at else 'Permanent'),
        ("Total Amount Paid", f"INR {booking.amount or 0}.00")
    ]
    
    for label, val in items:
        p.drawString(1.3*inch, y, label)
        p.drawRightString(width - 1.3*inch, y, val)
        p.setStrokeColorRGB(0.95, 0.96, 0.97)
        p.line(1.2*inch, y - 0.1*inch, width - 1.2*inch, y - 0.1*inch)
        y -= 0.35*inch

    # --- Footer ---
    p.setFont("Helvetica-Oblique", 9)
    p.setFillColorRGB(0.5, 0.5, 0.5)
    p.drawCentredString(width/2, 1.2*inch, "This is an electronically generated document. No physical signature is required.")
    p.setFont("Helvetica", 8)
    p.drawCentredString(width/2, 1.0*inch, f"Generated by VRS Management System on {datetime.now(IST).strftime('%d %b %Y, %I:%M %p')}")
    
    p.setStrokeColorRGB(0.26, 0.52, 0.96)
    p.line(0.5*inch, 0.7*inch, width - 0.5*inch, 0.7*inch)

    p.showPage()
    p.save()

    buffer.seek(0)
    filename = f"Receipt_{current_user.username}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

@app.route('/api/user/update_profile', methods=['POST'])
@login_required
def update_profile():
    data = request.get_json()
    user = User.query.get(current_user.id)
    if not user: return jsonify({'success': False}), 404
    
    # Allow users to update specific fields
    user.username = data.get('username', user.username)
    user.phone = data.get('phone', user.phone)
    user.fathers_name = data.get('fathers_name', user.fathers_name)
    user.address = data.get('address', user.address)
    user.email = data.get('email', user.email)
    
    db.session.commit()
    log_activity("Profile Updated", f"User {user.name} updated their profile details.", user_id=user.id)
    return jsonify({'success': True})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_id = request.form.get('login_id').strip()
        password = request.form.get('password').strip()
        from sqlalchemy import func
        user = User.query.filter(
            (func.lower(User.username) == login_id.lower()) | 
            (func.lower(User.email) == login_id.lower()) | 
            (User.phone == login_id)
        ).first()
        
        if user:
            # Check for hashed match
            is_valid = check_password_hash(user.password, password)
            
            if is_valid:
                if not user.is_active:
                    flash('Your account is pending admin approval.', 'warning')
                    return redirect(url_for('login'))
                login_user(user)
                log_activity("Login", f"{'Admin' if user.is_admin else 'Member'} {user.name} logged in.", user_id=user.id)
                return redirect(url_for('admin_dashboard') if user.is_admin else url_for('membership'))
            else:
                print(f"Password mismatch for user: {login_id}")
        else:
            print(f"User not found: {login_id}")
            
        flash('Login failed. Check your ID and password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/membership')
@login_required
def membership():
    if current_user.is_admin and request.args.get('enroll') == 'true':
        logout_user()
        flash('Logged out as admin to allow membership browsing.', 'info')
        return redirect(url_for('membership'))
    return render_template('membership.html')

@app.route('/api/seats')
@login_required
def get_seats():
    shift = request.args.get('shift', 'morning')
    is_admin = current_user.is_admin
    now = datetime.now(IST)
    
    # Expiry Check - Optimized to avoid N commits
    # For morning, we also care about full day
    # For evening, we also care about full day
    # For full day, we care about morning, evening, and full
    if shift == 'morning':
        shift_filter = ['morning', 'full']
    elif shift == 'evening':
        shift_filter = ['evening', 'full']
    else: # full
        shift_filter = ['morning', 'evening', 'full']
        
    all_active = Booking.query.filter(Booking.shift.in_(shift_filter), Booking.status == 'approved').all()
    expired_count = 0
    for b in all_active:
        if b.expires_at:
            expires = b.expires_at
            if expires.tzinfo is None: expires = IST.localize(expires)
            if expires < now:
                db.session.delete(b)
                expired_count += 1
    
    if expired_count > 0:
        db.session.commit()

    # Use joinedload to fetch user details along with bookings in one query
    from sqlalchemy.orm import joinedload
    bookings = Booking.query.filter(Booking.shift.in_(shift_filter)).options(joinedload(Booking.user)).all()
    seat_map = {}
    for b in bookings:
        if b.seat_id not in seat_map: seat_map[b.seat_id] = {'approved': None, 'pending': []}
        data = {
            'id': b.id, 
            'user_id': b.user_id, 
            'user': safe_str(b.user.name), 
            'phone': safe_str(b.user.phone), 
            'purpose': safe_str(b.user.purpose), 
            'status': b.status,
            'requested_plan': b.requested_plan,
            'expires_at': b.expires_at.strftime('%d %b %Y') if b.expires_at else 'Permanent',
            'profile_photo': b.user.profile_photo,
            'amount': b.amount,
            'comment': b.user.admin_note_1
        }
        if b.status == 'approved': seat_map[b.seat_id]['approved'] = data
        else: seat_map[b.seat_id]['pending'].append(data)

    # Ensure seats are initialized if they are missing
    if Seat.query.count() != 65:
        for i in range(1, 66):
            if not Seat.query.get(str(i)):
                db.session.add(Seat(id=str(i)))
        db.session.commit()

    all_seats = Seat.query.all()
    # Sort numerically
    def seat_sort_key(s):
        try:
            return int(s.id)
        except:
            return 0
    
    seats = sorted(all_seats, key=seat_sort_key)
    result = []
    for s in seats:
        state = seat_map.get(s.id, {'approved': None, 'pending': []})
        
        if is_admin:
            result.append({
                'id': s.id, 
                'status': 'approved' if state['approved'] else ('pending' if state['pending'] else 'available'),
                'approved_user': state['approved'], 
                'pending_requests': state['pending']
            })
        else:
            # USER VIEW LOGIC
            # If I am the approved owner -> Green (my-seat)
            if state['approved'] and state['approved']['user_id'] == current_user.id:
                final_status = 'my-seat'
                user_name = 'Your Seat'
            # If someone else is approved -> Red (booked)
            elif state['approved']:
                final_status = 'booked'
                user_name = 'Occupied'
            # If I have a pending request -> Yellow (pending)
            elif any(p['user_id'] == current_user.id for p in state['pending']):
                final_status = 'pending'
                user_name = 'Requested'
            # Otherwise -> Available
            else:
                final_status = 'available'
                user_name = 'Vacant'
                
            result.append({
                'id': s.id, 
                'status': final_status,
                'user': user_name
            })
    return jsonify(result)

@app.route('/api/book', methods=['POST'])
@login_required
def book_seat():
    data = request.get_json()
    seat_id = data.get('seat_id')
    shift = data.get('shift')
    
    # RULE: One user can only have ONE active request or booking across ALL shifts
    existing = Booking.query.filter_by(user_id=current_user.id).first()
    if existing:
        return jsonify({'success': False, 'message': 'You already have a seat request or booking. Please cancel it before making a new one.'}), 400
        
    if shift == 'morning':
        conflicting_shifts = ['morning', 'full']
    elif shift == 'evening':
        conflicting_shifts = ['evening', 'full']
    else: # full
        conflicting_shifts = ['morning', 'evening', 'full']
        
    if Booking.query.filter(Booking.seat_id == seat_id, Booking.shift.in_(conflicting_shifts), Booking.status == 'approved').first():
        return jsonify({'success': False, 'message': 'Seat already booked for a conflicting shift.'}), 400
        
    if current_user.status != 'active':
        return jsonify({'success': False, 'message': f'Your account is {current_user.status}. Only active members can make seat requests.'}), 403
        
    plan = data.get('plan', '1 Month')
    new_booking = Booking(seat_id=seat_id, user_id=current_user.id, shift=shift, status='pending', requested_plan=plan)
    db.session.add(new_booking)
    db.session.commit()
    log_activity("Seat Requested", f"User requested seat {seat_id} ({shift}).", user_id=current_user.id)
    return jsonify({'success': True})

@app.route('/api/admin/approve', methods=['POST'])
@login_required
def approve_booking():
    if not current_user.is_admin: return jsonify({'success': False}), 403
    try:
        data = request.get_json()
        booking = Booking.query.get(data.get('booking_id'))
        if booking:
            # Allow admin to change seat/shift/amount during approval
            booking.seat_id = str(data.get('seat_id', booking.seat_id))
            booking.shift = data.get('shift', booking.shift)
            booking.amount = int(data.get('amount', booking.amount or 0))
            
            start = data.get('start_date')
            if start:
                try:
                    booking.start_date = datetime.strptime(start, '%Y-%m-%d')
                except: pass
                
            expiry = data.get('expiry_date')
            if expiry:
                try:
                    try:
                        expiry_date = datetime.strptime(expiry, '%Y-%m-%d')
                    except:
                        expiry_date = datetime.fromisoformat(expiry.replace(' ', 'T'))
                    booking.expires_at = expiry_date
                except Exception as e:
                    print(f"Approval date error: {e}")
            else:
                booking.expires_at = datetime.now(IST).replace(tzinfo=None) + timedelta(days=30)

            booking.status = 'approved'
            
            # Cross-shift conflict cleanup
            if booking.shift == 'morning':
                conflicting_shifts = ['morning', 'full']
            elif booking.shift == 'evening':
                conflicting_shifts = ['evening', 'full']
            else: # full
                conflicting_shifts = ['morning', 'evening', 'full']
                
            others = Booking.query.filter(
                Booking.seat_id == booking.seat_id, 
                Booking.shift.in_(conflicting_shifts), 
                Booking.status == 'pending', 
                Booking.id != booking.id
            ).all()
            for o in others: db.session.delete(o)
            
            # Remove user from waiting room if they are in there
            WaitingRoom.query.filter_by(user_id=booking.user_id).delete()
            
            db.session.commit()
            log_activity("Booking Approved", f"Seat {booking.seat_id} ({booking.shift}) approved for {booking.user.name} at ₹{booking.amount}.", user_id=booking.user_id)
            return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': False}), 404

@app.route('/api/admin/reject', methods=['POST'])
@login_required
def reject_booking():
    if not current_user.is_admin: return jsonify({'success': False}), 403
    try:
        data = request.get_json()
        booking = Booking.query.get(data.get('booking_id'))
        if booking:
            user_name = booking.user.name
            user_id = booking.user_id
            db.session.delete(booking)
            db.session.commit()
            log_activity("Booking Rejected", f"Seat request for {user_name} was rejected.", user_id=user_id)
            return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': False}), 404

@app.route('/api/admin/remove', methods=['POST'])
@login_required
def remove_seat():
    if not current_user.is_admin: return jsonify({'success': False}), 403
    try:
        data = request.get_json()
        booking = Booking.query.filter_by(seat_id=data.get('seat_id'), shift=data.get('shift'), status='approved').first()
        if booking:
            user_id = booking.user_id
            seat_id = booking.seat_id
            
            # Check if user already in waiting room
            if not WaitingRoom.query.filter_by(user_id=user_id).first():
                wait = WaitingRoom(user_id=user_id, removed_from_seat=seat_id)
                db.session.add(wait)
            
            db.session.delete(booking)
            db.session.commit()
            log_activity("Seat Removed", f"User removed from seat {seat_id}.", user_id=user_id)
            return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': False}), 404

@app.route('/api/waiting_room')
@login_required
def get_waiting_room():
    waiting = WaitingRoom.query.all()
    return jsonify([{'user_name': w.user.name, 'seat': w.removed_from_seat} for w in waiting])

# --- Admin Member Management API ---
@app.route('/api/admin/user/<int:user_id>', methods=['GET'])
@login_required
def get_user_details(user_id):
    if not current_user.is_admin: return jsonify({'success': False}), 403
    user = User.query.get(user_id)
    if not user: return jsonify({'success': False}), 404
    
    # Get active booking if any
    booking = Booking.query.filter_by(user_id=user.id, status='approved').first()
    
    return jsonify({
        'id': user.id,
        'username': user.username,
        'name': user.name,
        'phone': user.phone,
        'email': user.email,
        'is_active': user.is_active,
        'profile_photo': user.profile_photo,
        'admin_note_1': user.admin_note_1,
        'admin_note_2': user.admin_note_2,
        'fathers_name': user.fathers_name or '',
        'address': user.address or '',
        'booking_id': booking.id if booking else None,
        'expires_at': booking.expires_at.strftime('%Y-%m-%dT%H:%M') if booking and booking.expires_at else None,
        'start_date': booking.start_date.strftime('%Y-%m-%dT%H:%M') if booking and booking.start_date else None,
        'seat_id': booking.seat_id if booking else '',
        'shift': booking.shift if booking else 'morning',
        'amount': booking.amount if booking else get_default_amount('morning'),
        'status': user.status
    })

@app.route('/api/admin/check_seat', methods=['POST'])
@login_required
def check_seat():
    if not current_user.is_admin: return jsonify({'success': False}), 403
    data = request.get_json()
    seat_id = str(data.get('seat_id'))
    shift = data.get('shift', 'morning')
    user_id = data.get('user_id')
    
    if not seat_id or seat_id == '': return jsonify({'available': True})
    
    # Check if seat is taken by ANY OTHER user in the same shift
    # Cross-shift availability check
    if shift == 'morning':
        conflicting_shifts = ['morning', 'full']
    elif shift == 'evening':
        conflicting_shifts = ['evening', 'full']
    else: # full
        conflicting_shifts = ['morning', 'evening', 'full']

    existing_conflict = Booking.query.filter(
        Booking.seat_id == str(seat_id),
        Booking.shift.in_(conflicting_shifts),
        Booking.status == 'approved',
        Booking.user_id != user_id
    ).first()
    
    if existing_conflict:
        return jsonify({
            'available': False, 
            'owner': safe_str(existing_conflict.user.name),
            'owner_shift': safe_str(existing_conflict.shift)
        })
    return jsonify({'available': True})

@app.route('/api/admin/user/add', methods=['POST'])
@login_required
def add_user_admin():
    if not current_user.is_admin: return jsonify({'success': False}), 403
    data = request.get_json()
    
    username = data.get('username', '').strip()
    if not username: return jsonify({'success': False, 'message': 'Username is required'}), 400
    
    # Check if username or email exists
    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'Username already exists'}), 400
        
    email = data.get('email', '').strip() or None
    if email and User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': 'Email already exists'}), 400
        
    new_user = User(
        username=username,
        name=data.get('name'),
        phone=data.get('phone'),
        email=email,
        password=generate_password_hash(data.get('password', 'vrs123')),
        fathers_name=data.get('fathers_name', '').strip() or None,
        address=data.get('address', '').strip() or None,
        purpose=data.get('purpose', 'Library Study'),
        admin_note_1=data.get('note_1'),
        admin_note_2=data.get('note_2'),
        profile_photo=data.get('photo'),
        status='active',
        is_active=True
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    # Handle Optional Seat Allotment
    seat_id = data.get('seat_id')
    if seat_id:
        from datetime import datetime
        try:
            start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d') if data.get('start_date') else datetime.now()
            expiry_date = datetime.strptime(data.get('expiry_date'), '%Y-%m-%d') if data.get('expiry_date') else (start_date + timedelta(days=30))
            
            booking = Booking(
                user_id=new_user.id,
                seat_id=str(seat_id),
                shift=data.get('shift', 'morning'),
                amount=int(data.get('amount') or 400),
                status='approved',
                start_date=start_date,
                expires_at=expiry_date
            )
            db.session.add(booking)
            db.session.commit()
            log_activity("Seat Allotted", f"Admin allotted seat {seat_id} to new user {new_user.name} during creation.", user_id=new_user.id)
        except Exception as e:
            print(f"Allotment error during creation: {e}")
            # User is still created, but allotment failed. Admin can fix in edit.
    
    log_activity("Admin Created User", f"Admin created new member {new_user.name} (@{new_user.username}).", user_id=new_user.id)
    return jsonify({'success': True})

@app.route('/api/admin/user/update', methods=['POST'])
@login_required
def update_user():
    if not current_user.is_admin: return jsonify({'success': False}), 403
    try:
        data = request.get_json()
        user = User.query.get(data.get('user_id'))
        if not user: return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # BLOCK EDITING FOR PENDING USERS
        if user.status == 'pending':
            return jsonify({'success': False, 'message': 'Cannot edit details for a pending user. Please approve them first.'}), 400
        
        user.name = data.get('name', user.name)
        user.phone = data.get('phone', user.phone)
        user.username = data.get('username', user.username)
        user.email = data.get('email', user.email)
        user.admin_note_1 = data.get('admin_note_1', user.admin_note_1)
        user.admin_note_2 = data.get('admin_note_2', user.admin_note_2)
        user.fathers_name = data.get('fathers_name', user.fathers_name)
        user.address = data.get('address', user.address)
        
        # Status management: pending -> active/frozen
        is_active_toggle = bool(data.get('is_active'))
        if user.status != 'pending':
            new_status = 'active' if is_active_toggle else 'frozen'
            
            # RULE: When frozen, all allotted seats are freed and membership canceled
            if new_status == 'frozen' and user.status == 'active':
                Booking.query.filter_by(user_id=user.id).delete()
            
            user.status = new_status
        
        user.is_active = is_active_toggle # Keep legacy boolean for compatibility
        
        new_password = data.get('password')
        if new_password:
            user.password = generate_password_hash(new_password.strip())
        
        if data.get('profile_photo'):
            user.profile_photo = data.get('profile_photo')
            
        # Status Logic: If freezing an active member, clear their seat
        new_is_active = data.get('is_active')
        new_status = 'active' if new_is_active else 'frozen'
        
        if new_status == 'frozen' and user.status == 'active':
            Booking.query.filter_by(user_id=user.id).delete()
            log_activity("Seat Cleared", f"User {user.name} was frozen; seat assignment removed.", user_id=user.id)

        if user.status != new_status:
            # SAFETY CHECK: Cannot manually activate a PENDING user via Update.
            # They must use the formal Approve route.
            if user.status == 'pending' and new_status == 'active':
                return jsonify({'success': False, 'message': 'Pending users must be activated via the official "Approve" button on the dashboard.'}), 400
                
            log_activity("Status Changed", f"User status changed from {user.status} to {new_status}.", user_id=user.id)
            user.status = new_status
            user.is_active = new_is_active

        # Update seat_id and shift - ONLY if the user is (or remains) ACTIVE
        seat_id = data.get('seat_id')
        shift = data.get('shift', 'morning')
        
        if seat_id and new_status == 'active':
            # Ensure only ONE approved booking exists
            all_user_bookings = Booking.query.filter_by(user_id=user.id, status='approved').all()
            if len(all_user_bookings) > 0:
                booking = all_user_bookings[0]
                if len(all_user_bookings) > 1:
                    for extra in all_user_bookings[1:]: db.session.delete(extra)
            else:
                booking = None
                
            if not booking:
                booking = Booking(user_id=user.id, seat_id=str(seat_id), shift=shift, status='approved')
                booking.amount = data.get('amount') or get_default_amount(shift)
                db.session.add(booking)
            else:
                booking.seat_id = str(seat_id)
                booking.shift = shift
                booking.status = 'approved'
                try:
                    booking.amount = int(data.get('amount') or 0)
                except:
                    booking.amount = 0
                
                if not booking.amount:
                    booking.amount = get_default_amount(shift)
                
            if data.get('expires_at'):
                try:
                    expiry_str = data.get('expires_at')
                    booking.expires_at = datetime.fromisoformat(expiry_str.replace(' ', 'T'))
                except: pass
            
            if data.get('start_date'):
                try:
                    start_str = data.get('start_date')
                    booking.start_date = datetime.fromisoformat(start_str.replace(' ', 'T'))
                except: pass
        elif seat_id and new_status != 'active':
            # If they are trying to ALLOT a seat to a non-active user (who wasn't just frozen)
            # we should block it. But if they just froze the user, we ignore the seat_id in payload.
            pass

        db.session.commit()
        log_activity("Profile Updated", f"Admin updated profile for {user.name}.", user_id=user.id)
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        print(f"Update error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/user/delete', methods=['POST'])
@login_required
def delete_user():
    if not current_user.is_admin: return jsonify({'success': False}), 403
    data = request.get_json()
    user = User.query.get(data.get('user_id'))
    if user and not user.is_admin:
        user_name = user.name
        db.session.delete(user)
        db.session.commit()
        log_activity("User Deleted", f"Member {user_name} was removed from system.")
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Cannot delete admin or user not found'})

if __name__ == '__main__':
    # Schema updated: fathers_name, address, start_date added.
    # Library added: reportlab
    app.run(debug=True, port=9090)
