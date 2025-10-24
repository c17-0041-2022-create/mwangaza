import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash

DATABASE = 'mwangaza.db'


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database with users, properties, tenancies and auxiliary tables."""
    conn = get_db()

    # Users table: Landlords and Tenants
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('tenant', 'landlord')),
            full_name TEXT,
            phone TEXT,
            kra_pin TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    ''')

    # Properties table: owned by landlords
    conn.execute('''
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            landlord_id INTEGER NOT NULL,
            property_name TEXT NOT NULL,
            address TEXT,
            monthly_rent REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (landlord_id) REFERENCES users(id)
        )
    ''')

    # Tenancies table: connects tenants to properties
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tenancies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            property_id INTEGER NOT NULL,
            landlord_id INTEGER NOT NULL,
            monthly_rent REAL NOT NULL,
            start_date DATE,
            end_date DATE,
            status TEXT DEFAULT 'active' CHECK(status IN ('active', 'inactive')),
            FOREIGN KEY (tenant_id) REFERENCES users(id),
            FOREIGN KEY (property_id) REFERENCES properties(id),
            FOREIGN KEY (landlord_id) REFERENCES users(id)
        )
    ''')

    # Payments table: records payments made by tenants
    conn.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            landlord_id INTEGER NOT NULL,
            tenacy_id INTEGER,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'KES',
            description TEXT,
            status TEXT DEFAULT 'confirmed' CHECK(status IN ('pending','confirmed','failed')),
            merchant_request_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES users(id),
            FOREIGN KEY (landlord_id) REFERENCES users(id)
        )
    ''')

    # Activities table: tenant/landlord activities (maintenance, notices, etc.)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            activity_type TEXT NOT NULL,
            description TEXT,
            amount REAL,
            status TEXT DEFAULT 'info',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Tax filings table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tax_filings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            landlord_id INTEGER NOT NULL,
            period_month INTEGER,
            period_year INTEGER,
            gross_rent REAL,
            tax_amount REAL,
            status TEXT DEFAULT 'filed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (landlord_id) REFERENCES users(id)
        )
    ''')

    # Withdrawals table: record landlord withdrawals and taxes deducted
    conn.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            landlord_id INTEGER NOT NULL,
            gross_amount REAL NOT NULL,
            tax_amount REAL NOT NULL,
            net_amount REAL NOT NULL,
            status TEXT DEFAULT 'confirmed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (landlord_id) REFERENCES users(id)
        )
    ''')

    # M-Pesa STK Push requests (outgoing) - store the request metadata so we can reconcile callbacks
    conn.execute('''
        CREATE TABLE IF NOT EXISTS mpesa_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER,
            landlord_id INTEGER,
            tenancy_id INTEGER,
            phone TEXT,
            amount REAL,
            account_reference TEXT,
            merchant_request_id TEXT,
            checkout_request_id TEXT,
            status TEXT DEFAULT 'initiated',
            response_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # M-Pesa callback receipts (incoming) - store raw callback payloads and parsed results
    conn.execute('''
        CREATE TABLE IF NOT EXISTS mpesa_callbacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            merchant_request_id TEXT,
            checkout_request_id TEXT,
            result_code INTEGER,
            result_desc TEXT,
            callback_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

    # Ensure payments table has merchant_request_id column for idempotency
    try:
        conn = get_db()
        cols = [r['name'] for r in conn.execute("PRAGMA table_info(payments)").fetchall()]
        if 'merchant_request_id' not in cols:
            conn.execute('ALTER TABLE payments ADD COLUMN merchant_request_id TEXT')
        # create an index to speed lookups by merchant_request_id
        conn.execute('CREATE INDEX IF NOT EXISTS idx_payments_merchant_request_id ON payments(merchant_request_id)')
        conn.commit()
        conn.close()
    except Exception:
        # non-fatal; best effort
        try:
            conn.close()
        except Exception:
            pass


# ========== Helper CRUD Functions ==========

def add_user(username, email, password_hash, role, full_name='', phone='', kra_pin=''):
    """Add a new user (tenant or landlord)."""
    conn = get_db()
    conn.execute(
        '''INSERT INTO users (username, email, password_hash, role, full_name, phone, kra_pin)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (username, email, password_hash, role, full_name, phone, kra_pin)
    )
    conn.commit()
    conn.close()


def update_user(user_id, **fields):
    """Update user fields by id. Only allows a few fields for safety."""
    allowed = {'full_name', 'phone', 'kra_pin', 'email', 'username'}
    updates = []
    params = []
    for k, v in fields.items():
        if k in allowed:
            updates.append(f"{k} = ?")
            params.append(v)
    if not updates:
        return
    params.append(user_id)
    conn = get_db()
    conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", tuple(params))
    conn.commit()
    conn.close()


def get_user_by_email(email):
    """Retrieve a user by email."""
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()
    return user


def get_user_by_id(user_id):
    """Retrieve a user by ID."""
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return user


def add_property(landlord_id, property_name, address, monthly_rent):
    """Add a property for a landlord."""
    conn = get_db()
    conn.execute(
        '''INSERT INTO properties (landlord_id, property_name, address, monthly_rent)
           VALUES (?, ?, ?, ?)''',
        (landlord_id, property_name, address, monthly_rent)
    )
    conn.commit()
    conn.close()


def get_properties_by_landlord(landlord_id):
    """Retrieve all properties owned by a landlord."""
    conn = get_db()
    properties = conn.execute(
        'SELECT * FROM properties WHERE landlord_id = ?',
        (landlord_id,)
    ).fetchall()
    conn.close()
    return properties


def add_payment(tenant_id, landlord_id, amount, description='', status='confirmed', tenacy_id=None, currency='KES', merchant_request_id=None):
    conn = get_db()
    conn.execute(
        '''INSERT INTO payments (tenant_id, landlord_id, tenacy_id, amount, currency, description, status, merchant_request_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (tenant_id, landlord_id, tenacy_id, amount, currency, description, status, merchant_request_id)
    )
    conn.commit()
    conn.close()


def get_payments_by_tenant(tenant_id, limit=10):
    conn = get_db()
    payments = conn.execute(
        'SELECT * FROM payments WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?',
        (tenant_id, limit)
    ).fetchall()
    conn.close()
    return payments


def get_latest_payment_by_tenant(tenant_id):
    conn = get_db()
    payment = conn.execute(
        'SELECT * FROM payments WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 1',
        (tenant_id,)
    ).fetchone()
    conn.close()
    return payment


def get_mpesa_balance_by_tenant(tenant_id):
    """Compute a simple balance as the sum of confirmed payments for the tenant."""
    conn = get_db()
    row = conn.execute(
        "SELECT IFNULL(SUM(amount), 0) as balance FROM payments WHERE tenant_id = ? AND status = 'confirmed'",
        (tenant_id,)
    ).fetchone()
    conn.close()
    return row['balance'] if row else 0


def add_activity(user_id, activity_type, description='', amount=None, status='info'):
    conn = get_db()
    conn.execute(
        'INSERT INTO activities (user_id, activity_type, description, amount, status) VALUES (?, ?, ?, ?, ?)',
        (user_id, activity_type, description, amount, status)
    )
    conn.commit()
    conn.close()


def add_tax_filing(landlord_id, period_month, period_year, gross_rent, tax_amount, status='filed'):
    """Persist a tax filing record."""
    conn = get_db()
    conn.execute(
        'INSERT INTO tax_filings (landlord_id, period_month, period_year, gross_rent, tax_amount, status) VALUES (?, ?, ?, ?, ?, ?)',
        (landlord_id, period_month, period_year, gross_rent, tax_amount, status)
    )
    conn.commit()
    conn.close()


def add_withdrawal(landlord_id, gross_amount, tax_amount, net_amount, status='confirmed'):
    """Record a withdrawal so available balance is reduced."""
    conn = get_db()
    conn.execute(
        'INSERT INTO withdrawals (landlord_id, gross_amount, tax_amount, net_amount, status) VALUES (?, ?, ?, ?, ?)',
        (landlord_id, gross_amount, tax_amount, net_amount, status)
    )
    conn.commit()
    conn.close()


def get_recent_activities_by_user(user_id, limit=5):
    conn = get_db()
    items = conn.execute(
        'SELECT * FROM activities WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
        (user_id, limit)
    ).fetchall()
    conn.close()
    return items


def get_user_count():
    conn = get_db()
    row = conn.execute('SELECT COUNT(1) as c FROM users').fetchone()
    conn.close()
    return row['c'] if row else 0


def ensure_demo_data():
    """Seed minimal demo data if database is empty.

    Creates one landlord, one tenant, a property, a tenancy, a few payments and activities.
    This function is safe to call repeatedly; it only seeds when no users exist.
    """
    if get_user_count() > 0:
        return

    # Create landlord
    landlord_pw = generate_password_hash('landlordpass')
    add_user('landlord1', 'landlord@example.com', landlord_pw, 'landlord', 'Alice Landlord', '+254700111222', 'LND123456')
    # Create tenant
    tenant_pw = generate_password_hash('tenantpass')
    add_user('tenant1', 'tenant@example.com', tenant_pw, 'tenant', 'Grace Wanjiku', '+254700000001', 'TNT987654')

    # Retrieve ids
    conn = get_db()
    landlord = conn.execute('SELECT * FROM users WHERE email = ?', ('landlord@example.com',)).fetchone()
    tenant = conn.execute('SELECT * FROM users WHERE email = ?', ('tenant@example.com',)).fetchone()

    # Property
    conn.execute('INSERT INTO properties (landlord_id, property_name, address, monthly_rent) VALUES (?, ?, ?, ?)',
                 (landlord['id'], 'Sunset Apartments - Unit 3A', '123 Nairobi Rd, Nairobi', 35000.0))
    conn.commit()
    property_row = conn.execute('SELECT * FROM properties WHERE landlord_id = ? LIMIT 1', (landlord['id'],)).fetchone()

    # Tenancy
    conn.execute('INSERT INTO tenancies (tenant_id, property_id, landlord_id, monthly_rent, start_date) VALUES (?, ?, ?, ?, ?)',
                 (tenant['id'], property_row['id'], landlord['id'], 35000.0, datetime.now().date()))
    conn.commit()
    tenancy_row = conn.execute('SELECT * FROM tenancies WHERE tenant_id = ? LIMIT 1', (tenant['id'],)).fetchone()

    # Payments
    conn.execute('INSERT INTO payments (tenant_id, landlord_id, tenacy_id, amount, description, status) VALUES (?, ?, ?, ?, ?, ?)',
                 (tenant['id'], landlord['id'], tenancy_row['id'], 35000.0, 'Rent Payment - October', 'confirmed'))
    conn.execute('INSERT INTO payments (tenant_id, landlord_id, tenacy_id, amount, description, status) VALUES (?, ?, ?, ?, ?, ?)',
                 (tenant['id'], landlord['id'], tenancy_row['id'], 1500.0, 'Water Bill Payment', 'confirmed'))
    conn.commit()

    # Activities
    conn.execute('INSERT INTO activities (user_id, activity_type, description, amount, status) VALUES (?, ?, ?, ?, ?)',
                 (tenant['id'], 'maintenance', 'Maintenance Request Logged', None, 'pending'))
    conn.execute('INSERT INTO activities (user_id, activity_type, description, amount, status) VALUES (?, ?, ?, ?, ?)',
                 (tenant['id'], 'payment', 'Rent Payment - October', 35000.0, 'confirmed'))
    conn.commit()
    conn.close()


def add_tenancy(tenant_id, property_id, landlord_id, monthly_rent, start_date, end_date=None):
    """Create a tenancy relationship between tenant and landlord."""
    conn = get_db()
    conn.execute(
        '''INSERT INTO tenancies (tenant_id, property_id, landlord_id, monthly_rent, start_date, end_date)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (tenant_id, property_id, landlord_id, monthly_rent, start_date, end_date)
    )
    conn.commit()
    conn.close()


def add_mpesa_request(tenant_id, landlord_id, tenancy_id, phone, amount, account_reference, merchant_request_id, checkout_request_id, status='initiated', response_json=None):
    conn = get_db()
    conn.execute(
        '''INSERT INTO mpesa_requests (tenant_id, landlord_id, tenancy_id, phone, amount, account_reference, merchant_request_id, checkout_request_id, status, response_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (tenant_id, landlord_id, tenancy_id, phone, amount, account_reference, merchant_request_id, checkout_request_id, status, response_json)
    )
    conn.commit()
    conn.close()


def add_mpesa_callback(merchant_request_id, checkout_request_id, result_code, result_desc, callback_json):
    conn = get_db()
    conn.execute(
        '''INSERT INTO mpesa_callbacks (merchant_request_id, checkout_request_id, result_code, result_desc, callback_json)
           VALUES (?, ?, ?, ?, ?)''',
        (merchant_request_id, checkout_request_id, result_code, result_desc, callback_json)
    )
    conn.commit()
    conn.close()


def get_mpesa_request_by_merchant_request_id(merchant_request_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM mpesa_requests WHERE merchant_request_id = ? LIMIT 1', (merchant_request_id,)).fetchone()
    conn.close()
    return row


def update_mpesa_request_status(merchant_request_id, status, response_json=None, checkout_request_id=None):
    conn = get_db()
    if checkout_request_id:
        conn.execute('UPDATE mpesa_requests SET status = ?, response_json = ?, checkout_request_id = ? WHERE merchant_request_id = ?', (status, response_json, checkout_request_id, merchant_request_id))
    else:
        conn.execute('UPDATE mpesa_requests SET status = ?, response_json = ? WHERE merchant_request_id = ?', (status, response_json, merchant_request_id))
    conn.commit()
    conn.close()


def get_tenancies_by_landlord(landlord_id):
    """Get all tenancies for a given landlord."""
    conn = get_db()
    tenancies = conn.execute(
        '''SELECT t.*, u.username AS tenant_name, p.property_name
           FROM tenancies t
           JOIN users u ON t.tenant_id = u.id
           JOIN properties p ON t.property_id = p.id
           WHERE t.landlord_id = ?''',
        (landlord_id,)
    ).fetchall()
    conn.close()
    return tenancies


def get_payments_by_landlord(landlord_id, limit=50):
    """Retrieve payments made to a landlord, including tenant and property info."""
    conn = get_db()
    payments = conn.execute(
        '''SELECT p.*, u.full_name as tenant_name, pr.property_name
           FROM payments p
           LEFT JOIN users u ON p.tenant_id = u.id
           LEFT JOIN tenancies t ON p.tenacy_id = t.id
           LEFT JOIN properties pr ON t.property_id = pr.id
           WHERE p.landlord_id = ?
           ORDER BY p.created_at DESC LIMIT ?''',
        (landlord_id, limit)
    ).fetchall()
    conn.close()
    return payments


def get_tenancies_by_tenant(tenant_id):
    """Get all tenancies for a given tenant."""
    conn = get_db()
    tenancies = conn.execute(
        '''SELECT t.*, p.property_name, u.full_name AS landlord_name
           FROM tenancies t
           JOIN properties p ON t.property_id = p.id
           JOIN users u ON t.landlord_id = u.id
           WHERE t.tenant_id = ?''',
        (tenant_id,)
    ).fetchall()
    conn.close()
    return tenancies


def deactivate_tenancy(tenancy_id):
    """Deactivate a tenancy (e.g., lease ended)."""
    conn = get_db()
    conn.execute(
        'UPDATE tenancies SET status = "inactive" WHERE id = ?',
        (tenancy_id,)
    )
    conn.commit()
    conn.close()


# Initialize the database when models.py is imported
init_db()
