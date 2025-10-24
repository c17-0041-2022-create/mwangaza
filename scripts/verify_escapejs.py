import os, sys
sys.path.insert(0, os.getcwd())
from app import create_app
app = create_app()
with app.test_request_context():
    f = app.jinja_env.filters.get('escapejs')
    print('escapejs registered:', bool(f))
    if f:
        print('sample escaped:', f("O'Reilly\n</script>"))
