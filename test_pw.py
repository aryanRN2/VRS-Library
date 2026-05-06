from flask_bcrypt import Bcrypt
bcrypt = Bcrypt()
pw_hash = '$2b$12$Jr9TUr61AcioBm7rHWO8kOdgsq435ZKxb0htupqaZJ6RXAQvbnJI2'
print(bcrypt.check_password_hash(pw_hash, 'admin123'))
