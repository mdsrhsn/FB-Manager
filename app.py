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
            purchase_date=datetime.strptime(purchase_date, '%Y-%m-%d').date() if purchase_date else None,
            purchase_cost=float(request.form.get('purchase_cost') or 0),
            status=request.form.get('status', 'active'),
            notes=request.form.get('notes')
        )
        db.session.add(account)
        db.session.commit()
        flash('FB Account add ho gaya', 'success')
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
        account.purchase_date = datetime.strptime(purchase_date, '%Y-%m-%d').date() if purchase_date else None
        account.purchase_cost = float(request.form.get('purchase_cost') or 0)
        account.status = request.form.get('status', 'active')
        account.notes = request.form.get('notes')
        db.session.commit()
        flash('FB Account update ho gaya', 'success')
        return redirect(url_for('fb_accounts'))
    
    return render_template('fb_account_form.html', account=account)


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


if __name__ == '__main__':
    init_db(app)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
    if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(host="0.0.0.0", port=5000)
    git add .
git commit -m "Fixed SQLAlchemy app context"
git push
