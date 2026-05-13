import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

from app import app, db, User

with app.app_context():
    admin = User.query.filter_by(is_admin=True).first()
    if admin:
        admin.password = 'admin123'
        db.session.commit()
        print(f"Password for admin user '{admin.username}' reset to 'admin123'")
    else:
        print("No admin user found. Creating one...")
        admin = User(
            username='admin', 
            email='admin@vrs.com', 
            password='admin123', 
            name='VRS Admin', 
            phone='0000000000', 
            is_active=True, 
            is_admin=True,
            status='active'
        )
        db.session.add(admin)
        db.session.commit()
        print("Admin user 'admin' created with password 'admin123'")
