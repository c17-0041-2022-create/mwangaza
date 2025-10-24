import importlib
importlib.invalidate_caches()
from app import create_app
app=create_app()
print('Registered endpoints (sample):')
for e in sorted(list(app.view_functions.keys())):
    if e.startswith('landlord') or e.startswith('tenant'):
        print(' -', e)
with app.test_request_context():
    print('url_for("landlord") ->', app.jinja_env.globals['url_for']('landlord'))
    print('url_for("alltenants") ->', app.jinja_env.globals['url_for']('alltenants'))
