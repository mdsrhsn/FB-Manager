from app import app, db
from models import User
from werkzeug.security import generate_password_hash

with app.app_context():
    db.create_all()

    if not User.query.filter_by(username='mudassar').first():
        admin = User(
            username='mudassar',
            full_name='Mudassar Hussain',
            password_hash=generate_password_hash('admin123'),
            role='owner'
        )

        db.session.add(admin)
        db.session.commit()

    print("Database initialized successfully!")