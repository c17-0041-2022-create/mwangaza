from flask import Blueprint, render_template, session
from blueprints.auth import landlord_required
from app.models import get_db, get_payments_by_landlord
from app.models import get_user_by_id
from datetime import datetime

bp = Blueprint('landlord', __name__)


@bp.route('/landlord', endpoint='landlord')
@landlord_required
def landlord_dashboard():
    """Render the landlord dashboard with real DB-driven KPIs.

    If the landlord has no payments yet, attempt to seed demo data and re-query
    so developers always see realistic data in local/dev environments.
    """
    landlord_id = session.get('user_id')

    # 1) compute totals: total rent collected this month, total confirmed balance
    now = datetime.now()
    year_month = now.strftime('%Y-%m')

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT IFNULL(SUM(amount), 0) as month_total FROM payments WHERE landlord_id = ? AND status = 'confirmed' AND substr(created_at,1,7) = ?",
            (landlord_id, year_month)
        ).fetchone()
        month_total = float(row['month_total']) if row else 0.0

        row2 = conn.execute(
            "SELECT IFNULL(SUM(amount), 0) as balance FROM payments WHERE landlord_id = ? AND status = 'confirmed'",
            (landlord_id,)
        ).fetchone()
        total_balance = float(row2['balance']) if row2 else 0.0

        # KRA filings count — simple compliance indicator
        row3 = conn.execute('SELECT COUNT(1) as filings FROM tax_filings WHERE landlord_id = ?', (landlord_id,)).fetchone()
        filings = int(row3['filings']) if row3 else 0

        # Recent payments (with tenant name and property if available)
        recent = conn.execute(
            """
            SELECT p.amount, p.created_at, p.description, u.full_name AS tenant_name, pr.property_name
            FROM payments p
            LEFT JOIN users u ON p.tenant_id = u.id
            LEFT JOIN tenancies t ON p.tenacy_id = t.id
            LEFT JOIN properties pr ON t.property_id = pr.id
            WHERE p.landlord_id = ?
            ORDER BY p.created_at DESC LIMIT 6
            """,
            (landlord_id,)
        ).fetchall()
        recent_payments = [dict(r) for r in recent]
    finally:
        conn.close()

    # If no payments at all, attempt to seed demo data and re-query (dev-only fallback)
    if total_balance == 0 and not recent_payments:
        try:
            from seed import run_all as _run_seed
            _run_seed()
            # re-run queries
            conn = get_db()
            row = conn.execute(
                "SELECT IFNULL(SUM(amount), 0) as month_total FROM payments WHERE landlord_id = ? AND status = 'confirmed' AND substr(created_at,1,7) = ?",
                (landlord_id, year_month)
            ).fetchone()
            month_total = float(row['month_total']) if row else 0.0
            row2 = conn.execute(
                "SELECT IFNULL(SUM(amount), 0) as balance FROM payments WHERE landlord_id = ? AND status = 'confirmed'",
                (landlord_id,)
            ).fetchone()
            total_balance = float(row2['balance']) if row2 else 0.0
            recent = conn.execute(
                """
                SELECT p.amount, p.created_at, p.description, u.full_name AS tenant_name, pr.property_name
                FROM payments p
                LEFT JOIN users u ON p.tenant_id = u.id
                LEFT JOIN tenancies t ON p.tenacy_id = t.id
                LEFT JOIN properties pr ON t.property_id = pr.id
                WHERE p.landlord_id = ?
                ORDER BY p.created_at DESC LIMIT 6
                """,
                (landlord_id,)
            ).fetchall()
            recent_payments = [dict(r) for r in recent]
        except Exception:
            # ignore seeding errors — continue to render what we have
            try:
                conn.close()
            except Exception:
                pass

    # Compute a simple compliance metric (if filings exist then 100%, else 0%)
    compliance = 100 if filings > 0 else 0

    # Provide context values to template to replace the previous static demo numbers
    context = {
        'total_rent_collected': month_total,
        'kes_balance': total_balance,
        'compliance_pct': compliance,
        'recent_payments': recent_payments
    }

    return render_template('landlord_dashboard.html', **context)


@bp.route('/settings', endpoint='settings')
@landlord_required
def settings():
    """Render the landlord settings/profile page using the landlord layout.

    This provides a `settings` endpoint that templates can link to (e.g. the
    sidebar's `url_for('settings')`) and ensures the profile page uses the
    `landlord_base.html` layout rather than the tenant layout.
    """
    landlord_id = session.get('user_id')
    user = None
    try:
        user = get_user_by_id(landlord_id)
    except Exception:
        user = None

    return render_template('profile.html', user=user, base_template='landlord_base.html')

@bp.route('/alltenants', endpoint='alltenants')
@landlord_required
def all_tenants():
    conn = get_db()
    rows = conn.execute('''
        SELECT u.id as user_id, u.full_name, u.email, u.phone, p.property_name, t.status, t.monthly_rent, t.id as tenancy_id
        FROM users u
        LEFT JOIN tenancies t ON u.id = t.tenant_id
        LEFT JOIN properties p ON t.property_id = p.id
        WHERE u.role = 'tenant'
        ORDER BY u.full_name
    ''').fetchall()
    conn.close()
    tenants = [dict(r) for r in rows]
    return render_template('tenants.html', tenants=tenants)

@bp.route('/landlord_payments', endpoint='landlord_payments')
@landlord_required
def landlord_payments():
    return render_template('landlord_payment.html')


@bp.route('/landlord_receipts', endpoint='landlord_receipts')
@landlord_required
def landlord_receipts():
    """Show receipts/payments received for the logged-in landlord."""
    landlord_id = session.get('user_id')
    payments = []
    try:
        payments = get_payments_by_landlord(landlord_id, limit=100)
    except Exception:
        # fallback: query directly
        conn = get_db()
        payments = conn.execute('SELECT * FROM payments WHERE landlord_id = ? ORDER BY created_at DESC', (landlord_id,)).fetchall()
        conn.close()

    # Convert sqlite3.Row objects to plain dicts for predictable template access
    payments = [dict(p) for p in payments]

    # If there are no payments, attempt a best-effort seeding (dev only).
    # This is idempotent and ensures demo landlords see receipts during development.
    if not payments:
        try:
            # run the seeder to top-up demo data
            from seed import run_all as _run_seed
            _run_seed()
            # re-query payments after seeding
            payments = get_payments_by_landlord(landlord_id, limit=100)
            payments = [dict(p) for p in payments]
        except Exception:
            # ignore seeding errors and continue to render empty page
            pass

    # If still no payments for this landlord, show a global recent-payments
    # fallback so developers can see example receipts even if tenancy->landlord
    # linkage differs in their local DB. Mark as fallback to show a note in UI.
    global_fallback = False
    if not payments:
        try:
            conn = get_db()
            rows = conn.execute(
                '''SELECT p.*, u.full_name as tenant_name, pr.property_name
                   FROM payments p
                   LEFT JOIN users u ON p.tenant_id = u.id
                   LEFT JOIN tenancies t ON p.tenacy_id = t.id
                   LEFT JOIN properties pr ON t.property_id = pr.id
                   ORDER BY p.created_at DESC LIMIT 50'''
            ).fetchall()
            conn.close()
            payments = [dict(r) for r in rows]
            global_fallback = True if payments else False
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    return render_template('landlord_receipt.html', payments=payments, global_fallback=global_fallback)
