import os, sys
sys.path.insert(0, os.getcwd())
from app import create_app

app = create_app()

with app.test_client() as c:
    # GET the landlord receipts page (AUTH_DISABLED True will create a demo landlord session)
    resp = c.get('/landlord_receipts')
    print('status:', resp.status_code)
    text = resp.get_data(as_text=True)
    # quick check
    if 'No receipts found yet.' in text:
        print('NO RECEIPTS FOUND')
    else:
        # print a short excerpt around Recent Receipts
        i = text.find('Recent Receipts')
        print(text[i:i+400])
