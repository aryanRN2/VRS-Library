from app import app, db
from sqlalchemy import text

with app.app_context():
    sql = 'SELECT "user".id AS user_id, "user".username AS user_username, "user".fathers_name AS user_fathers_name FROM "user" LIMIT 1'
    try:
        with db.engine.connect() as conn:
            result = conn.execute(text(sql))
            for row in result:
                print(row)
            print("Success!")
    except Exception as e:
        print(f"Error running specific SQL: {e}")
