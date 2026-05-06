import os
from datetime import datetime, timedelta
import pytz
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///library.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

IST = pytz.timezone('Asia/Kolkata')

# Models
class Seat(db.Model):
    id = db.Column(db.String(10), primary_key=True)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    seat_id = db.Column(db.String(10), db.ForeignKey('seat.id'), nullable=False)
    user_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15))
    email = db.Column(db.String(100))
    purpose = db.Column(db.String(50))
    other_description = db.Column(db.Text)
    shift = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='pending') # pending, approved
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(IST))
    expires_at = db.Column(db.DateTime)

class WaitingRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(100), nullable=False)
    removed_from_seat = db.Column(db.String(10))

with app.app_context():
    db.create_all()
    if Seat.query.count() == 0:
        for col in range(1, 5):
            for row in range(1, 21):
                new_seat = Seat(id=f"A{col}-{row}")
                db.session.add(new_seat)
        db.session.commit()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/membership')
def membership():
    is_admin = request.args.get('admin') == 'true'
    return render_template('membership.html', is_admin=is_admin)

@app.route('/api/seats')
def get_seats():
    shift = request.args.get('shift', 'morning')
    is_admin = request.args.get('admin') == 'true'
    
    # 1. Check for expired bookings
    now = datetime.now(IST)
    all_bookings = Booking.query.filter_by(shift=shift).all()
    for b in all_bookings:
        if b.expires_at:
            expires = b.expires_at
            if expires.tzinfo is None:
                expires = IST.localize(expires)
            if expires < now:
                db.session.delete(b)
                db.session.commit()

    # 2. Group bookings by seat_id
    bookings = Booking.query.filter_by(shift=shift).all()
    seat_map = {}
    for b in bookings:
        if b.seat_id not in seat_map:
            seat_map[b.seat_id] = {'approved': None, 'pending': []}
        
        data = {
            'id': b.id,
            'user': b.user_name,
            'phone': b.phone,
            'email': b.email,
            'purpose': b.purpose,
            'desc': b.other_description,
            'status': b.status
        }
        
        if b.status == 'approved':
            seat_map[b.seat_id]['approved'] = data
        else:
            seat_map[b.seat_id]['pending'].append(data)

    # 3. Build Result
    seats = Seat.query.order_by(Seat.id).all()
    result = []
    for s in seats:
        state = seat_map.get(s.id, {'approved': None, 'pending': []})
        
        # Admin gets full data, User gets simplified
        if is_admin:
            result.append({
                'id': s.id,
                'status': 'approved' if state['approved'] else ('pending' if state['pending'] else 'available'),
                'approved_user': state['approved'],
                'pending_requests': state['pending']
            })
        else:
            # Users see 'Red' if approved, but can still request if 'Pending'
            result.append({
                'id': s.id,
                'status': 'approved' if state['approved'] else 'available',
                'user': state['approved']['user'] if state['approved'] else None
            })
    return jsonify(result)

@app.route('/api/book', methods=['POST'])
def book_seat():
    data = request.get_json()
    seat_id = data.get('seat_id')
    user_name = data.get('user_name')
    shift = data.get('shift')
    
    # Block if already approved
    approved = Booking.query.filter_by(seat_id=seat_id, shift=shift, status='approved').first()
    if approved:
        return jsonify({'success': False, 'message': 'This seat is already booked.'}), 400
    
    # Allow multiple pending requests
    new_booking = Booking(
        seat_id=seat_id, 
        user_name=user_name,
        phone=data.get('phone'),
        email=data.get('email'),
        purpose=data.get('purpose'),
        other_description=data.get('desc'),
        shift=shift, 
        status='pending'
    )
    db.session.add(new_booking)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/admin/approve', methods=['POST'])
def approve_booking():
    data = request.get_json()
    booking_id = data.get('booking_id') # Use unique booking ID now
    expiry_str = data.get('expiry_date')
    
    booking = Booking.query.get(booking_id)
    if booking and booking.status == 'pending':
        # Approve this one
        booking.status = 'approved'
        if expiry_str:
            booking.expires_at = datetime.strptime(expiry_str, '%Y-%m-%d')
        else:
            booking.expires_at = datetime.now(IST).replace(tzinfo=None) + timedelta(days=30)
        
        # IMPORTANT: Delete ALL other pending requests for this seat and shift
        others = Booking.query.filter(
            Booking.seat_id == booking.seat_id,
            Booking.shift == booking.shift,
            Booking.status == 'pending',
            Booking.id != booking_id
        ).all()
        for other in others:
            db.session.delete(other)
            
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/api/admin/remove', methods=['POST'])
def remove_user():
    data = request.get_json()
    seat_id = data.get('seat_id')
    shift = data.get('shift')
    
    # Remove the approved one
    booking = Booking.query.filter_by(seat_id=seat_id, shift=shift, status='approved').first()
    if booking:
        wait = WaitingRoom(user_name=booking.user_name, removed_from_seat=seat_id)
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
