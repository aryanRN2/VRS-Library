import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash

load_dotenv()
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, text
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'vrs-secret-key-development-only')

basedir = os.path.abspath(os.path.dirname(__file__))

if os.environ.get('DATABASE_URL'):
    # Fix for SQLAlchemy 1.4+ which requires 'postgresql://' instead of 'postgres://'
    db_url = os.environ.get('DATABASE_URL')
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
elif os.environ.get('VERCEL'):
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
    password = db.Column(db.String(60), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    purpose = db.Column(db.String(100))
    description = db.Column(db.Text)
    profile_photo = db.Column(db.Text, nullable=True) # Store compressed base64
    is_active = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='pending') # pending, active, frozen
    
    # Admin only comments
    admin_note_1 = db.Column(db.Text, nullable=True)
    admin_note_2 = db.Column(db.Text, nullable=True)
    
    # Relationship with Bookings (Cascade Delete ensures bookings are removed if user is deleted)
    bookings = db.relationship('Booking', backref='user', cascade='all, delete-orphan')

class Seat(db.Model):
    id = db.Column(db.String(10), primary_key=True)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    seat_id = db.Column(db.String(10), db.ForeignKey('seat.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    shift = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='pending') 
    requested_plan = db.Column(db.String(20), default='1 Month')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    expires_at = db.Column(db.DateTime)

class WaitingRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(100), nullable=False)
    removed_from_seat = db.Column(db.String(10))

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
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

# Simplified initialization
with app.app_context():
    try:
        # Just create tables if they don't exist
        db.create_all()
        
        # Check seats once - use a simpler check
        if Seat.query.limit(1).count() == 0:
            print("Initializing first-time seats...")
            for i in range(1, 66):
                db.session.add(Seat(id=str(i)))
            
            if not User.query.filter_by(is_admin=True).first():
                admin_username = os.environ.get('ADMIN_USER', 'admin')
                admin_password = os.environ.get('ADMIN_PASS', 'admin123')
                db.session.add(User(
                    username=admin_username, email='admin@vrs.com', 
                    password=admin_password, name='VRS Admin', phone='0000000000', 
                    is_active=True, is_admin=True, status='active'
                ))
            db.session.commit()
            print("Database setup complete.")
    except Exception as e:
        print(f"Startup check skipped: {e}")

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
            'expires_at': active_booking.expires_at.strftime('%Y-%m-%d %H:%M') if active_booking and active_booking.expires_at else 'No Expiry',
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
        username = request.form.get('username')
        email = request.form.get('email')
        
        # Check if username or email (if provided) already exists
        user_query = User.query.filter(User.username == username)
        if email:
            user_query = User.query.filter(or_(User.username == username, User.email == email))
            
        if user_query.first():
            flash('Username or Email already exists.', 'danger')
            return redirect(url_for('register'))
            
        password = request.form.get('password', '').strip()
        new_user = User(
            username=username, email=email, password=password, 
            name=request.form.get('name'), phone=request.form.get('phone'), 
            purpose=request.form.get('purpose'), description=request.form.get('description'), 
            is_active=False, status='pending'
        )
        db.session.add(new_user)
        db.session.commit()
        
        log_activity("New Registration", f"New user {new_user.name} (@{new_user.username}) registered.", user_id=new_user.id)
            
        flash('Registration successful! Please wait for admin approval.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/api/upload_photo', methods=['POST'])
def upload_photo():
    data = request.get_json()
    user_id = data.get('user_id')
    photo_data = data.get('photo') # Base64 string
    
    if not user_id or not photo_data:
        return jsonify({'success': False, 'message': 'Missing data'}), 400
        
    user = User.query.get(user_id)
    if user:
        user.profile_photo = photo_data
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'User not found'}), 404

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
            # Check for plain text match
            is_valid = (user.password == password)
            
            if is_valid:
                if not user.is_active:
                    flash('Your account is pending admin approval.', 'warning')
                    return redirect(url_for('login'))
                login_user(user)
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
            'user': b.user.name, 
            'phone': b.user.phone, 
            'purpose': b.user.purpose, 
            'status': b.status,
            'requested_plan': b.requested_plan,
            'expires_at': b.expires_at.strftime('%d %b %Y') if b.expires_at else 'Permanent'
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
    data = request.get_json()
    booking = Booking.query.get(data.get('booking_id'))
    if booking:
        expiry = data.get('expiry_date')
        if expiry:
            try:
                # Handle both YYYY-MM-DD and potentially datetime-local format
                try:
                    expiry_date = datetime.strptime(expiry, '%Y-%m-%d')
                except:
                    expiry_date = datetime.fromisoformat(expiry.replace(' ', 'T'))
                
                # SERVER-SIDE BLOCK: Prevent past dates
                if expiry_date.date() < datetime.now().date():
                    return jsonify({'success': False, 'message': 'Cannot allot a membership to a past date.'}), 400
                
                booking.expires_at = expiry_date
            except Exception as e:
                print(f"Approval date error: {e}")
        else:
            booking.expires_at = datetime.now(IST).replace(tzinfo=None) + timedelta(days=30)

        booking.status = 'approved'
        others = Booking.query.filter(Booking.seat_id == booking.seat_id, Booking.shift == booking.shift, Booking.status == 'pending', Booking.id != booking.id).all()
        for o in others: db.session.delete(o)
        db.session.commit()
        log_activity("Booking Approved", f"Seat {booking.seat_id} ({booking.shift}) approved for {booking.user.name}.", user_id=booking.user_id)
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/api/admin/reject', methods=['POST'])
@login_required
def reject_booking():
    if not current_user.is_admin: return jsonify({'success': False}), 403
    data = request.get_json()
    booking = Booking.query.get(data.get('booking_id'))
    if booking:
        user_name = booking.user.name
        user_id = booking.user_id
        db.session.delete(booking)
        db.session.commit()
        log_activity("Booking Rejected", f"Seat request for {user_name} was rejected.", user_id=user_id)
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/api/admin/remove', methods=['POST'])
@login_required
def remove_seat():
    if not current_user.is_admin: return jsonify({'success': False}), 403
    data = request.get_json()
    booking = Booking.query.filter_by(seat_id=data.get('seat_id'), shift=data.get('shift'), status='approved').first()
    if booking:
        wait = WaitingRoom(user_name=booking.user.name, removed_from_seat=booking.seat_id)
        db.session.add(wait)
        user_id = booking.user_id
        seat_id = booking.seat_id
        db.session.delete(booking)
        db.session.commit()
        log_activity("Seat Removed", f"User removed from seat {seat_id}.", user_id=user_id)
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/api/waiting_room')
def get_waiting_room():
    waiting = WaitingRoom.query.all()
    return jsonify([{'user_name': w.user_name, 'seat': w.removed_from_seat} for w in waiting])

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
        'password': user.password,
        'booking_id': booking.id if booking else None,
        'expires_at': booking.expires_at.strftime('%Y-%m-%dT%H:%M') if booking and booking.expires_at else None,
        'seat_id': booking.seat_id if booking else '',
        'shift': booking.shift if booking else 'morning',
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
            'owner': existing_conflict.user.name,
            'owner_shift': existing_conflict.shift
        })
    return jsonify({'available': True})

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
            user.password = new_password.strip()
        
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
                db.session.add(booking)
            else:
                booking.seat_id = str(seat_id)
                booking.shift = shift
                booking.status = 'approved'
                
            if data.get('expires_at'):
                try:
                    expiry_str = data.get('expires_at')
                    booking.expires_at = datetime.fromisoformat(expiry_str.replace(' ', 'T'))
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
    app.run(debug=True, port=9090)
