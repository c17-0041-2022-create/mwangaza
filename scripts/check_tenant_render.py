import importlib, re
importlib.invalidate_caches()
from app import create_app
app = create_app()
print('App created, making test client request to /tenant')
with app.test_client() as c:
    rv = c.get('/tenant')
    print('Status code:', rv.status_code)
    data = rv.get_data(as_text=True)
    # find KES value near Current Rent Due
    if 'Current Rent Due' in data:
        start = data.find('Current Rent Due')
        snippet = data[start:start+400]
        print('snippet:\n', snippet)
    else:
        print('Current Rent Due not present in response')
