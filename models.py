"""
FB Manager - Database Models
============================
Sare database tables yahan defined hain
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()


class User(db.Model, UserMixin):
    """Team members: Owner, Supervisor, Worker"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # owner, supervisor, worker
    supervisor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    phone = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    workers = db.relationship('User', backref=db.backref('supervisor', remote_side=[id]))
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_owner(self):
        return self.role == 'owner'
    
    def is_supervisor(self):
        return self.role == 'supervisor'
    
    def is_worker(self):
        return self.role == 'worker'


class FBAccount(db.Model):
    """Aap ki Facebook IDs (multiple logins)"""
    __tablename__ = 'fb_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    account_name = db.Column(db.String(120), nullable=False)  # e.g. "Mudassar FB 1"
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    fb_password = db.Column(db.Text)  # encrypted - owner only visible
    recovery_email = db.Column(db.String(120))  # backup email
    two_fa_code = db.Column(db.Text)  # encrypted - 2FA backup codes
    purchase_date = db.Column(db.Date)
    purchase_cost = db.Column(db.Float, default=0)  # PKR
    status = db.Column(db.String(20), default='active')  # active, restricted, banned, disabled
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    pages = db.relationship('Page', backref='fb_account', lazy=True)
    business_managers = db.relationship('BusinessManager', backref='fb_account', lazy=True)
    
    # ============ ENCRYPTION HELPERS ============
    def set_fb_password(self, plain_password):
        """Password encrypt karke save karen"""
        if plain_password:
            from crypto_utils import encrypt_text
            self.fb_password = encrypt_text(plain_password)
        else:
            self.fb_password = None
    
    def get_fb_password(self):
        """Decrypted password return karen"""
        if not self.fb_password:
            return ''
        from crypto_utils import decrypt_text
        return decrypt_text(self.fb_password)
    
    def set_two_fa_code(self, plain_code):
        """2FA code encrypt karke save karen"""
        if plain_code:
            from crypto_utils import encrypt_text
            self.two_fa_code = encrypt_text(plain_code)
        else:
            self.two_fa_code = None
    
    def get_two_fa_code(self):
        """Decrypted 2FA code return karen"""
        if not self.two_fa_code:
            return ''
        from crypto_utils import decrypt_text
        return decrypt_text(self.two_fa_code)


class BusinessManager(db.Model):
    """Business Manager accounts"""
    __tablename__ = 'business_managers'
    
    id = db.Column(db.Integer, primary_key=True)
    bm_name = db.Column(db.String(120), nullable=False)
    bm_id = db.Column(db.String(50))  # Facebook BM ID
    fb_account_id = db.Column(db.Integer, db.ForeignKey('fb_accounts.id'), nullable=False)
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Page(db.Model):
    """Facebook Pages"""
    __tablename__ = 'pages'
    
    id = db.Column(db.Integer, primary_key=True)
    page_name = db.Column(db.String(150), nullable=False)
    page_url = db.Column(db.String(255))
    niche = db.Column(db.String(80))  # Comedy, News, Animals, etc.
    fb_account_id = db.Column(db.Integer, db.ForeignKey('fb_accounts.id'), nullable=False)
    bm_id = db.Column(db.Integer, db.ForeignKey('business_managers.id'), nullable=True)
    assigned_worker_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    monetization_status = db.Column(db.String(20), default='non_monetized')  
    # non_monetized, in_review, monetized, suspended
    
    monetized_date = db.Column(db.Date, nullable=True)
    page_created_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    assigned_worker = db.relationship('User', foreign_keys=[assigned_worker_id])
    business_manager = db.relationship('BusinessManager', foreign_keys=[bm_id])
    daily_reports = db.relationship('DailyReport', backref='page', lazy=True)


class DailyReport(db.Model):
    """Daily report har page ke liye"""
    __tablename__ = 'daily_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    page_id = db.Column(db.Integer, db.ForeignKey('pages.id'), nullable=False)
    worker_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    report_date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    
    views = db.Column(db.Integer, default=0)
    reach = db.Column(db.Integer, default=0)
    followers_gained = db.Column(db.Integer, default=0)
    
    # Earnings - sirf owner dekh sakta hai
    earnings_usd = db.Column(db.Float, default=0)
    
    notes = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    worker = db.relationship('User', foreign_keys=[worker_id])
    
    # Unique constraint - ek page ka ek din ka ek hi report
    __table_args__ = (db.UniqueConstraint('page_id', 'report_date', name='unique_page_date'),)


class TeamPayment(db.Model):
    """Supervisor aur Worker dono ke liye payment tracking"""
    __tablename__ = 'team_payments'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    month = db.Column(db.String(7), nullable=False)  # YYYY-MM format
    
    # Earnings details
    total_earned_usd = db.Column(db.Float, default=0)  # FB se kitna earn hua
    agreed_amount_pkr = db.Column(db.Float, default=0)  # Worker/supervisor ko kitna dena hai
    
    # Status tracking
    received_from_fb = db.Column(db.Boolean, default=False)
    received_date = db.Column(db.Date, nullable=True)
    
    paid_to_member = db.Column(db.Boolean, default=False)
    payment_date = db.Column(db.Date, nullable=True)
    payment_method = db.Column(db.String(50))  # Cash, Bank, EasyPaisa, JazzCash
    payment_reference = db.Column(db.String(100))  # Transaction ID
    
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id])
    
    @property
    def status(self):
        if self.paid_to_member:
            return 'paid'
        elif self.received_from_fb:
            return 'received'
        else:
            return 'pending'


def init_db(app):
    """Database initialize karna aur default owner user banana"""
    with app.app_context():
        db.create_all()
        
        # ==================== AUTO-MIGRATION ====================
        # Naye columns add karen agar existing table mein nahi hain
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        
        if 'fb_accounts' in inspector.get_table_names():
            existing_cols = [col['name'] for col in inspector.get_columns('fb_accounts')]
            
            # SQLite aur PostgreSQL dono ke liye work karta hai
            migrations = []
            if 'fb_password' not in existing_cols:
                migrations.append(('fb_password', 'TEXT'))
            if 'recovery_email' not in existing_cols:
                migrations.append(('recovery_email', 'VARCHAR(120)'))
            if 'two_fa_code' not in existing_cols:
                migrations.append(('two_fa_code', 'TEXT'))
            
            if migrations:
                with db.engine.connect() as conn:
                    for col_name, col_type in migrations:
                        try:
                            conn.execute(text(f'ALTER TABLE fb_accounts ADD COLUMN {col_name} {col_type}'))
                            conn.commit()
                            print(f"✅ Migration: Added column 'fb_accounts.{col_name}'")
                        except Exception as e:
                            print(f"⚠️ Migration warning for {col_name}: {e}")
        
        # Default owner user banao agar nahi hai
        if not User.query.filter_by(role='owner').first():
            owner = User(
                username='mudassar',
                full_name='Mudassar (Owner)',
                role='owner',
                phone='',
            )
            owner.set_password('admin123')  # IMPORTANT: change after first login
            db.session.add(owner)
            db.session.commit()
            print("✅ Default owner created: username='mudassar', password='admin123'")
