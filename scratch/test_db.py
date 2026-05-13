import os
from sqlalchemy import text
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
db_url = os.environ.get('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

print(f"URL: {db_url}")
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True}
db = SQLAlchemy(app)

with app.app_context():
    try:
        print("Testing database connection...")
        result = db.session.execute(text("SELECT 1")).fetchone()
        print(f"Connection successful: {result}")
    except Exception as e:
        print(f"Connection failed: {e}")
