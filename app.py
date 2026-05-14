"""
FB Manager - Main Application
=============================
Flask app jo Facebook Pages, Team, aur Earnings manage karta hai
"""
import os
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import func, extract

from models import db, User, FBAccount, BusinessManager, Page, DailyReport, TeamPayment, init_db
# ==================== APP CONFIG ====================
app = Flask(__name__)
with app.app_context():
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-secret-in-production-12345')

# Database - Railway pe PostgreSQL ya local SQLite
database_url = os.environ.get('DATABASE_URL', 'sqlite:///fb_manager.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# ==================== LOGIN MANAGER ====================
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Pehle login karein'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ==================== ROLE DECORATORS ====================
def owner_required(f):
    """Sirf owner access kar sakta hai"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_owner():
            flash('Yeh page sirf owner ke liye hai', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def owner_or_supervisor(f):
    """Owner ya supervisor access kar sakta hai"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.is_worker():
            flash('Access denied', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# ==================== AUTH ROUTES ====================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username, is_active=True).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Galat username ya password', 'error')
    
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ==================== DASHBOARD ====================
@app.route('/')
@login_required
def dashboard():
    today = date.today()
    last_7_days = today - timedelta(days=7)
    last_30_days = today - timedelta(days=30)
    
    # Common stats (sab dekh sakte hain)
    total_pages = Page.query.filter_by(is_active=True).count()
    monetized_pages = Page.query.filter_by(is_active=True, monetization_status='monetized').count()
    non_monetized = Page.query.filter_by(is_active=True, monetization_status='non_monetized').count()
    in_review = Page.query.filter_by(is_active=True, monetization_status='in_review').count()
    total_fb_accounts = FBAccount.query.filter_by(status='active').count()
    
    # Role ke hisaab se data filter
    if current_user.is_worker():
        # Worker sirf apne assigned pages
        my_pages = Page.query.filter_by(assigned_worker_id=current_user.id, is_active=True).all()
        
        # Aaj ki report status
        today_reports = DailyReport.query.filter_by(
            worker_id=current_user.id, 
            report_date=today
        ).count()
        
        # Last 7 days views (sirf views, NO earnings)
        my_views = db.session.query(func.sum(DailyReport.views)).filter(
            DailyReport.worker_id == current_user.id,
            DailyReport.report_date >= last_7_days
        ).scalar() or 0
        
        return render_template('dashboard_worker.html',
            my_pages=my_pages,
            total_pages_assigned=len(my_pages),
            today_reports=today_reports,
            pending_reports=len(my_pages) - today_reports,
            my_views=my_views
        )
    
    elif current_user.is_supervisor():
        # Supervisor: apni team ke pages
        team_workers = User.query.filter_by(supervisor_id=current_user.id).all()
        team_worker_ids = [w.id for w in team_workers]
        
        team_pages = Page.query.filter(
            Page.assigned_worker_id.in_(team_worker_ids),
            Page.is_active == True
        ).all() if team_worker_ids else []
        
        # Team views (NO earnings)
        team_views = db.session.query(func.sum(DailyReport.views)).filter(
            DailyReport.worker_id.in_(team_worker_ids),
            DailyReport.report_date >= last_7_days
        ).scalar() or 0 if team_worker_ids else 0
        
        return render_template('dashboard_supervisor.html',
            team_workers=team_workers,
            team_pages=team_pages,
            total_team_pages=len(team_pages),
            team_views=team_views,
            monetized_pages=monetized_pages,
            non_monetized=non_monetized
        )
    
    else:  # OWNER - sab kuch dekhega including earnings
        # Total earnings
        total_earnings_30d = db.session.query(func.sum(DailyReport.earnings_usd)).filter(
            DailyReport.report_date >= last_30_days
        ).scalar() or 0
        
        total_earnings_today = db.session.query(func.sum(DailyReport.earnings_usd)).filter(
            DailyReport.report_date == today
        ).scalar() or 0
        
        total_views_30d = db.session.query(func.sum(DailyReport.views)).filter(
            DailyReport.report_date >= last_30_days
        ).scalar() or 0
        
        # Pending payments
        pending_fb_payments = db.session.query(func.sum(TeamPayment.total_earned_usd)).filter(
            TeamPayment.received_from_fb == False
        ).scalar() or 0
        
        pending_team_payments = db.session.query(func.sum(TeamPayment.agreed_amount_pkr)).filter(
            TeamPayment.received_from_fb == True,
            TeamPayment.paid_to_member == False
        ).scalar() or 0
        
        # Top pages by earnings (last 30 days)
        top_pages = db.session.query(
            Page.page_name,
            func.sum(DailyReport.earnings_usd).label('earnings'),
            func.sum(DailyReport.views).label('views')
        ).join(DailyReport).filter(
            DailyReport.report_date >= last_30_days
        ).group_by(Page.id).order_by(func.sum(DailyReport.earnings_usd).desc()).limit(10).all()
        
        # Last 7 days chart data
        chart_data = []
        for i in range(7):
            d = today - timedelta(days=6-i)
            earnings = db.session.query(func.sum(DailyReport.earnings_usd)).filter(
                DailyReport.report_date == d
            ).scalar() or 0
            views = db.session.query(func.sum(DailyReport.views)).filter(
                DailyReport.report_date == d
            ).scalar() or 0
            chart_data.append({
                'date': d.strftime('%d %b'),
                'earnings': float(earnings),
                'views': int(views)
            })
        
        return render_template('dashboard_owner.html',
            total_pages=total_pages,
            monetized_pages=monetized_pages,
            non_monetized=non_monetized,
            in_review=in_review,
            total_fb_accounts=total_fb_accounts,
            total_earnings_30d=total_earnings_30d,
            total_earnings_today=total_earnings_today,
            total_views_30d=total_views_30d,
            pending_fb_payments=pending_fb_payments,
            pending_team_payments=pending_team_payments,
            top_pages=top_pages,
            chart_data=chart_data
        )


# ==================== FB ACCOUNTS ====================
@app.route('/fb-accounts')
@login_required
@owner_or_supervisor
def fb_accounts():
    accounts = FBAccount.query.order_by(FBAccount.created_at.desc()).all()
    return render_template('fb_accounts.html', accounts=accounts)


@app.route('/fb-accounts/add', methods=['GET', 'POST'])
@login_required
@owner_required
def add_fb_account():
    if request.method == 'POST':
        purchase_date = request.form.get('purchase_date')
        account = FBAccount(
            account_name=request.form.get('account_name'),
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            recovery_email=request.form.get('recovery_email'),
            purchase_date=datetime.strptime(purchase_date, '%Y-%m-%d').date() if purchase_date else None,
            purchase_cost=float(request.form.get('purchase_cost') or 0),
            status=request.form.get('status', 'active'),
            notes=request.form.get('notes')
        )
        # Encrypted fields
        account.set_fb_password(request.form.get('fb_password'))
        account.set_two_fa_code(request.form.get('two_fa_code'))
        
        db.session.add(account)
        db.session.commit()
        flash('FB Account add ho gaya (password encrypted hai)', 'success')
        return redirect(url_for('fb_accounts'))
    
    return render_template('fb_account_form.html', account=None)


@app.route('/fb-accounts/<int:account_id>/edit', methods=['GET', 'POST'])
@login_required
@owner_required
def edit_fb_account(account_id):
    account = FBAccount.query.get_or_404(account_id)
    if request.method == 'POST':
        purchase_date = request.form.get('purchase_date')
        account.account_name = request.form.get('account_name')
        account.email = request.form.get('email')
        account.phone = request.form.get('phone')
        
        # Password sirf tab update karen agar user ne diya hai
        new_password = request.form.get('fb_password')
        if new_password:
            account.set_fb_password(new_password)
        
        new_2fa = request.form.get('two_fa_code')
        if new_2fa:
            account.set_two_fa_code(new_2fa)
        
        account.recovery_email = request.form.get('recovery_email')
        account.purchase_date = datetime.strptime(purchase_date, '%Y-%m-%d').date() if purchase_date else None
        account.purchase_cost = float(request.form.get('purchase_cost') or 0)
        account.status = request.form.get('status', 'active')
        account.notes = request.form.get('notes')
        db.session.commit()
        flash('FB Account update ho gaya', 'success')
        return redirect(url_for('fb_accounts'))
    
    return render_template('fb_account_form.html', account=account)


# ==================== FB ACCOUNTS - EXCEL IMPORT/EXPORT ====================

@app.route('/fb-accounts/export')
@login_required
@owner_required
def export_fb_accounts():
    """Saare FB accounts ko Excel file mein export karen"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from io import BytesIO
    from flask import send_file
    
    wb = Workbook()
    ws = wb.active
    ws.title = "FB Accounts"
    
    # Headers
    headers = [
        'Account Name', 'Email', 'Phone', 'FB Password', 
        'Recovery Email', '2FA Code', 'Purchase Date', 
        'Purchase Cost (PKR)', 'Status', 'Notes'
    ]
    ws.append(headers)
    
    # Header styling
    header_font = Font(bold=True, color='FFFFFF', size=12)
    header_fill = PatternFill(start_color='1877F2', end_color='1877F2', fill_type='solid')
    for col_num, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # Data rows
    accounts = FBAccount.query.order_by(FBAccount.created_at.desc()).all()
    for acc in accounts:
        ws.append([
            acc.account_name or '',
            acc.email or '',
            acc.phone or '',
            acc.get_fb_password() or '',
            acc.recovery_email or '',
            acc.get_two_fa_code() or '',
            acc.purchase_date.strftime('%Y-%m-%d') if acc.purchase_date else '',
            acc.purchase_cost or 0,
            acc.status or 'active',
            acc.notes or ''
        ])
    
    # Auto-width columns
    column_widths = [20, 25, 15, 20, 25, 20, 14, 15, 12, 30]
    for i, width in enumerate(column_widths, 1):
        ws.column_dimensions[chr(64 + i)].width = width
    
    # Freeze first row
    ws.freeze_panes = 'A2'
    
    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    filename = f"fb_accounts_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


@app.route('/fb-accounts/import', methods=['POST'])
@login_required
@owner_required
def import_fb_accounts():
    """Excel file se FB accounts ko bulk import karen"""
    from openpyxl import load_workbook
    
    if 'excel_file' not in request.files:
        flash('Koi file select nahi ki gayi', 'error')
        return redirect(url_for('fb_accounts'))
    
    file = request.files['excel_file']
    if file.filename == '':
        flash('Koi file select nahi ki gayi', 'error')
        return redirect(url_for('fb_accounts'))
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        flash('Sirf Excel file (.xlsx ya .xls) upload karen', 'error')
        return redirect(url_for('fb_accounts'))
    
    try:
        wb = load_workbook(file, data_only=True)
        ws = wb.active
        
        imported_count = 0
        skipped_count = 0
        error_rows = []
        
        # Pehli row header hai, baqi data
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            # Empty rows skip karen
            if not row or not any(row):
                continue
            
            try:
                # Columns: account_name, email, phone, password, recovery_email, 2fa, purchase_date, cost, status, notes
                account_name = str(row[0]).strip() if row[0] else None
                
                if not account_name:
                    skipped_count += 1
                    continue
                
                # Duplicate check (account_name ke base par)
                existing = FBAccount.query.filter_by(account_name=account_name).first()
                if existing:
                    skipped_count += 1
                    continue
                
                # Purchase date parse
                purchase_date = None
                if row[6]:
                    try:
                        if isinstance(row[6], datetime):
                            purchase_date = row[6].date()
                        elif isinstance(row[6], date):
                            purchase_date = row[6]
                        else:
                            purchase_date = datetime.strptime(str(row[6]).split()[0], '%Y-%m-%d').date()
                    except:
                        purchase_date = None
                
                # Purchase cost
                try:
                    purchase_cost = float(row[7]) if row[7] else 0
                except:
                    purchase_cost = 0
                
                # Status validate
                status = str(row[8]).strip().lower() if row[8] else 'active'
                if status not in ['active', 'restricted', 'banned', 'disabled']:
                    status = 'active'
                
                account = FBAccount(
                    account_name=account_name,
                    email=str(row[1]).strip() if row[1] else None,
                    phone=str(row[2]).strip() if row[2] else None,
                    recovery_email=str(row[4]).strip() if row[4] else None,
                    purchase_date=purchase_date,
                    purchase_cost=purchase_cost,
                    status=status,
                    notes=str(row[9]).strip() if row[9] else None
                )
                # Encrypt sensitive fields
                if row[3]:
                    account.set_fb_password(str(row[3]).strip())
                if row[5]:
                    account.set_two_fa_code(str(row[5]).strip())
                
                db.session.add(account)
                imported_count += 1
                
            except Exception as e:
                error_rows.append(f"Row {row_num}: {str(e)}")
                continue
        
        db.session.commit()
        
        msg = f'✅ {imported_count} accounts import ho gaye'
        if skipped_count > 0:
            msg += f' | ⏭️ {skipped_count} skip kiye gaye (already exist ya empty)'
        if error_rows:
            msg += f' | ⚠️ {len(error_rows)} errors'
        
        flash(msg, 'success' if imported_count > 0 else 'warning')
        
    except Exception as e:
        flash(f'Import error: {str(e)}', 'error')
    
    return redirect(url_for('fb_accounts'))


@app.route('/fb-accounts/template')
@login_required
@owner_required
def fb_accounts_template():
    """Sample Excel template download karen for import"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from io import BytesIO
    from flask import send_file
    
    wb = Workbook()
    ws = wb.active
    ws.title = "FB Accounts Template"
    
    headers = [
        'Account Name', 'Email', 'Phone', 'FB Password', 
        'Recovery Email', '2FA Code', 'Purchase Date', 
        'Purchase Cost (PKR)', 'Status', 'Notes'
    ]
    ws.append(headers)
    
    # Header styling
    header_font = Font(bold=True, color='FFFFFF', size=12)
    header_fill = PatternFill(start_color='1877F2', end_color='1877F2', fill_type='solid')
    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
    
    # Sample data
    sample_rows = [
        ['Mudassar FB 1', 'fb1@gmail.com', '03001234567', 'YourPassword123', 
         'recovery@gmail.com', '2FA backup code', '2024-01-15', 5000, 'active', 'Main account'],
        ['Mudassar FB 2', 'fb2@gmail.com', '03007654321', 'AnotherPass456', 
         '', '', '2024-02-20', 3000, 'active', 'Secondary'],
    ]
    for row in sample_rows:
        ws.append(row)
    
    # Status note
    ws.cell(row=5, column=1, value='Note: Status field accepts: active, restricted, banned, disabled')
    ws.cell(row=5, column=1).font = Font(italic=True, color='888888')
    
    column_widths = [20, 25, 15, 20, 25, 20, 14, 15, 12, 30]
    for i, width in enumerate(column_widths, 1):
        ws.column_dimensions[chr(64 + i)].width = width
    
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='fb_accounts_template.xlsx'
    )


# ==================== API: Get decrypted password (owner only) ====================
@app.route('/api/fb-account/<int:account_id>/password')
@login_required
@owner_required
def api_get_fb_password(account_id):
    """AJAX endpoint - returns decrypted password for display"""
    account = FBAccount.query.get_or_404(account_id)
    return jsonify({
        'success': True,
        'password': account.get_fb_password(),
        'two_fa': account.get_two_fa_code()
    })


# ==================== EXCEL HELPER ====================
def _excel_response(wb, filename):
    """Helper: workbook ko Excel download response banata hai"""
    from io import BytesIO
    from flask import send_file
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


def _style_header(ws, headers, color='1877F2'):
    """Helper: header row par styling lagao"""
    from openpyxl.styles import Font, PatternFill, Alignment
    ws.append(headers)
    header_font = Font(bold=True, color='FFFFFF', size=12)
    header_fill = PatternFill(start_color=color, end_color=color, fill_type='solid')
    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.freeze_panes = 'A2'


# ==================== PAGES - EXCEL IMPORT/EXPORT ====================
@app.route('/pages/export')
@login_required
@owner_required
def export_pages():
    """Saare pages Excel mein export karen"""
    from openpyxl import Workbook
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Pages"
    
    headers = [
        'Page Name', 'Page URL', 'Niche', 'FB Account', 'Business Manager',
        'Assigned Worker', 'Monetization Status', 'Monetized Date', 
        'Page Created Date', 'Notes'
    ]
    _style_header(ws, headers, '42b72a')
    
    pages_list = Page.query.filter_by(is_active=True).all()
    for p in pages_list:
        ws.append([
            p.page_name or '',
            p.page_url or '',
            p.niche or '',
            p.fb_account.account_name if p.fb_account else '',
            p.business_manager.bm_name if p.business_manager else '',
            p.assigned_worker.full_name if p.assigned_worker else '',
            p.monetization_status or 'non_monetized',
            p.monetized_date.strftime('%Y-%m-%d') if p.monetized_date else '',
            p.page_created_date.strftime('%Y-%m-%d') if p.page_created_date else '',
            p.notes or ''
        ])
    
    column_widths = [25, 35, 15, 20, 20, 20, 18, 14, 14, 30]
    for i, width in enumerate(column_widths, 1):
        ws.column_dimensions[chr(64 + i)].width = width
    
    filename = f"pages_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return _excel_response(wb, filename)


@app.route('/pages/template')
@login_required
@owner_required
def pages_template():
    """Pages import ke liye sample Excel template"""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Pages Template"
    
    headers = [
        'Page Name', 'Page URL', 'Niche', 'FB Account', 'Business Manager',
        'Assigned Worker', 'Monetization Status', 'Monetized Date', 
        'Page Created Date', 'Notes'
    ]
    _style_header(ws, headers, '42b72a')
    
    # Sample data
    samples = [
        ['Comedy Hub', 'https://fb.com/comedyhub', 'Comedy', 'Mudassar FB 1', '', 
         '', 'monetized', '2024-03-15', '2023-12-01', 'Top performer'],
        ['News Pakistan', 'https://fb.com/newspk', 'News', 'Mudassar FB 1', 'Main BM', 
         'Ali Worker', 'non_monetized', '', '2024-01-10', ''],
    ]
    for row in samples:
        ws.append(row)
    
    notes = [
        '',
        'Notes:',
        '1. FB Account: existing account_name use karen (exact match)',
        '2. Business Manager: optional, agar BM mein hai',
        '3. Assigned Worker: worker ka full_name (exact match)',
        '4. Monetization Status: monetized, non_monetized, in_review, suspended',
        '5. Dates: YYYY-MM-DD format mein (e.g. 2024-03-15)'
    ]
    for i, note in enumerate(notes, start=5):
        cell = ws.cell(row=i, column=1, value=note)
        if i > 5:
            cell.font = Font(italic=True, color='888888', size=11)
    
    column_widths = [25, 35, 15, 20, 20, 20, 18, 14, 14, 30]
    for i, width in enumerate(column_widths, 1):
        ws.column_dimensions[chr(64 + i)].width = width
    
    return _excel_response(wb, 'pages_template.xlsx')


@app.route('/pages/import', methods=['POST'])
@login_required
@owner_required
def import_pages():
    """Excel se pages bulk import karen"""
    from openpyxl import load_workbook
    
    if 'excel_file' not in request.files or request.files['excel_file'].filename == '':
        flash('Koi file select nahi ki gayi', 'error')
        return redirect(url_for('pages'))
    
    file = request.files['excel_file']
    if not file.filename.endswith(('.xlsx', '.xls')):
        flash('Sirf Excel file upload karen', 'error')
        return redirect(url_for('pages'))
    
    try:
        wb = load_workbook(file, data_only=True)
        ws = wb.active
        
        imported = 0
        skipped = 0
        errors = []
        
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or not any(row):
                continue
            
            try:
                page_name = str(row[0]).strip() if row[0] else None
                if not page_name:
                    skipped += 1
                    continue
                
                # Duplicate check
                if Page.query.filter_by(page_name=page_name).first():
                    skipped += 1
                    continue
                
                # FB Account lookup by name
                fb_account_name = str(row[3]).strip() if row[3] else None
                fb_account = FBAccount.query.filter_by(account_name=fb_account_name).first() if fb_account_name else None
                if not fb_account:
                    errors.append(f"Row {row_num}: FB Account '{fb_account_name}' nahi mila")
                    continue
                
                # BM lookup by name
                bm = None
                if row[4]:
                    bm_name = str(row[4]).strip()
                    bm = BusinessManager.query.filter_by(bm_name=bm_name).first()
                
                # Worker lookup
                worker = None
                if row[5]:
                    worker_name = str(row[5]).strip()
                    worker = User.query.filter_by(full_name=worker_name, role='worker').first()
                
                # Dates parse
                def parse_date(val):
                    if not val: return None
                    if isinstance(val, datetime): return val.date()
                    if isinstance(val, date): return val
                    try: return datetime.strptime(str(val).split()[0], '%Y-%m-%d').date()
                    except: return None
                
                monetization = str(row[6]).strip().lower() if row[6] else 'non_monetized'
                if monetization not in ['monetized', 'non_monetized', 'in_review', 'suspended']:
                    monetization = 'non_monetized'
                
                page = Page(
                    page_name=page_name,
                    page_url=str(row[1]).strip() if row[1] else None,
                    niche=str(row[2]).strip() if row[2] else None,
                    fb_account_id=fb_account.id,
                    bm_id=bm.id if bm else None,
                    assigned_worker_id=worker.id if worker else None,
                    monetization_status=monetization,
                    monetized_date=parse_date(row[7]),
                    page_created_date=parse_date(row[8]),
                    notes=str(row[9]).strip() if row[9] else None
                )
                db.session.add(page)
                imported += 1
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
        
        db.session.commit()
        
        msg = f'✅ {imported} pages import ho gaye'
        if skipped > 0: msg += f' | ⏭️ {skipped} skip kiye'
        if errors: msg += f' | ⚠️ {len(errors)} errors: ' + '; '.join(errors[:3])
        flash(msg, 'success' if imported > 0 else 'warning')
    except Exception as e:
        flash(f'Import error: {str(e)}', 'error')
    
    return redirect(url_for('pages'))


# ==================== BUSINESS MANAGERS - EXCEL ====================
@app.route('/business-managers')
@login_required
@owner_required
def business_managers():
    """BM list page"""
    bms = BusinessManager.query.order_by(BusinessManager.created_at.desc()).all()
    return render_template('business_managers.html', bms=bms)


@app.route('/business-managers/add', methods=['GET', 'POST'])
@login_required
@owner_required
def add_business_manager():
    if request.method == 'POST':
        bm = BusinessManager(
            bm_name=request.form.get('bm_name'),
            bm_id=request.form.get('bm_id'),
            fb_account_id=int(request.form.get('fb_account_id')),
            status=request.form.get('status', 'active')
        )
        db.session.add(bm)
        db.session.commit()
        flash('Business Manager add ho gaya', 'success')
        return redirect(url_for('business_managers'))
    
    fb_accounts_list = FBAccount.query.filter_by(status='active').all()
    return render_template('bm_form.html', bm=None, fb_accounts=fb_accounts_list)


@app.route('/business-managers/<int:bm_id>/edit', methods=['GET', 'POST'])
@login_required
@owner_required
def edit_business_manager(bm_id):
    bm = BusinessManager.query.get_or_404(bm_id)
    if request.method == 'POST':
        bm.bm_name = request.form.get('bm_name')
        bm.bm_id = request.form.get('bm_id')
        bm.fb_account_id = int(request.form.get('fb_account_id'))
        bm.status = request.form.get('status', 'active')
        db.session.commit()
        flash('Business Manager update ho gaya', 'success')
        return redirect(url_for('business_managers'))
    fb_accounts_list = FBAccount.query.filter_by(status='active').all()
    return render_template('bm_form.html', bm=bm, fb_accounts=fb_accounts_list)


@app.route('/business-managers/export')
@login_required
@owner_required
def export_business_managers():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Business Managers"
    
    headers = ['BM Name', 'BM ID Number', 'Linked FB Account', 'Status', 'Pages Count']
    _style_header(ws, headers, '7F77DD')
    
    bms = BusinessManager.query.all()
    for bm in bms:
        pages_count = Page.query.filter_by(bm_id=bm.id, is_active=True).count()
        ws.append([
            bm.bm_name,
            bm.bm_id or '',
            bm.fb_account.account_name if bm.fb_account else '',
            bm.status,
            pages_count
        ])
    
    for i, w in enumerate([25, 25, 25, 15, 15], 1):
        ws.column_dimensions[chr(64+i)].width = w
    
    return _excel_response(wb, f"business_managers_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")


@app.route('/business-managers/template')
@login_required
@owner_required
def bm_template():
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    headers = ['BM Name', 'BM ID Number', 'Linked FB Account', 'Status']
    _style_header(ws, headers, '7F77DD')
    ws.append(['Main BM', '123456789012345', 'Mudassar FB 1', 'active'])
    ws.append(['Backup BM', '987654321098765', 'Mudassar FB 2', 'active'])
    ws.cell(row=5, column=1, value='Note: FB Account exact match honi chahiye (account_name)').font = Font(italic=True, color='888888')
    for i, w in enumerate([25, 25, 25, 15], 1):
        ws.column_dimensions[chr(64+i)].width = w
    return _excel_response(wb, 'business_managers_template.xlsx')


@app.route('/business-managers/import', methods=['POST'])
@login_required
@owner_required
def import_business_managers():
    from openpyxl import load_workbook
    if 'excel_file' not in request.files or request.files['excel_file'].filename == '':
        flash('Koi file select nahi ki gayi', 'error')
        return redirect(url_for('business_managers'))
    
    try:
        wb = load_workbook(request.files['excel_file'], data_only=True)
        ws = wb.active
        imported, skipped, errors = 0, 0, []
        
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or not any(row):
                continue
            try:
                bm_name = str(row[0]).strip() if row[0] else None
                if not bm_name:
                    skipped += 1
                    continue
                if BusinessManager.query.filter_by(bm_name=bm_name).first():
                    skipped += 1
                    continue
                
                fb_acc_name = str(row[2]).strip() if row[2] else None
                fb_acc = FBAccount.query.filter_by(account_name=fb_acc_name).first() if fb_acc_name else None
                if not fb_acc:
                    errors.append(f"Row {row_num}: FB Account nahi mila")
                    continue
                
                bm = BusinessManager(
                    bm_name=bm_name,
                    bm_id=str(row[1]).strip() if row[1] else None,
                    fb_account_id=fb_acc.id,
                    status=str(row[3]).strip().lower() if row[3] else 'active'
                )
                db.session.add(bm)
                imported += 1
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
        
        db.session.commit()
        msg = f'✅ {imported} BMs import | ⏭️ {skipped} skip'
        if errors: msg += f' | ⚠️ {len(errors)} errors'
        flash(msg, 'success' if imported > 0 else 'warning')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('business_managers'))


# ==================== TEAM - EXCEL ====================
@app.route('/team/export')
@login_required
@owner_required
def export_team():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Team Members"
    
    headers = ['Full Name', 'Username', 'Role', 'Phone', 'Supervisor', 'Active', 'Joined']
    _style_header(ws, headers, 'd62976')
    
    members = User.query.filter(User.role != 'owner').all()
    for m in members:
        ws.append([
            m.full_name,
            m.username,
            m.role,
            m.phone or '',
            m.supervisor.full_name if m.supervisor else '',
            'Yes' if m.is_active else 'No',
            m.created_at.strftime('%Y-%m-%d') if m.created_at else ''
        ])
    
    for i, w in enumerate([25, 18, 15, 15, 25, 10, 14], 1):
        ws.column_dimensions[chr(64+i)].width = w
    
    return _excel_response(wb, f"team_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")


@app.route('/team/template')
@login_required
@owner_required
def team_template():
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    headers = ['Full Name', 'Username', 'Password', 'Role', 'Phone', 'Supervisor Name']
    _style_header(ws, headers, 'd62976')
    ws.append(['Ali Khan', 'ali_khan', 'password123', 'worker', '03001234567', 'Ahmad Supervisor'])
    ws.append(['Ahmad Hussain', 'ahmad_h', 'mypass456', 'supervisor', '03007654321', ''])
    
    notes = [
        '',
        'Notes:',
        '1. Role: worker, supervisor (owner allowed nahi)',
        '2. Supervisor Name: workers ke liye apne supervisor ka full_name',
        '3. Username unique hona chahiye',
        '4. Password kam az kam 6 characters'
    ]
    for i, note in enumerate(notes, start=5):
        cell = ws.cell(row=i, column=1, value=note)
        if i > 5:
            cell.font = Font(italic=True, color='888888', size=11)
    
    for i, w in enumerate([25, 18, 18, 15, 15, 25], 1):
        ws.column_dimensions[chr(64+i)].width = w
    
    return _excel_response(wb, 'team_template.xlsx')


@app.route('/team/import', methods=['POST'])
@login_required
@owner_required
def import_team():
    from openpyxl import load_workbook
    if 'excel_file' not in request.files or request.files['excel_file'].filename == '':
        flash('Koi file select nahi ki gayi', 'error')
        return redirect(url_for('team'))
    
    try:
        wb = load_workbook(request.files['excel_file'], data_only=True)
        ws = wb.active
        imported, skipped, errors = 0, 0, []
        
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or not any(row):
                continue
            try:
                full_name = str(row[0]).strip() if row[0] else None
                username = str(row[1]).strip() if row[1] else None
                password = str(row[2]).strip() if row[2] else None
                role = str(row[3]).strip().lower() if row[3] else None
                
                if not (full_name and username and password and role):
                    skipped += 1
                    continue
                
                if role not in ['worker', 'supervisor']:
                    errors.append(f"Row {row_num}: Invalid role '{role}'")
                    continue
                
                if User.query.filter_by(username=username).first():
                    skipped += 1
                    continue
                
                supervisor = None
                if role == 'worker' and row[5]:
                    supervisor = User.query.filter_by(
                        full_name=str(row[5]).strip(), role='supervisor'
                    ).first()
                
                user = User(
                    full_name=full_name,
                    username=username,
                    role=role,
                    phone=str(row[4]).strip() if row[4] else None,
                    supervisor_id=supervisor.id if supervisor else None,
                    is_active=True
                )
                user.set_password(password)
                db.session.add(user)
                imported += 1
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
        
        db.session.commit()
        msg = f'✅ {imported} members import | ⏭️ {skipped} skip'
        if errors: msg += f' | ⚠️ {len(errors)} errors: ' + '; '.join(errors[:3])
        flash(msg, 'success' if imported > 0 else 'warning')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('team'))


# ==================== PAGES ====================
@app.route('/pages')
@login_required
def pages():
    # Role-based filtering
    if current_user.is_worker():
        pages_list = Page.query.filter_by(assigned_worker_id=current_user.id, is_active=True).all()
    elif current_user.is_supervisor():
        team_worker_ids = [w.id for w in User.query.filter_by(supervisor_id=current_user.id).all()]
        pages_list = Page.query.filter(
            Page.assigned_worker_id.in_(team_worker_ids),
            Page.is_active == True
        ).all() if team_worker_ids else []
    else:  # owner
        pages_list = Page.query.filter_by(is_active=True).order_by(Page.created_at.desc()).all()
    
    return render_template('pages.html', pages=pages_list)


@app.route('/pages/add', methods=['GET', 'POST'])
@login_required
@owner_required
def add_page():
    if request.method == 'POST':
        page_created = request.form.get('page_created_date')
        monetized_date = request.form.get('monetized_date')
        
        page = Page(
            page_name=request.form.get('page_name'),
            page_url=request.form.get('page_url'),
            niche=request.form.get('niche'),
            fb_account_id=int(request.form.get('fb_account_id')),
            bm_id=int(request.form.get('bm_id')) if request.form.get('bm_id') else None,
            assigned_worker_id=int(request.form.get('assigned_worker_id')) if request.form.get('assigned_worker_id') else None,
            monetization_status=request.form.get('monetization_status', 'non_monetized'),
            page_created_date=datetime.strptime(page_created, '%Y-%m-%d').date() if page_created else None,
            monetized_date=datetime.strptime(monetized_date, '%Y-%m-%d').date() if monetized_date else None,
            notes=request.form.get('notes')
        )
        db.session.add(page)
        db.session.commit()
        flash('Page add ho gaya', 'success')
        return redirect(url_for('pages'))
    
    fb_accounts_list = FBAccount.query.filter_by(status='active').all()
    workers = User.query.filter(User.role.in_(['worker', 'supervisor']), User.is_active==True).all()
    bms = BusinessManager.query.filter_by(status='active').all()
    return render_template('page_form.html', page=None, fb_accounts=fb_accounts_list, workers=workers, bms=bms)


@app.route('/pages/<int:page_id>/edit', methods=['GET', 'POST'])
@login_required
@owner_required
def edit_page(page_id):
    page = Page.query.get_or_404(page_id)
    if request.method == 'POST':
        page_created = request.form.get('page_created_date')
        monetized_date = request.form.get('monetized_date')
        
        page.page_name = request.form.get('page_name')
        page.page_url = request.form.get('page_url')
        page.niche = request.form.get('niche')
        page.fb_account_id = int(request.form.get('fb_account_id'))
        page.bm_id = int(request.form.get('bm_id')) if request.form.get('bm_id') else None
        page.assigned_worker_id = int(request.form.get('assigned_worker_id')) if request.form.get('assigned_worker_id') else None
        page.monetization_status = request.form.get('monetization_status', 'non_monetized')
        page.page_created_date = datetime.strptime(page_created, '%Y-%m-%d').date() if page_created else None
        page.monetized_date = datetime.strptime(monetized_date, '%Y-%m-%d').date() if monetized_date else None
        page.notes = request.form.get('notes')
        db.session.commit()
        flash('Page update ho gaya', 'success')
        return redirect(url_for('pages'))
    
    fb_accounts_list = FBAccount.query.filter_by(status='active').all()
    workers = User.query.filter(User.role.in_(['worker', 'supervisor']), User.is_active==True).all()
    bms = BusinessManager.query.filter_by(status='active').all()
    return render_template('page_form.html', page=page, fb_accounts=fb_accounts_list, workers=workers, bms=bms)


# ==================== DAILY REPORTS ====================
@app.route('/reports/submit', methods=['GET', 'POST'])
@login_required
def submit_report():
    today = date.today()
    
    if current_user.is_worker():
        my_pages = Page.query.filter_by(assigned_worker_id=current_user.id, is_active=True).all()
    elif current_user.is_supervisor():
        team_worker_ids = [w.id for w in User.query.filter_by(supervisor_id=current_user.id).all()]
        my_pages = Page.query.filter(Page.assigned_worker_id.in_(team_worker_ids + [current_user.id])).all()
    else:
        my_pages = Page.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        page_id = int(request.form.get('page_id'))
        report_date_str = request.form.get('report_date', today.strftime('%Y-%m-%d'))
        report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
        
        # Check duplicate
        existing = DailyReport.query.filter_by(page_id=page_id, report_date=report_date).first()
        if existing:
            existing.views = int(request.form.get('views') or 0)
            existing.reach = int(request.form.get('reach') or 0)
            existing.followers_gained = int(request.form.get('followers_gained') or 0)
            # Earnings sirf owner update kar sake
            if current_user.is_owner():
                existing.earnings_usd = float(request.form.get('earnings_usd') or 0)
            existing.notes = request.form.get('notes')
            flash('Report update ho gayi', 'success')
        else:
            report = DailyReport(
                page_id=page_id,
                worker_id=current_user.id,
                report_date=report_date,
                views=int(request.form.get('views') or 0),
                reach=int(request.form.get('reach') or 0),
                followers_gained=int(request.form.get('followers_gained') or 0),
                earnings_usd=float(request.form.get('earnings_usd') or 0) if current_user.is_owner() else 0,
                notes=request.form.get('notes')
            )
            db.session.add(report)
            flash('Report submit ho gayi', 'success')
        
        db.session.commit()
        return redirect(url_for('submit_report'))
    
    # Aaj ki submitted reports
    today_reports = DailyReport.query.filter_by(report_date=today).all()
    submitted_page_ids = [r.page_id for r in today_reports if r.worker_id == current_user.id]
    
    return render_template('submit_report.html', 
        pages=my_pages, 
        today=today,
        submitted_page_ids=submitted_page_ids
    )


@app.route('/reports')
@login_required
def reports_list():
    """Reports list with role-based earnings visibility"""
    days = int(request.args.get('days', 7))
    start_date = date.today() - timedelta(days=days)
    
    query = DailyReport.query.filter(DailyReport.report_date >= start_date)
    
    if current_user.is_worker():
        query = query.filter(DailyReport.worker_id == current_user.id)
    elif current_user.is_supervisor():
        team_ids = [w.id for w in User.query.filter_by(supervisor_id=current_user.id).all()]
        team_ids.append(current_user.id)
        query = query.filter(DailyReport.worker_id.in_(team_ids))
    
    reports = query.order_by(DailyReport.report_date.desc()).all()
    return render_template('reports_list.html', reports=reports, days=days)


# ==================== TEAM MANAGEMENT ====================
@app.route('/team')
@login_required
@owner_or_supervisor
def team():
    if current_user.is_owner():
        members = User.query.filter(User.role != 'owner').order_by(User.role, User.full_name).all()
    else:
        # Supervisor sirf apni team
        members = User.query.filter_by(supervisor_id=current_user.id).all()
    return render_template('team.html', members=members)


@app.route('/team/add', methods=['GET', 'POST'])
@login_required
@owner_required
def add_team_member():
    if request.method == 'POST':
        user = User(
            username=request.form.get('username'),
            full_name=request.form.get('full_name'),
            role=request.form.get('role'),
            phone=request.form.get('phone'),
            supervisor_id=int(request.form.get('supervisor_id')) if request.form.get('supervisor_id') else None
        )
        user.set_password(request.form.get('password'))
        db.session.add(user)
        db.session.commit()
        flash(f'{user.full_name} add ho gaya', 'success')
        return redirect(url_for('team'))
    
    supervisors = User.query.filter_by(role='supervisor', is_active=True).all()
    return render_template('team_form.html', member=None, supervisors=supervisors)


# ==================== PAYMENTS (OWNER ONLY) ====================
@app.route('/payments')
@login_required
@owner_required
def payments():
    payments_list = TeamPayment.query.order_by(TeamPayment.month.desc(), TeamPayment.created_at.desc()).all()
    
    # Summary
    total_pending_fb = sum(p.total_earned_usd for p in payments_list if not p.received_from_fb)
    total_pending_pay = sum(p.agreed_amount_pkr for p in payments_list if p.received_from_fb and not p.paid_to_member)
    total_paid = sum(p.agreed_amount_pkr for p in payments_list if p.paid_to_member)
    
    return render_template('payments.html', 
        payments=payments_list,
        total_pending_fb=total_pending_fb,
        total_pending_pay=total_pending_pay,
        total_paid=total_paid
    )


@app.route('/payments/add', methods=['GET', 'POST'])
@login_required
@owner_required
def add_payment():
    if request.method == 'POST':
        payment = TeamPayment(
            user_id=int(request.form.get('user_id')),
            month=request.form.get('month'),
            total_earned_usd=float(request.form.get('total_earned_usd') or 0),
            agreed_amount_pkr=float(request.form.get('agreed_amount_pkr') or 0),
            notes=request.form.get('notes')
        )
        db.session.add(payment)
        db.session.commit()
        flash('Payment entry add ho gayi', 'success')
        return redirect(url_for('payments'))
    
    members = User.query.filter(User.role.in_(['supervisor', 'worker']), User.is_active==True).all()
    return render_template('payment_form.html', members=members)


@app.route('/payments/<int:pid>/mark-received', methods=['POST'])
@login_required
@owner_required
def mark_received(pid):
    payment = TeamPayment.query.get_or_404(pid)
    payment.received_from_fb = True
    payment.received_date = date.today()
    db.session.commit()
    flash('FB se received mark ho gaya', 'success')
    return redirect(url_for('payments'))


@app.route('/payments/<int:pid>/mark-paid', methods=['POST'])
@login_required
@owner_required
def mark_paid(pid):
    payment = TeamPayment.query.get_or_404(pid)
    payment.paid_to_member = True
    payment.payment_date = date.today()
    payment.payment_method = request.form.get('payment_method', 'Cash')
    payment.payment_reference = request.form.get('payment_reference')
    db.session.commit()
    flash('Payment paid mark ho gaya', 'success')
    return redirect(url_for('payments'))


# ==================== INITIALIZE ====================
@app.cli.command('init-db')
def init_db_command():
    """Database initialize karne ke liye"""
    init_db(app)


with app.app_context():
    db.create_all()
    init_db(app)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
