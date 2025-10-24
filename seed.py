"""Database seeder to ensure each table has at least 10 complete rows.

Run this script to populate or top-up the local sqlite DB with realistic demo rows.
It is safe to run multiple times; it only inserts new rows to reach target counts.
"""
from datetime import datetime, timedelta
import random
from werkzeug.security import generate_password_hash

from models import get_db, get_user_count, add_user, add_property, add_tenancy, add_payment, add_activity


TARGET = 10


def count(table_name):
    conn = get_db()
    row = conn.execute(f"SELECT COUNT(1) as c FROM {table_name}").fetchone()
    conn.close()
    return row['c'] if row else 0


def seed_users():
    existing = count('users')
    to_create = max(0, TARGET - existing)
    if to_create <= 0:
        print('users OK:', existing)
        return

    # Create a mix of landlords and tenants
    for i in range(to_create):
        role = 'landlord' if i < max(1, to_create // 4) else 'tenant'
        idx = existing + i + 1
        username = f'user{idx}'
        email = f'user{idx}@example.com'
        pw = generate_password_hash('password123')
        full_name = f"Demo User {idx}"
        phone = f"+2547{random.randint(10000000,99999999)}"
        kra = f"KRA{idx:08d}"
        try:
            add_user(username, email, pw, role, full_name, phone, kra)
        except Exception:
            # ignore duplicates
            continue
    print('users seeded ->', count('users'))


def seed_properties():
    existing = count('properties')
    to_create = max(0, TARGET - existing)
    if to_create <= 0:
        print('properties OK:', existing)
        return

    conn = get_db()
    landlords = conn.execute("SELECT id FROM users WHERE role='landlord'").fetchall()
    if not landlords:
        # promote some users to landlords
        u = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
        if u:
            conn.execute("UPDATE users SET role='landlord' WHERE id = ?", (u['id'],))
            conn.commit()
            landlords = conn.execute("SELECT id FROM users WHERE role='landlord'").fetchall()

    landlord_ids = [l['id'] for l in landlords]
    if not landlord_ids:
        conn.close()
        print('no landlords to assign properties to')
        return

    for i in range(to_create):
        landlord_id = random.choice(landlord_ids)
        idx = existing + i + 1
        name = f"Demo Property {idx}"
        address = f"{idx} Demo Road, Nairobi"
        monthly_rent = random.choice([20000, 25000, 30000, 35000, 40000])
        try:
            add_property(landlord_id, name, address, monthly_rent)
        except Exception:
            continue

    conn.close()
    print('properties seeded ->', count('properties'))


def seed_tenancies():
    existing = count('tenancies')
    to_create = max(0, TARGET - existing)
    if to_create <= 0:
        print('tenancies OK:', existing)
        return

    conn = get_db()
    tenants = conn.execute("SELECT id FROM users WHERE role='tenant'").fetchall()
    properties = conn.execute('SELECT id, landlord_id, monthly_rent FROM properties').fetchall()

    tenant_ids = [t['id'] for t in tenants]
    prop_list = [p for p in properties]

    if not tenant_ids or not prop_list:
        conn.close()
        print('need tenants and properties to create tenancies')
        return

    for i in range(to_create):
        tenant_id = random.choice(tenant_ids)
        prop = random.choice(prop_list)
        property_id = prop['id']
        landlord_id = prop['landlord_id']
        monthly_rent = prop['monthly_rent']
        start_date = (datetime.now() - timedelta(days=random.randint(30, 365))).date()
        try:
            add_tenancy(tenant_id, property_id, landlord_id, monthly_rent, start_date)
        except Exception:
            continue

    conn.close()
    print('tenancies seeded ->', count('tenancies'))


def seed_payments():
    existing = count('payments')
    to_create = max(0, TARGET - existing)
    if to_create <= 0:
        print('payments OK:', existing)
    else:
        conn = get_db()
        tenancies = conn.execute('SELECT * FROM tenancies').fetchall()
        if not tenancies:
            conn.close()
            print('no tenancies for payments')
        else:
            for i in range(to_create):
                t = random.choice(tenancies)
                tenant_id = t['tenant_id']
                landlord_id = t['landlord_id']
                tenacy_id = t['id']
                amount = t['monthly_rent'] if t['monthly_rent'] else random.choice([20000, 30000, 35000])
                desc = random.choice(['Rent Payment', 'Water Bill', 'Electricity'])
                status = random.choice(['confirmed', 'pending'])
                try:
                    # Occasionally attach a merchant_request_id to simulate STK payments
                    mrid = None
                    if status == 'confirmed' and random.random() < 0.3:
                        mrid = f"MR{random.randint(100000,999999)}-{i}"
                    add_payment(tenant_id, landlord_id, amount, description=f"{desc} - {datetime.now().year}", status=status, tenacy_id=tenacy_id, merchant_request_id=mrid)
                except Exception:
                    continue

            conn.close()
            print('payments seeded ->', count('payments'))

    # Ensure each landlord has at least TARGET receipts (payments) so landlord
    # receipts pages always show some data. We try to attach payments to
    # existing tenancies for that landlord; if none exist, assign a random
    # tenant as the payer.
    try:
        conn = get_db()
        landlords = conn.execute("SELECT id FROM users WHERE role='landlord'").fetchall()
        for l in landlords:
            lid = l['id']
            row = conn.execute('SELECT COUNT(1) as c FROM payments WHERE landlord_id = ?', (lid,)).fetchone()
            cur = row['c'] if row else 0
            needed = max(0, TARGET - cur)
            if needed <= 0:
                continue

            # find tenancies for this landlord
            ten = conn.execute('SELECT * FROM tenancies WHERE landlord_id = ?', (lid,)).fetchall()
            ten_list = [t for t in ten]

            # find any tenants to use as fallback
            tenants = conn.execute("SELECT id FROM users WHERE role='tenant'").fetchall()
            tenant_ids = [t['id'] for t in tenants]

            for _ in range(needed):
                if ten_list:
                    t = random.choice(ten_list)
                    tenant_id = t['tenant_id']
                    tenacy_id = t['id']
                    amount = t['monthly_rent'] if t['monthly_rent'] else random.choice([20000, 30000, 35000])
                else:
                    tenant_id = random.choice(tenant_ids) if tenant_ids else None
                    tenacy_id = None
                    amount = random.choice([5000, 1500, 20000, 35000])

                desc = random.choice(['Rent Payment', 'Service Charge', 'Maintenance Reimbursement'])
                try:
                    # For landlord receipts ensure some payments have merchant_request_id
                    mrid = f"MR{random.randint(100000,999999)}-l{lid}" if random.random() < 0.25 else None
                    add_payment(tenant_id, lid, amount, description=f"{desc} - {datetime.now().year}", status='confirmed', tenacy_id=tenacy_id, merchant_request_id=mrid)
                except Exception:
                    continue

        conn.close()
        print('landlord receipts ensured ->', count('payments'))
    except Exception:
        # best-effort; ignore seeding errors
        try:
            conn.close()
        except Exception:
            pass


def seed_activities():
    existing = count('activities')
    to_create = max(0, TARGET - existing)
    if to_create <= 0:
        print('activities OK:', existing)
        return

    conn = get_db()
    users = conn.execute('SELECT id FROM users').fetchall()
    if not users:
        conn.close()
        print('no users for activities')
        return

    for i in range(to_create):
        u = random.choice(users)
        user_id = u['id']
        activity_type = random.choice(['payment', 'maintenance', 'notice'])
        description = random.choice([
            'Rent Payment posted', 'Maintenance Request', 'Lease signed', 'Received invoice', 'Payment reminder'
        ])
        amount = random.choice([None, 1500, 35000, 20000])
        status = random.choice(['confirmed', 'pending', 'info'])
        try:
            add_activity(user_id, activity_type, description, amount, status)
        except Exception:
            continue

    conn.close()
    print('activities seeded ->', count('activities'))


def seed_tax_filings():
    existing = count('tax_filings')
    to_create = max(0, TARGET - existing)
    if to_create <= 0:
        print('tax_filings OK:', existing)
        return

    conn = get_db()
    landlords = conn.execute("SELECT id FROM users WHERE role='landlord'").fetchall()
    landlord_ids = [l['id'] for l in landlords]
    if not landlord_ids:
        conn.close()
        print('no landlords for tax filings')
        return

    year = datetime.now().year
    for i in range(to_create):
        landlord_id = random.choice(landlord_ids)
        month = random.randint(1, 12)
        gross_rent = random.choice([30000, 35000, 40000])
        tax_amount = round(gross_rent * 0.1, 2)
        try:
            conn.execute('INSERT INTO tax_filings (landlord_id, period_month, period_year, gross_rent, tax_amount, status) VALUES (?, ?, ?, ?, ?, ?)',
                         (landlord_id, month, year, gross_rent, tax_amount, 'filed'))
            conn.commit()
        except Exception:
            continue

    conn.close()
    print('tax_filings seeded ->', count('tax_filings'))


def seed_withdrawals():
    """Seed withdrawals so landlord balances reflect payouts in the demo DB."""
    existing = count('withdrawals')
    to_create = max(0, TARGET - existing)
    if to_create <= 0:
        print('withdrawals OK:', existing)
        return

    conn = get_db()
    landlords = conn.execute("SELECT id FROM users WHERE role='landlord'").fetchall()
    landlord_ids = [l['id'] for l in landlords]
    if not landlord_ids:
        conn.close()
        print('no landlords for withdrawals')
        return

    for i in range(to_create):
        lid = random.choice(landlord_ids)
        gross = random.choice([20000, 30000, 35000, 40000])
        tax = round(gross * 0.1, 2)
        net = round(gross - tax, 2)
        status = random.choice(['confirmed', 'pending'])
        try:
            conn.execute('INSERT INTO withdrawals (landlord_id, gross_amount, tax_amount, net_amount, status) VALUES (?, ?, ?, ?, ?)',
                         (lid, gross, tax, net, status))
            conn.commit()
        except Exception:
            continue

    conn.close()
    print('withdrawals seeded ->', count('withdrawals'))


def seed_mpesa_requests():
    """Seed outgoing mpesa_requests to exercise reconciliation paths in dev."""
    existing = count('mpesa_requests')
    to_create = max(0, TARGET - existing)
    if to_create <= 0:
        print('mpesa_requests OK:', existing)
        return

    conn = get_db()
    tenancies = conn.execute('SELECT * FROM tenancies').fetchall()
    tenants = conn.execute("SELECT id FROM users WHERE role='tenant'").fetchall()
    landlords = conn.execute("SELECT id FROM users WHERE role='landlord'").fetchall()

    for i in range(to_create):
        t = random.choice(tenancies) if tenancies else None
        tenant_id = t['tenant_id'] if t else (random.choice(tenants)['id'] if tenants else None)
        landlord_id = t['landlord_id'] if t else (random.choice(landlords)['id'] if landlords else None)
        tenancy_id = t['id'] if t else None
        phone = f"2547{random.randint(10000000,99999999)}"
        amount = t['monthly_rent'] if t and t.get('monthly_rent') else random.choice([1500, 20000, 35000])
        account_ref = f"demo-{random.randint(1000,9999)}"
        mrid = f"MR{random.randint(100000,999999)}-{i}"
        co = f"CR{random.randint(100000,999999)}-{i}"
        status = random.choice(['initiated', 'processing', 'completed'])
        resp = '{}'
        try:
            conn.execute('INSERT INTO mpesa_requests (tenant_id, landlord_id, tenancy_id, phone, amount, account_reference, merchant_request_id, checkout_request_id, status, response_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                         (tenant_id, landlord_id, tenancy_id, phone, amount, account_ref, mrid, co, status, resp))
            conn.commit()
        except Exception:
            continue

    conn.close()
    print('mpesa_requests seeded ->', count('mpesa_requests'))


def seed_mpesa_callbacks():
    """Seed incoming mpesa_callbacks to simulate Daraja webhook receipts."""
    existing = count('mpesa_callbacks')
    to_create = max(0, TARGET - existing)
    if to_create <= 0:
        print('mpesa_callbacks OK:', existing)
        return

    conn = get_db()
    # sample from existing requests to form callbacks
    reqs = conn.execute('SELECT merchant_request_id, checkout_request_id FROM mpesa_requests LIMIT ?',(TARGET,)).fetchall()
    for i in range(to_create):
        if reqs:
            r = random.choice(reqs)
            mr = r['merchant_request_id']
            co = r['checkout_request_id']
        else:
            mr = f"MR{random.randint(100000,999999)}-cb{i}"
            co = f"CR{random.randint(100000,999999)}-cb{i}"
        rc = random.choice([0, 1, 10302])
        desc = 'The service request was processed successfully' if rc == 0 else 'Failed'
        cb = '{"DemoCallback": true}'
        try:
            conn.execute('INSERT INTO mpesa_callbacks (merchant_request_id, checkout_request_id, result_code, result_desc, callback_json) VALUES (?, ?, ?, ?, ?)',
                         (mr, co, rc, desc, cb))
            conn.commit()
        except Exception:
            continue

    conn.close()
    print('mpesa_callbacks seeded ->', count('mpesa_callbacks'))


def run_all():
    seed_users()
    seed_properties()
    seed_tenancies()
    seed_payments()
    seed_activities()
    seed_tax_filings()
    # New seeds for MPesa and withdrawals so dashboard and reconciliation paths
    # have realistic demo data in development environments.
    try:
        seed_withdrawals()
    except Exception:
        pass
    try:
        seed_mpesa_requests()
    except Exception:
        pass
    try:
        seed_mpesa_callbacks()
    except Exception:
        pass


if __name__ == '__main__':
    print('Starting DB seeder...')
    run_all()
    print('Done.')
