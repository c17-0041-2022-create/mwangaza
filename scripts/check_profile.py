import os, sys
sys.path.insert(0, os.getcwd())
from app import create_app
app = create_app()
with app.test_client() as c:
    resp = c.get('/auth/profile')
    print('status', resp.status_code)
    text = resp.get_data(as_text=True)
    print(text[:500])
