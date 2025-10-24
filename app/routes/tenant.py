from flask import Blueprint, render_template, session
from blueprints.auth import tenant_required
from app.models import (
    get_tenancies_by_tenant,
    get_latest_payment_by_tenant,
    get_mpesa_balance_by_tenant,
    get_recent_activities_by_user,
    get_user_by_id,
    ensure_demo_data,
    get_payments_by_tenant,
    get_db
)

bp = Blueprint('tenant', __name__)


@bp.route('/tenant', endpoint='tenant')
@tenant_required
def tenant_dashboard():
    try:
        ensure_demo_data()
    except Exception:
        pass

    user_id = session.get('user_id')
    tenancies = get_tenancies_by_tenant(user_id) or []
    tenancy = tenancies[0] if tenancies else None

    last_payment = get_latest_payment_by_tenant(user_id)
    mpesa_balance = get_mpesa_balance_by_tenant(user_id)
    recent_activities = get_recent_activities_by_user(user_id, limit=5)

    # If no tenancy was found for the current session user, fall back to a
    # seeded tenancy (first available). This prevents the dashboard from
    # rendering empty placeholders when session or tenancy linkage is missing.
    if not tenancy:
        try:
            conn = get_db()
            sample = conn.execute(
                '''SELECT t.*, p.property_name, u.full_name AS landlord_name
                   FROM tenancies t
                   JOIN properties p ON t.property_id = p.id
                   JOIN users u ON t.landlord_id = u.id
                   LIMIT 1'''
            ).fetchone()
            conn.close()
            if sample:
                tenancy = sample
                # If we picked a sample tenancy, adjust derived values too
                last_payment = get_latest_payment_by_tenant(tenancy['tenant_id'])
                mpesa_balance = get_mpesa_balance_by_tenant(tenancy['tenant_id'])
                recent_activities = get_recent_activities_by_user(tenancy['tenant_id'], limit=5)
        except Exception:
            pass

    kra_status = 'Not filed'
    try:
        if tenancy:
            conn = get_db()
            row = conn.execute('SELECT COUNT(1) as c FROM tax_filings WHERE landlord_id = ?', (tenancy['landlord_id'],)).fetchone()
            conn.close()
            if row and row['c'] > 0:
                kra_status = 'Filed'
    except Exception:
        pass

    return render_template('tenant_dashboard.html',
                           tenancy=tenancy,
                           last_payment=last_payment,
                           mpesa_balance=mpesa_balance,
                           recent_activities=recent_activities,
                           kra_status=kra_status)

@bp.route('/tenant_activity', endpoint='tenantactivity')
@tenant_required
def tenant_activity():
    user_id = session.get('user_id')
    recent_activities = get_recent_activities_by_user(user_id, limit=100)
    return render_template('tenant_activity.html', activities=recent_activities)

@bp.route('/tenant_payments', endpoint='tenantpayments')
@tenant_required
def tenant_payments():
    user_id = session.get('user_id')
    payments = get_payments_by_tenant(user_id, limit=20)
    tenancies = get_tenancies_by_tenant(user_id) or []
    tenancy = tenancies[0] if tenancies else None
    user = get_user_by_id(user_id)
    return render_template('tenant_payment.html', payments=payments, tenancy=tenancy, user=user)

@bp.route('/tenant_receipt', endpoint='tenantreceipt')
@tenant_required
def tenant_receipt():
    user_id = session.get('user_id')
    last_payment = get_latest_payment_by_tenant(user_id)
    tenancy = (get_tenancies_by_tenant(user_id) or [None])[0]
    landlord = None
    if tenancy:
        conn = get_db()
        landlord = conn.execute('SELECT * FROM users WHERE id = ?', (tenancy['landlord_id'],)).fetchone()
        conn.close()
    return render_template('tenant_receipt.html', payment=last_payment, tenancy=tenancy, landlord=landlord)

@bp.route('/tenant_settings', endpoint='tenantsettings')
@tenant_required
def tenant_settings():
    user = get_user_by_id(session.get('user_id'))
    return render_template('tenant_settings.html', user=user)
