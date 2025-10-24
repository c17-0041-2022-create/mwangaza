import os
from functools import wraps
from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, session
)
from werkzeug.security import generate_password_hash, check_password_hash

from models import (
    get_db, add_user, get_user_by_email, get_user_by_id, update_user
)

from models import ensure_demo_data


def _ensure_demo_session(role='tenant'):
    """Seed demo data if needed and set a session user for dev when auth is off.

    This ensures routes like `/tenant` have a valid `session['user_id']` and
    templates render real DB values instead of placeholders.
    """
    try:
        ensure_demo_data()
    except Exception:
        pass

    if 'user_id' in session:
        return

    try:
        conn = get_db()
        row = conn.execute('SELECT * FROM users WHERE role = ? ORDER BY id LIMIT 1', (role,)).fetchone()
        conn.close()
        if row:
            session['user_id'] = row['id']
            session['username'] = row['username']
            session['email'] = row['email']
            session['role'] = row['role']
            session['full_name'] = row['full_name']
    except Exception:
        return

bp = Blueprint('auth', __name__, template_folder='../templates')


def _normalize_phone(msisdn: str) -> str:
    """Normalize common phone formats into '2547XXXXXXXX'."""
    if not msisdn:
        return ''
    s = msisdn.strip()
    for ch in [' ', '+', '-', '(', ')']:
        s = s.replace(ch, '')
    if s.startswith('0'):
        s = '254' + s[1:]
    if s.startswith('7'):
        s = '254' + s
    if not s.isdigit():
        s = ''.join([c for c in s if c.isdigit()])
    return s

# ===========================
#  AUTHENTICATION TOGGLE
# ===========================
AUTH_DISABLED = True  # ⚠️ Disable auth for now (dev mode)


# ===========================
#  DECORATORS
# ===========================

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if AUTH_DISABLED:
            try:
                _ensure_demo_session()
            except Exception:
                pass
            return f(*args, **kwargs)
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return wrapper


def tenant_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if AUTH_DISABLED:
            try:
                _ensure_demo_session(role='tenant')
            except Exception:
                pass
            return f(*args, **kwargs)
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'tenant':
            flash('Access denied — tenant access only.', 'error')
            return redirect(url_for('general.index'))
        return f(*args, **kwargs)
    return wrapper


def landlord_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if AUTH_DISABLED:
            try:
                _ensure_demo_session(role='landlord')
            except Exception:
                pass
            return f(*args, **kwargs)
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'landlord':
            flash('Access denied — landlord access only.', 'error')
            return redirect(url_for('general.index'))
        return f(*args, **kwargs)
    return wrapper


# ===========================
#  AUTH ROUTES
# ===========================

@bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if request.method == 'POST':
        data = {k: request.form.get(k, '').strip() for k in
                ['username', 'email', 'password', 'confirm_password', 'role', 'full_name', 'phone', 'kra_pin']}

        # --- Basic validation
        if not all([data['username'], data['email'], data['password'], data['confirm_password'], data['role']]):
            flash('Please fill in all required fields.', 'error')
            return render_template('register.html')

        if data['password'] != data['confirm_password']:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')

        if len(data['password']) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return render_template('register.html')

        if data['role'] not in ['tenant', 'landlord']:
            flash('Invalid role selected.', 'error')
            return render_template('register.html')

        if get_user_by_email(data['email']):
            flash('Email already registered. Please login.', 'warning')
            return redirect(url_for('auth.login'))

        # Normalize phone before storing
        data['phone'] = _normalize_phone(data.get('phone', ''))

        # --- Create user
        try:
            add_user(
                data['username'], data['email'],
                generate_password_hash(data['password']),
                data['role'], data['full_name'], data['phone'], data['kra_pin']
            )
            flash(f'Registration successful! Please log in as {data["role"]}.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            flash(f'Error during registration: {e}', 'error')

    return render_template('register.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login route"""
    if AUTH_DISABLED:
        flash('Authentication temporarily disabled — you are logged in as demo.', 'info')
        session['user_id'] = 1
        session['username'] = 'demo_user'
        session['role'] = 'tenant'
        session['email'] = 'demo@mwangaza.app'
        session['full_name'] = 'Demo Tenant'
        return redirect(url_for('tenant'))

    if request.method == 'POST':
        email = request.form.get('email', '').lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please enter both email and password.', 'error')
            return render_template('login.html')

        user = get_user_by_email(email)
        if not user or not check_password_hash(user['password_hash'], password):
            flash('Invalid credentials.', 'error')
            return render_template('login.html')

        session.clear()
        session.update({
            'user_id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'role': user['role'],
            'full_name': user['full_name']
        })
        flash(f'Welcome back, {user["username"]}!', 'success')

        return redirect(url_for('landlord') if user['role'] == 'landlord' else url_for('tenant'))

    return render_template('login.html')


@bp.route('/logout')
def logout():
    if AUTH_DISABLED:
        flash('Auth disabled — logout skipped.', 'info')
        return redirect(url_for('general.index'))

    username = session.get('username', 'User')
    session.clear()
    flash(f'Goodbye, {username}.', 'success')
    return redirect(url_for('auth.login'))


# ===========================
#  PROFILE MANAGEMENT
# ===========================

@bp.route('/profile')
@login_required
def profile():
    if AUTH_DISABLED:
        demo_user = {
            'username': 'demo_user',
            'email': 'demo@mwangaza.app',
            'full_name': 'Demo Account',
            'phone': '+254700000000',
            'kra_pin': 'A123456789X',
            'role': 'tenant'
        }
        flash('Auth disabled — showing demo profile.', 'info')
        # choose base template based on role so tenants/landlords see correct layout
        base = 'landlord_base.html' if demo_user.get('role') == 'landlord' else 'tenant_base.html'
        return render_template('profile.html', user=demo_user, base_template=base)

    user = get_user_by_id(session['user_id'])
    base = 'landlord_base.html' if (user and user.get('role') == 'landlord') or session.get('role') == 'landlord' else 'tenant_base.html'
    return render_template('profile.html', user=user, base_template=base)


@bp.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    if AUTH_DISABLED:
        flash('Auth disabled — no profile updates applied.', 'info')
        return redirect(url_for('auth.profile'))

    updates = {
        'full_name': request.form.get('full_name'),
        'phone': _normalize_phone(request.form.get('phone')),
        'kra_pin': request.form.get('kra_pin'),
        'email': request.form.get('email').lower()
    }

    try:
        update_user(session['user_id'], **updates)
        session.update({k: v for k, v in updates.items() if v})
        flash('Profile updated successfully.', 'success')
    except Exception as e:
        flash(f'Error updating profile: {e}', 'error')

    return redirect(url_for('auth.profile'))
