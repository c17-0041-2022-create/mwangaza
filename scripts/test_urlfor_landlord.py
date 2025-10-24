import importlib, traceback
importlib.invalidate_caches()
from app import create_app
app = create_app()
ctx = app.test_request_context()
ctx.push()
try:
    print('Trying url_for("landlord") ->', app.jinja_env.globals['url_for']('landlord'))
    print('Trying url_for("landlord_payments") ->', app.jinja_env.globals['url_for']('landlord_payments'))
except Exception:
    traceback.print_exc()
finally:
    ctx.pop()
