from flask import session

def register_context(app):
    @app.context_processor
    def inject_user():
        return dict(
            logged_in=('user_id' in session),
            username=session.get('username'),
            role=session.get('role')
        )
