import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash

load_dotenv()
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from sqlalchemy import or_

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

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

IST = pytz.timezone('Asia/Kolkata')

# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    purpose = db.Column(db.String(100))
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)

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
    user = db.relationship('User', backref='bookings')

class WaitingRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(100), nullable=False)
    removed_from_seat = db.Column(db.String(10))

# Initialize Database
with app.app_context():
    try:
        db.create_all()
        if Seat.query.count() == 0:
            # A1: 15 seats
            for row in range(1, 16):
                db.session.add(Seat(id=f"A1-{row}"))
            # A2: 20 seats
            for row in range(1, 21):
                db.session.add(Seat(id=f"A2-{row}"))
            # A3: 20 seats
            for row in range(1, 21):
                db.session.add(Seat(id=f"A3-{row}"))
            # A4: 15 seats
            for row in range(1, 16):
                db.session.add(Seat(id=f"A4-{row}"))
            
            if not User.query.filter_by(is_admin=True).first():
                admin_username = os.environ.get('ADMIN_USER', 'admin')
                admin_password = os.environ.get('ADMIN_PASS', 'admin123')
                hashed_pw = bcrypt.generate_password_hash(admin_password).decode('utf-8')
                admin = User(
                    username=admin_username, 
                    email='admin@vrs.com', 
                    password=hashed_pw, 
                    name='VRS Admin', 
                    phone='0000000000', 
                    is_active=True, 
                    is_admin=True
                )
                db.session.add(admin)
            db.session.commit()
    except Exception as e:
        print(f"Error initializing database: {e}")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Admin Dashboard Routes ---
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return redirect(url_for('membership'))
    
    stats = {
        'pending_users': User.query.filter_by(is_active=False, is_admin=False).count(),
        'active_members': User.query.filter_by(is_active=True, is_admin=False).count(),
        'total_seats': Seat.query.count(),
        'pending_bookings': Booking.query.filter_by(status='pending').count(),
        'active_bookings': Booking.query.filter_by(status='approved').count()
    }
    
    pending_users = User.query.filter_by(is_active=False, is_admin=False).order_by(User.id.desc()).all()
    all_users = User.query.filter_by(is_admin=False).order_by(User.name).all()
    
    # Enrich users with booking info
    users_with_bookings = []
    for user in all_users:
        active_booking = Booking.query.filter_by(user_id=user.id, status='approved').first()
        users_with_bookings.append({
            'id': user.id,
            'name': user.name,
            'username': user.username,
            'phone': user.phone,
            'is_active': user.is_active,
            'purpose': user.purpose,
            'booking': active_booking.seat_id if active_booking else None,
            'shift': active_booking.shift if active_booking else None
        })

    return render_template('admin_dashboard.html', 
                           stats=stats, 
                           pending_users=pending_users, 
                           active_users=users_with_bookings)

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
        db.session.commit()
        flash(f'Account for {user.name} approved successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

# --- Auth Routes ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash('Username or Email already exists.', 'danger')
            return redirect(url_for('register'))
            
        hashed_pw = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
        new_user = User(
            username=username, email=email, password=hashed_pw, 
            name=request.form.get('name'), phone=request.form.get('phone'), 
            purpose=request.form.get('purpose'), description=request.form.get('description'), 
            is_active=False
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please wait for admin approval.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_id = request.form.get('login_id').strip()
        password = request.form.get('password').strip()
        user = User.query.filter((User.username == login_id) | (User.email == login_id)).first()
        
        if user:
            if bcrypt.check_password_hash(user.password, password):
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
    
    # Expiry Check
    all_active = Booking.query.filter_by(shift=shift, status='approved').all()
    for b in all_active:
        if b.expires_at:
            expires = b.expires_at
            if expires.tzinfo is None: expires = IST.localize(expires)
            if expires < now:
                db.session.delete(b)
                db.session.commit()

    bookings = Booking.query.filter_by(shift=shift).all()
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
    if Seat.query.count() == 0:
        # A1: 15 seats
        for row in range(1, 16):
            db.session.add(Seat(id=f"A1-{row}"))
        # A2: 20 seats
        for row in range(1, 21):
            db.session.add(Seat(id=f"A2-{row}"))
        # A3: 20 seats
        for row in range(1, 21):
            db.session.add(Seat(id=f"A3-{row}"))
        # A4: 15 seats
        for row in range(1, 16):
            db.session.add(Seat(id=f"A4-{row}"))
        db.session.commit()

    all_seats = Seat.query.all()
    # Sort logically: A1-1, A1-2, ..., A1-10, A2-1, ...
    def seat_sort_key(s):
        parts = s.id.split('-')
        prefix = parts[0] # e.g. "A1"
        num = int(parts[1]) if len(parts) > 1 else 0
        return (prefix, num)
    
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
    
    # RULE: One user can only have ONE active request or booking per shift
    existing = Booking.query.filter_by(user_id=current_user.id, shift=shift).first()
    if existing:
        return jsonify({'success': False, 'message': 'You already have a seat request or booking for this shift.'}), 400
        
    if Booking.query.filter_by(seat_id=seat_id, shift=shift, status='approved').first():
        return jsonify({'success': False, 'message': 'Seat already booked.'}), 400
        
    plan = data.get('plan', '1 Month')
    new_booking = Booking(seat_id=seat_id, user_id=current_user.id, shift=shift, status='pending', requested_plan=plan)
    db.session.add(new_booking)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/admin/approve', methods=['POST'])
@login_required
def approve_booking():
    if not current_user.is_admin: return jsonify({'success': False}), 403
    data = request.get_json()
    booking = Booking.query.get(data.get('booking_id'))
    if booking:
        booking.status = 'approved'
        expiry = data.get('expiry_date')
        booking.expires_at = datetime.strptime(expiry, '%Y-%m-%d') if expiry else datetime.now(IST).replace(tzinfo=None) + timedelta(days=30)
        others = Booking.query.filter(Booking.seat_id == booking.seat_id, Booking.shift == booking.shift, Booking.status == 'pending', Booking.id != booking.id).all()
        for o in others: db.session.delete(o)
        db.session.commit()
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
        db.session.delete(booking)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/api/waiting_room')
def get_waiting_room():
    waiting = WaitingRoom.query.all()
    return jsonify([{'user_name': w.user_name, 'seat': w.removed_from_seat} for w in waiting])

if __name__ == '__main__':
    app.run(debug=True, port=9090)
