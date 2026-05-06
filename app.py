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
    bookings = Booking.query.filter_by(shift=shift).all()
    
    # Check for expired bookings
    now = datetime.now(IST)
    for b in bookings:
        if b.expires_at:
            # Handle naive/aware comparison
            expires = b.expires_at
            if expires.tzinfo is None:
                expires = IST.localize(expires)
            
            if expires < now:
                db.session.delete(b)
                db.session.commit()

    # Re-fetch after cleaning
    bookings = Booking.query.filter_by(shift=shift).all()
    booking_data = {b.seat_id: {'user': b.user_name, 'status': b.status} for b in bookings}
    
    seats = Seat.query.order_by(Seat.id).all()
    result = []
    for s in seats:
        result.append({
            'id': s.id,
            'user': booking_data.get(s.id, {}).get('user'),
            'status': booking_data.get(s.id, {}).get('status')
        })
    return jsonify(result)

@app.route('/api/book', methods=['POST'])
def book_seat():
    data = request.get_json()
    seat_id = data.get('seat_id')
    user_name = data.get('user_name')
    shift = data.get('shift')
    
    existing = Booking.query.filter_by(seat_id=seat_id, shift=shift).first()
    if existing:
        return jsonify({'success': False, 'message': 'Already booked/requested'}), 400
    
    new_booking = Booking(seat_id=seat_id, user_name=user_name, shift=shift, status='pending')
    db.session.add(new_booking)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/admin/approve', methods=['POST'])
def approve_booking():
    data = request.get_json()
    seat_id = data.get('seat_id')
    shift = data.get('shift')
    
    booking = Booking.query.filter_by(seat_id=seat_id, shift=shift, status='pending').first()
    if booking:
        booking.status = 'approved'
        booking.expires_at = datetime.now(IST) + timedelta(days=30)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/api/admin/remove', methods=['POST'])
def remove_user():
    data = request.get_json()
    seat_id = data.get('seat_id')
    shift = data.get('shift')
    
    booking = Booking.query.filter_by(seat_id=seat_id, shift=shift).first()
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
