"""Smoke test: GET / (index) using Flask test client."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import create_app

def main():
    app = create_app()
    app.testing = True
    client = app.test_client()
    resp = client.get('/')
    print('STATUS:', resp.status_code)
    print(resp.get_data(as_text=True)[:800])

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('ERROR:', e)
        sys.exit(2)
