import os
from app import app, db
from sqlalchemy import text

with app.app_context():
    print(f"Connecting to: {app.config['SQLALCHEMY_DATABASE_URI']}")
    with db.engine.connect() as conn:
        for col, col_type in [('fathers_name', 'VARCHAR(100)'), ('address', 'TEXT')]:
            print(f"Adding {col}...")
            try:
                # Use public."user" to be safe
                conn.execute(text(f"ALTER TABLE public.\"user\" ADD COLUMN IF NOT EXISTS {col} {col_type}"))
                conn.commit()
                print(f"Column '{col}' verified/added.")
            except Exception as e:
                print(f"Error for {col}: {e}")
        
        # Also check booking for start_date
        print("Checking booking table...")
        try:
            conn.execute(text("ALTER TABLE public.\"booking\" ADD COLUMN IF NOT EXISTS start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            conn.commit()
            print("Column 'start_date' verified/added.")
        except Exception as e:
            print(f"Error for start_date: {e}")
