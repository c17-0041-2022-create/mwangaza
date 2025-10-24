import importlib, re, traceback, os
importlib.invalidate_caches()
from app import create_app
app = create_app()
print('App created, making test client request to /tenant')
with app.test_client() as c:
    rv = c.get('/tenant')
    print('Status code:', rv.status_code)
    data = rv.get_data(as_text=True)
    start = data.find('Current Rent Due')
    if start!=-1:
        snippet = data[start:start+400]
        print('snippet:\n', snippet)
    else:
        print('Current Rent Due not present')

    # Print a short extract around Recent Activity
    ra = data.find('Recent Activity')
    if ra!=-1:
        print('\nRecent Activity snippet:\n', data[ra:ra+400])
    else:
        print('Recent Activity not present')
