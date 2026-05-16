from app import app, db
from sqlalchemy import text

with app.app_context():
    print(f"DATABASE_URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    try:
        with db.engine.connect() as conn:
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'user'"))
            columns = [row[0] for row in result]
            print(f"Columns in 'user' table: {columns}")
            
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'booking'"))
            columns = [row[0] for row in result]
            print(f"Columns in 'booking' table: {columns}")
    except Exception as e:
        print(f"Error checking columns: {e}")
        # Try sqlite if information_schema fails
        try:
            with db.engine.connect() as conn:
                result = conn.execute(text("PRAGMA table_info('user')"))
                columns = [row[1] for row in result]
                print(f"Columns in 'user' table (sqlite): {columns}")
        except Exception as e2:
            print(f"Error checking columns (sqlite): {e2}")
