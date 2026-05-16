from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        with db.engine.connect() as conn:
            result = conn.execute(text("SELECT table_name, table_schema FROM information_schema.tables WHERE table_name ILIKE 'user'"))
            for row in result:
                print(f"Table: {row[0]}, Schema: {row[1]}")
                
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'user' AND table_schema = 'public'"))
            print(f"Columns in public.user: {[row[0] for row in result]}")
    except Exception as e:
        print(f"Error: {e}")
