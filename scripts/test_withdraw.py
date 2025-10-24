"""Small smoke test: render the /withdraw page using Flask test client.

This script starts the app in testing mode, sets a demo landlord id into session
and performs a GET on /withdraw, printing status and a short HTML snippet.
"""
import sys
import os
# Ensure project root is on sys.path so local packages (app, models) import correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import create_app
from models import get_db


def main():
    app = create_app()
    app.testing = True
    client = app.test_client()

    # find a landlord id seeded by ensure_demo_data
    conn = get_db()
    row = conn.execute("SELECT id FROM users WHERE role = 'landlord' LIMIT 1").fetchone()
    conn.close()
    landlord_id = row['id'] if row else 1

    with client.session_transaction() as sess:
        sess['user_id'] = landlord_id

    resp = client.get('/withdraw')
    print('STATUS:', resp.status_code)
    text = resp.get_data(as_text=True)
    print('HTML snippet:')
    print(text[:1200])


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('ERROR during test:', e)
        sys.exit(2)