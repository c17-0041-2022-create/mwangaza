import importlib
import traceback

importlib.invalidate_caches()
from app import create_app
app = create_app()
print('Sample endpoints:', sorted(list(app.view_functions.keys()))[:40])
ctx = app.test_request_context()
ctx.push()
try:
    print('url_for("tenant") ->', app.jinja_env.globals['url_for']('tenant'))
except Exception:
    traceback.print_exc()
finally:
    ctx.pop()
