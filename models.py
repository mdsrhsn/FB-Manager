"""
FB Manager - Database Models
============================
Sare database tables yahan defined hain

VERSION 2.0 - 10 FEATURES UPDATE
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

    # ============ PERMISSIONS (owner control karta hai) ============
    # Owner ke paas hamesha sab access hota hai. Yeh flags supervisors par lagte hain.
    can_view_fb_accounts = db.Column(db.Boolean, default=True)
    can_view_passwords = db.Column(db.Boolean, default=False)   # FB passwords dekh sakta hai
    can_view_bms = db.Column(db.Boolean, default=True)
    can_view_groups = db.Column(db.Boolean, default=True)
    can_view_team = db.Column(db.Boolean, default=True)
    can_add_edit = db.Column(db.Boolean, default=True)          # naya add / edit kar sakta hai
    can_delete = db.Column(db.Boolean, default=False)           # delete kar sakta hai
    can_export = db.Column(db.Boolean, default=False)           # Excel download kar sakta hai
    # Data scope: True = sab ka data dikhega | False = sirf apna + jo assign kiya gaya
    can_view_all_data = db.Column(db.Boolean, default=False)
    perms_initialized = db.Column(db.Boolean, default=False)    # ek dafa defaults set karne ke liye

    workers = db.relationship('User', backref=db.backref('supervisor', remote_side=[id]))

    def has_perm(self, perm):
        """
        Permission check — owner ke paas hamesha sab kuch hai.
        Supervisor AUR worker dono ke liye owner ke diye hue flags chalte hain.
        """
        if self.role == 'owner':
            return True
        return bool(getattr(self, 'can_' + perm, False))

    def sees_all_data(self):
        """Kya yeh user sab ka data dekh sakta hai?"""
        return self.role == 'owner' or bool(self.can_view_all_data)

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


@db.event.listens_for(User, 'before_insert')
def _apply_role_permission_defaults(mapper, connection, target):
    """
    Naya user kisi bhi raaste se bane (form, Excel import, script) —
    role ke hisaab se mehfooz defaults khud lag jayen.
    Owner permissions baad mein badal sakta hai.
    """
    if target.perms_initialized:
        return
    if target.role == 'owner':
        for f in ['can_view_fb_accounts', 'can_view_passwords', 'can_view_bms',
                  'can_view_groups', 'can_view_team', 'can_add_edit', 'can_delete',
                  'can_export', 'can_view_all_data']:
            setattr(target, f, True)
    elif target.role == 'worker':
        # Worker ko by default kuch nazar nahi aata jab tak owner ijazat na de
        for f in ['can_view_fb_accounts', 'can_view_passwords', 'can_view_bms',
                  'can_view_groups', 'can_view_team', 'can_add_edit', 'can_delete',
                  'can_export', 'can_view_all_data']:
            setattr(target, f, False)
    else:  # supervisor
        target.can_view_passwords = False
        target.can_delete = False
        target.can_export = False
        target.can_view_all_data = False
    target.perms_initialized = True


class FBAccount(db.Model):
    """Aap ki Facebook IDs (multiple logins)"""
    __tablename__ = 'fb_accounts'

    id = db.Column(db.Integer, primary_key=True)
    account_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    fb_password = db.Column(db.Text)  # encrypted
    recovery_email = db.Column(db.String(120))
    two_fa_code = db.Column(db.Text)  # encrypted
    purchase_date = db.Column(db.Date)
    purchase_cost = db.Column(db.Float, default=0)  # PKR
    status = db.Column(db.String(20), default='active')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ============ V3: kis ne banaya / kis ko assign hai ============
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    assigned_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # ============ V2 FIELDS ============
    location = db.Column(db.String(80))  # Feature 1: Pakistan, USA, Finland...
    issue_type = db.Column(db.String(30), default='none')  # Feature 2
    issue_notes = db.Column(db.Text)
    profile_link = db.Column(db.String(255))  # Feature 10
    profile_username = db.Column(db.String(120))  # Feature 10 auto-extracted
    date_of_birth = db.Column(db.Date)

    # Relationships
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    assigned_user = db.relationship('User', foreign_keys=[assigned_user_id])
    pages = db.relationship('Page', backref='fb_account', lazy=True)
    business_managers = db.relationship(
        'BusinessManager',
        foreign_keys='BusinessManager.fb_account_id',
        backref='fb_account',
        lazy=True
    )

    # ============ ENCRYPTION HELPERS ============
    def set_fb_password(self, plain_password):
        if plain_password:
            from crypto_utils import encrypt_text
            self.fb_password = encrypt_text(plain_password)
        else:
            self.fb_password = None

    def get_fb_password(self):
        if not self.fb_password:
            return ''
        from crypto_utils import decrypt_text
        return decrypt_text(self.fb_password)

    def set_two_fa_code(self, plain_code):
        if plain_code:
            from crypto_utils import encrypt_text
            self.two_fa_code = encrypt_text(plain_code)
        else:
            self.two_fa_code = None

    def get_two_fa_code(self):
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

    # ============ V3: ownership ============
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    assigned_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # ============ V2 FIELDS: Invite tracking (Feature 5) ============
    invited_to_fb_account_id = db.Column(
        db.Integer,
        db.ForeignKey('fb_accounts.id'),
        nullable=True
    )
    invite_date = db.Column(db.Date, nullable=True)
    invite_notes = db.Column(db.Text)

    invited_fb_account = db.relationship(
        'FBAccount',
        foreign_keys=[invited_to_fb_account_id],
        backref=db.backref('bm_invites_received', lazy=True)
    )
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    assigned_user = db.relationship('User', foreign_keys=[assigned_user_id])

    # Feature 4: partner access records
    partner_accesses = db.relationship(
        'BMPartnerAccess',
        backref='source_bm',
        lazy=True,
        cascade='all, delete-orphan'
    )

    # Email invites (pending / accepted)
    email_invites = db.relationship(
        'BMInvite',
        backref='business_manager',
        lazy=True,
        cascade='all, delete-orphan',
        order_by='BMInvite.created_at.desc()'
    )

    @property
    def pending_invites(self):
        return [i for i in self.email_invites if (i.status or 'pending') == 'pending']


class BMPartnerAccess(db.Model):
    """
    Feature 4: BM Partner Access tracking
    Jab kisi BM ko doosri BM ko Partner Access diya jata hai, yahan record hota hai.
    """
    __tablename__ = 'bm_partner_access'

    id = db.Column(db.Integer, primary_key=True)
    source_bm_id = db.Column(db.Integer, db.ForeignKey('business_managers.id'), nullable=False)
    partner_bm_name = db.Column(db.String(120), nullable=False)
    partner_bm_id = db.Column(db.String(50))
    access_granted_date = db.Column(db.Date, nullable=True)
    access_level = db.Column(db.String(50))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Page(db.Model):
    """Facebook Pages"""
    __tablename__ = 'pages'

    id = db.Column(db.Integer, primary_key=True)
    page_name = db.Column(db.String(150), nullable=False)
    page_url = db.Column(db.String(255))
    niche = db.Column(db.String(80))
    fb_account_id = db.Column(db.Integer, db.ForeignKey('fb_accounts.id'), nullable=False)
    bm_id = db.Column(db.Integer, db.ForeignKey('business_managers.id'), nullable=True)
    assigned_worker_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    monetization_status = db.Column(db.String(20), default='non_monetized')
    monetized_date = db.Column(db.Date, nullable=True)
    page_created_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ============ V2 FIELDS ============
    recommendation = db.Column(db.String(10), default='okay')  # Feature 3: 'okay' / 'not_okay'
    recommendation_notes = db.Column(db.Text)
    is_fresh_start = db.Column(db.Boolean, default=True)  # Feature 6
    followers_at_start = db.Column(db.Integer, default=0)
    current_followers = db.Column(db.Integer, default=0)
    # Page health status — monetization se alag (suspend/flag/restrict tracking)
    page_status = db.Column(db.String(20), default='active')
    page_status_notes = db.Column(db.Text)

    # ============ V3: kis ne banaya ============
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relationships
    assigned_worker = db.relationship('User', foreign_keys=[assigned_worker_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    business_manager = db.relationship('BusinessManager', foreign_keys=[bm_id])
    daily_reports = db.relationship('DailyReport', backref='page', lazy=True)

    # Feature 7: Groups linked to this page
    linked_groups = db.relationship(
        'Group',
        foreign_keys='Group.page_id',
        backref='page',
        lazy=True
    )


class Group(db.Model):
    """
    Feature 7: Facebook Groups linked to Pages or FB Accounts
    """
    __tablename__ = 'groups'

    id = db.Column(db.Integer, primary_key=True)
    group_name = db.Column(db.String(150), nullable=False)
    group_url = db.Column(db.String(255))
    group_fb_id = db.Column(db.String(50))

    page_id = db.Column(db.Integer, db.ForeignKey('pages.id'), nullable=True)
    fb_account_id = db.Column(db.Integer, db.ForeignKey('fb_accounts.id'), nullable=True)

    members_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='active')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ============ V3: ownership ============
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    assigned_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    created_by = db.relationship('User', foreign_keys=[created_by_id])
    assigned_user = db.relationship('User', foreign_keys=[assigned_user_id])

    fb_account = db.relationship(
        'FBAccount',
        foreign_keys=[fb_account_id],
        backref=db.backref('linked_groups', lazy=True)
    )

    # Extra IDs jinme yeh group admin hai
    extra_accounts = db.relationship(
        'GroupAccount',
        backref='group',
        lazy=True,
        cascade='all, delete-orphan'
    )

    @property
    def all_account_ids(self):
        """Main ID + extra IDs — sab milakar"""
        ids = set()
        if self.fb_account_id:
            ids.add(self.fb_account_id)
        for ga in self.extra_accounts:
            if ga.fb_account_id:
                ids.add(ga.fb_account_id)
        return ids


class ActivityLog(db.Model):
    """
    Kis ne kya kiya — khaas kar DELETE ka record.
    Owner ko dashboard par nazar aata hai.
    """
    __tablename__ = 'activity_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    user_name = db.Column(db.String(120))      # snapshot — user delete ho jaye to bhi naam rahe
    user_role = db.Column(db.String(20))
    action = db.Column(db.String(20))          # create / update / delete
    entity_type = db.Column(db.String(40))     # FB Account / Page / BM / Group / Partner Access
    entity_name = db.Column(db.String(180))
    details = db.Column(db.Text)
    seen_by_owner = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class GroupAccount(db.Model):
    """
    Ek group agar kai FB IDs mein admin hai to woh extra IDs yahan.
    Main (primary) ID Group.fb_account_id mein rehti hai.
    """
    __tablename__ = 'group_accounts'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    fb_account_id = db.Column(db.Integer, db.ForeignKey('fb_accounts.id'), nullable=False)
    role_note = db.Column(db.String(80))      # e.g. Admin / Moderator
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    fb_account = db.relationship('FBAccount', foreign_keys=[fb_account_id])

    __table_args__ = (db.UniqueConstraint('group_id', 'fb_account_id', name='unique_group_account'),)


class BMInvite(db.Model):
    """
    BM ka invite jo EMAIL par bheja gaya — abhi accept nahi hua.
    Accept ho jaye to status badal kar konsi FB ID bani woh bhi link kar sakte hain.
    """
    __tablename__ = 'bm_invites'

    id = db.Column(db.Integer, primary_key=True)
    bm_id = db.Column(db.Integer, db.ForeignKey('business_managers.id'), nullable=False)
    email = db.Column(db.String(160), nullable=False)
    status = db.Column(db.String(20), default='pending')   # pending / accepted / expired
    invited_date = db.Column(db.Date, nullable=True)
    accepted_date = db.Column(db.Date, nullable=True)
    # Accept hone ke baad konsi FB ID se juda (optional)
    fb_account_id = db.Column(db.Integer, db.ForeignKey('fb_accounts.id'), nullable=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    fb_account = db.relationship('FBAccount', foreign_keys=[fb_account_id])


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
    earnings_usd = db.Column(db.Float, default=0)
    notes = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    worker = db.relationship('User', foreign_keys=[worker_id])

    __table_args__ = (db.UniqueConstraint('page_id', 'report_date', name='unique_page_date'),)


class TeamPayment(db.Model):
    """Supervisor aur Worker dono ke liye payment tracking"""
    __tablename__ = 'team_payments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    month = db.Column(db.String(7), nullable=False)  # YYYY-MM

    total_earned_usd = db.Column(db.Float, default=0)
    agreed_amount_pkr = db.Column(db.Float, default=0)

    received_from_fb = db.Column(db.Boolean, default=False)
    received_date = db.Column(db.Date, nullable=True)
    paid_to_member = db.Column(db.Boolean, default=False)
    payment_date = db.Column(db.Date, nullable=True)
    payment_method = db.Column(db.String(50))
    payment_reference = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])

    @property
    def status(self):
        if self.paid_to_member:
            return 'paid'
        elif self.received_from_fb:
            return 'received'
        else:
            return 'pending'


# ==================== UTILITY: Extract Username from FB URL ====================
def extract_username_from_url(url):
    """Feature 10: FB Profile Link se username auto-extract"""
    if not url:
        return None

    try:
        url = url.strip().rstrip('/')

        for prefix in ('https://', 'http://'):
            if url.startswith(prefix):
                url = url[len(prefix):]
                break

        for prefix in ('www.', 'm.', 'mbasic.', 'web.'):
            if url.startswith(prefix):
                url = url[len(prefix):]
                break

        if not (url.startswith('facebook.com/') or url.startswith('fb.com/')):
            return None

        if url.startswith('facebook.com/'):
            path = url[len('facebook.com/'):]
        else:
            path = url[len('fb.com/'):]

        if not path:
            return None

        for separator in ('?', '#'):
            if separator in path:
                path = path.split(separator)[0]

        if path.startswith('profile.php'):
            if '?' in url:
                query = url.split('?', 1)[1]
                for param in query.split('&'):
                    if param.startswith('id='):
                        numeric_id = param[3:].split('&')[0].split('#')[0]
                        if numeric_id.isdigit():
                            return f'id_{numeric_id}'
            return None

        if path.startswith('people/'):
            parts = path.split('/')
            if len(parts) >= 3:
                return f'people_{parts[1]}_{parts[2]}'
            return None

        username = path.split('/')[0]

        if not username:
            return None

        if not all(c.isalnum() or c in '._-' for c in username):
            return None

        return username

    except Exception:
        return None


# ==================== DATABASE INIT + AUTO-MIGRATION ====================
def init_db(app):
    """Database initialize karna aur default owner user banana"""
    with app.app_context():
        db.create_all()

        from sqlalchemy import inspect, text

        inspector = inspect(db.engine)
        all_migrations = []

        # PostgreSQL (Railway) aur SQLite (local) ka syntax alag hai
        is_postgres = db.engine.dialect.name == 'postgresql'
        BOOL_TRUE = 'BOOLEAN DEFAULT TRUE' if is_postgres else 'BOOLEAN DEFAULT 1'
        BOOL_FALSE = 'BOOLEAN DEFAULT FALSE' if is_postgres else 'BOOLEAN DEFAULT 0'

        # ---- fb_accounts new columns ----
        if 'fb_accounts' in inspector.get_table_names():
            existing_cols = [col['name'] for col in inspector.get_columns('fb_accounts')]
            migrations = []

            if 'fb_password' not in existing_cols:
                migrations.append(('fb_password', 'TEXT'))
            if 'recovery_email' not in existing_cols:
                migrations.append(('recovery_email', 'VARCHAR(120)'))
            if 'two_fa_code' not in existing_cols:
                migrations.append(('two_fa_code', 'TEXT'))
            if 'location' not in existing_cols:
                migrations.append(('location', 'VARCHAR(80)'))
            if 'issue_type' not in existing_cols:
                migrations.append(('issue_type', "VARCHAR(30) DEFAULT 'none'"))
            if 'issue_notes' not in existing_cols:
                migrations.append(('issue_notes', 'TEXT'))
            if 'profile_link' not in existing_cols:
                migrations.append(('profile_link', 'VARCHAR(255)'))
            if 'profile_username' not in existing_cols:
                migrations.append(('profile_username', 'VARCHAR(120)'))
            if 'date_of_birth' not in existing_cols:
                migrations.append(('date_of_birth', 'DATE'))

            if 'created_by_id' not in existing_cols:
                migrations.append(('created_by_id', 'INTEGER'))
            if 'assigned_user_id' not in existing_cols:
                migrations.append(('assigned_user_id', 'INTEGER'))

            for col_name, col_type in migrations:
                all_migrations.append(('fb_accounts', col_name, col_type))

        # ---- users permission columns ----
        if 'users' in inspector.get_table_names():
            existing_cols = [col['name'] for col in inspector.get_columns('users')]
            perm_defaults = [
                ('can_view_fb_accounts', True),
                ('can_view_passwords', False),
                ('can_view_bms', True),
                ('can_view_groups', True),
                ('can_view_team', True),
                ('can_add_edit', True),
                ('can_delete', False),
                ('can_export', False),
                ('can_view_all_data', False),
                ('perms_initialized', False),
            ]
            for col_name, default_true in perm_defaults:
                if col_name not in existing_cols:
                    col_type = BOOL_TRUE if default_true else BOOL_FALSE
                    all_migrations.append(('users', col_name, col_type))

        # ---- business_managers new columns ----
        if 'business_managers' in inspector.get_table_names():
            existing_cols = [col['name'] for col in inspector.get_columns('business_managers')]
            migrations = []

            if 'invited_to_fb_account_id' not in existing_cols:
                migrations.append(('invited_to_fb_account_id', 'INTEGER'))
            if 'invite_date' not in existing_cols:
                migrations.append(('invite_date', 'DATE'))
            if 'invite_notes' not in existing_cols:
                migrations.append(('invite_notes', 'TEXT'))

            if 'created_by_id' not in existing_cols:
                migrations.append(('created_by_id', 'INTEGER'))
            if 'assigned_user_id' not in existing_cols:
                migrations.append(('assigned_user_id', 'INTEGER'))

            for col_name, col_type in migrations:
                all_migrations.append(('business_managers', col_name, col_type))

        # ---- pages new columns ----
        if 'pages' in inspector.get_table_names():
            existing_cols = [col['name'] for col in inspector.get_columns('pages')]
            migrations = []

            if 'recommendation' not in existing_cols:
                migrations.append(('recommendation', "VARCHAR(10) DEFAULT 'okay'"))
            if 'recommendation_notes' not in existing_cols:
                migrations.append(('recommendation_notes', 'TEXT'))
            if 'is_fresh_start' not in existing_cols:
                migrations.append(('is_fresh_start', BOOL_TRUE))
            if 'followers_at_start' not in existing_cols:
                migrations.append(('followers_at_start', 'INTEGER DEFAULT 0'))
            if 'current_followers' not in existing_cols:
                migrations.append(('current_followers', 'INTEGER DEFAULT 0'))
            if 'page_status' not in existing_cols:
                migrations.append(('page_status', "VARCHAR(20) DEFAULT 'active'"))
            if 'page_status_notes' not in existing_cols:
                migrations.append(('page_status_notes', 'TEXT'))
            if 'created_by_id' not in existing_cols:
                migrations.append(('created_by_id', 'INTEGER'))

            for col_name, col_type in migrations:
                all_migrations.append(('pages', col_name, col_type))

        # ---- groups new columns ----
        if 'groups' in inspector.get_table_names():
            existing_cols = [col['name'] for col in inspector.get_columns('groups')]
            if 'created_by_id' not in existing_cols:
                all_migrations.append(('groups', 'created_by_id', 'INTEGER'))
            if 'assigned_user_id' not in existing_cols:
                all_migrations.append(('groups', 'assigned_user_id', 'INTEGER'))

        # ---- Apply all migrations ----
        if all_migrations:
            with db.engine.connect() as conn:
                for table_name, col_name, col_type in all_migrations:
                    try:
                        conn.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}'))
                        conn.commit()
                        print(f"Migration: Added column '{table_name}.{col_name}'")
                    except Exception as e:
                        print(f"Migration warning for {table_name}.{col_name}: {e}")

        # ---- Ek dafa permission defaults set karen (safety) ----
        # Workers ko by default kuch nazar nahi aata jab tak owner ijazat na de.
        # Supervisors ko dekhne ka access milta hai lekin export/delete/passwords nahi.
        try:
            uninitialized = User.query.filter(
                (User.perms_initialized == False) | (User.perms_initialized.is_(None))
            ).all()
            for u in uninitialized:
                if u.role == 'worker':
                    u.can_view_fb_accounts = False
                    u.can_view_passwords = False
                    u.can_view_bms = False
                    u.can_view_groups = False
                    u.can_view_team = False
                    u.can_add_edit = False
                    u.can_delete = False
                    u.can_export = False
                    u.can_view_all_data = False
                elif u.role == 'supervisor':
                    u.can_view_passwords = False
                    u.can_delete = False
                    u.can_export = False
                    if u.can_view_all_data is None:
                        u.can_view_all_data = False
                u.perms_initialized = True
            if uninitialized:
                db.session.commit()
                print(f"Permissions initialized for {len(uninitialized)} user(s)")
        except Exception as e:
            db.session.rollback()
            print(f"Permission init skipped: {e}")

        # Default owner user banao agar nahi hai
        if not User.query.filter_by(role='owner').first():
            owner = User(
                username='mudassar',
                full_name='Mudassar (Owner)',
                role='owner',
                phone='',
            )
            owner.set_password('admin123')
            db.session.add(owner)
            db.session.commit()
            print("Default owner created: username='mudassar', password='admin123'")
