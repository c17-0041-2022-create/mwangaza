import os, sys
HERE = os.path.dirname(os.path.dirname(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from models import get_db

conn = get_db()
rows = conn.execute('SELECT landlord_id, COUNT(1) as c FROM payments GROUP BY landlord_id').fetchall()
for r in rows:
    print('landlord', r['landlord_id'], 'payments', r['c'])
conn.close()
