# 📊 FB Manager - Facebook Pages & Earnings Management System

Aap ke Facebook monetization business ke liye complete management system. BizHisaab jaisa hi, Flask + SQLite par bana hua.

## 🎯 Features

### Role-Based Access Control
- **Owner (Aap)**: Sab kuch dekh sakte hain — earnings, payments, profit
- **Supervisor**: Apni team ki performance dekhe (NO $ amounts)
- **Worker**: Sirf apne pages aur daily reports submit kare (NO $)

### Core Modules
1. **FB Accounts** — Multiple Facebook IDs ka tracking
2. **Business Managers** — BM accounts linked to FB IDs
3. **Pages** — Har page ka complete data (FB account, BM, worker, niche, monetization status)
4. **Daily Reports** — Worker daily views/reach submit kare, owner earnings add kare
5. **Team Management** — Workers aur supervisors add karna, role assign karna
6. **Payments (Owner Only)** — 3-step payment flow:
   - Step 1: Owner add kare "X member ne $Y earn kiya"
   - Step 2: Jab FB se payout aaye → "Received" mark karen
   - Step 3: Jab member ko pay karen → "Paid" mark karen

## 🚀 Local Setup

```bash
# 1. Dependencies install karen
pip install -r requirements.txt

# 2. App run karen
python app.py
```

Browser mein khulen: `http://localhost:5000`

**Default Login:**
- Username: `mudassar`
- Password: `admin123`

⚠️ **First login ke baad password change kar dein!**

## ☁️ Railway Deployment

BizHisaab ki tarah Railway pe deploy karne ke liye:

1. **GitHub** par push karen
2. Railway dashboard pe **New Project → Deploy from GitHub**
3. Railway automatically `requirements.txt` aur `Procfile` detect kare ga
4. **PostgreSQL** add karen (Railway → New → Database → PostgreSQL)
5. Environment variables set karen:
   - `SECRET_KEY` = koi long random string
   - `DATABASE_URL` = automatically set ho jata hai PostgreSQL se

## 📋 Pehli Dafa Use Kaise Karen?

### Step 1: Login karen (Owner)
Default credentials se login karen.

### Step 2: FB Accounts add karen
Sidebar → FB Accounts → + Add Account
Apni sari FB IDs add karen — naam, email, status.

### Step 3: Team Members add karen
Sidebar → Team → + Add Member
Workers aur Supervisors add karen, supervisors ke neeche workers assign karen.

### Step 4: Pages add karen
Sidebar → Pages → + Add Page
Har page add karen, FB account select karen, worker assign karen, monetization status set karen.

### Step 5: Workers ko login dein
Workers ko unka username/password den. Wo apne dashboard se daily report submit karen ge.

### Step 6: Daily Reports
Workers daily views/reach submit karen ge. Aap (owner) un par earnings add kar saken ge.

### Step 7: Payments Track karen
Month end pe Payments module use karen — pending FB receipts, team payments track karen.

## 🔐 Security Notes

- Earnings field sirf owner ke views mein appear hota hai
- Database mein bhi store hota hai lekin worker/supervisor ke routes par hide
- Role-based decorators (`@owner_required`) har sensitive route par lagaye gaye hain

## 🛠️ Tech Stack

- **Backend**: Flask 3.0 + Flask-Login + Flask-SQLAlchemy
- **Database**: SQLite (local) / PostgreSQL (Railway production)
- **Frontend**: Jinja2 templates + Custom CSS + Chart.js
- **Auth**: Werkzeug password hashing
- **Deployment**: Gunicorn + Railway

## 📞 Support

Mudassar bhai, koi bhi feature add karwana ho ya bug fix karwana ho, batayen!

---
Built for **Ecomlink / Facebook Monetization Business** 🇵🇰
