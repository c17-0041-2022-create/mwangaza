import sqlite3

conn = sqlite3.connect('mwangaza.db')
conn.row_factory = sqlite3.Row
print('--- users ---')
for r in conn.execute('SELECT id,username,email,role,full_name FROM users ORDER BY id').fetchall():
    print(dict(r))

print('\n--- tenancies (join properties) ---')
for r in conn.execute('SELECT t.id as tenancy_id, t.tenant_id, t.property_id, t.monthly_rent, p.property_name, p.monthly_rent as property_rent FROM tenancies t LEFT JOIN properties p ON t.property_id = p.id ORDER BY t.id').fetchall():
    print(dict(r))

print('\n--- payments (latest 5) ---')
for r in conn.execute('SELECT * FROM payments ORDER BY created_at DESC LIMIT 5').fetchall():
    print(dict(r))

print('\n--- counts ---')
for tbl in ['users','properties','tenancies','payments','activities','tax_filings']:
    c = conn.execute(f"SELECT COUNT(1) as c FROM {tbl}").fetchone()['c']
    print(f"{tbl}: {c}")

conn.close()
