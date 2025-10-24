"""Smoke test: GET /landlord using Flask test client and print KPIs."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import create_app
from models import get_db

def main():
    app = create_app()
    app.testing = True
    client = app.test_client()

    conn = get_db()
    row = conn.execute("SELECT id FROM users WHERE role = 'landlord' LIMIT 1").fetchone()
    conn.close()
    landlord_id = row['id'] if row else 1

    with client.session_transaction() as sess:
        sess['user_id'] = landlord_id

    resp = client.get('/landlord')
    print('STATUS:', resp.status_code)
    text = resp.get_data(as_text=True)
    # print a small snippet showing KPI numbers
    start = text.find('Total Rent Collected')
    print(text[start:start+400])

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('ERROR:', e)
        sys.exit(2)
