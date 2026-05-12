import os
from app import app, db, text

with app.app_context():
    try:
        # Check if we are on PostgreSQL or SQLite
        engine_name = db.engine.name
        print(f"Detected engine: {engine_name}")
        
        if engine_name == 'postgresql':
            # Quoting "user" table name as it's a reserved keyword in Postgres
            db.session.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT \'pending\''))
        else:
            # SQLite doesn't support ADD COLUMN IF NOT EXISTS easily
            try:
                db.session.execute(text("ALTER TABLE user ADD COLUMN status VARCHAR(20) DEFAULT 'pending'"))
            except Exception as e:
                print(f"SQLite status column might already exist or error: {e}")
                
        db.session.commit()
        print("Database schema updated successfully!")
    except Exception as e:
        print(f"Error updating database: {e}")
        db.session.rollback()
