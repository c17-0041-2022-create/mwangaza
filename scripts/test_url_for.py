import os
import sys

# Ensure project root is on sys.path so `import app` works when running from scripts/
HERE = os.path.dirname(os.path.dirname(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from app import create_app
from flask import url_for

app = create_app()

with app.test_request_context():
    print('\nRegistered endpoints:')
    for k in sorted(app.view_functions.keys()):
        print(' -', k)
    print()
    try:
        print('receipts ->', url_for('receipts'))
    except Exception as e:
        print('receipts failed:', type(e).__name__, e)

    try:
        print('settings ->', url_for('settings'))
    except Exception as e:
        print('settings failed:', type(e).__name__, e)

    try:
        print('tenant ->', url_for('tenant'))
    except Exception as e:
        print('tenant failed:', type(e).__name__, e)

    # Direct flask.url_for calls (bypass Jinja global wrapper) for comparison
    from flask import url_for as flask_url_for
    try:
        print('\nflask.url_for("tenant.tenantreceipt") ->', flask_url_for('tenant.tenantreceipt'))
    except Exception as e:
        print('flask tenant.tenantreceipt failed:', type(e).__name__, e)

    try:
        print('flask.url_for("tenant.tenantsettings") ->', flask_url_for('tenant.tenantsettings'))
    except Exception as e:
        print('flask tenant.tenantsettings failed:', type(e).__name__, e)
