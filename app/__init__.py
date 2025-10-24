from flask import Flask
from datetime import timedelta
import os

from app.filters import register_filters
from app.context import register_context
from app.errors import register_errors
from models import ensure_demo_data

from blueprints.payments import bp as payments_bp
from blueprints.kra_tax import bp as kra_bp
from blueprints.auth import bp as auth_bp


def create_app():
    # The project's `static/` directory lives at the repository root, not inside
    # the `app/` package. Configure Flask to serve that folder so templates
    # using `url_for('static', filename=...)` resolve correctly.
    root_static = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static'))
    app = Flask(__name__, static_folder=root_static, static_url_path='/static')
    app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.permanent_session_lifetime = timedelta(days=7)

    # Register filters, context, and error handlers
    register_filters(app)
    register_context(app)
    register_errors(app)

    # Ensure minimal demo data exists on startup (safe no-op if DB already seeded)
    try:
        ensure_demo_data()
    except Exception:
        pass

    # Also run the fuller seeder to ensure demo tables (payments, activities, tax filings)
    # are topped up for development/demo environments. The seeder is idempotent.
    try:
        from seed import run_all as _run_seed
        _run_seed()
    except Exception:
        # best-effort; ignore failures during startup seeding
        pass

    # Register blueprints
    app.register_blueprint(payments_bp)
    app.register_blueprint(kra_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # Register route groups
    from app.routes import general, tenant, landlord, tax
    app.register_blueprint(general.bp)
    app.register_blueprint(tenant.bp)
    app.register_blueprint(landlord.bp)
    app.register_blueprint(tax.bp)

    # Create short-name endpoint aliases for templates that expect them
    # (e.g. url_for('receipts') -> tenant.tenantreceipt). This avoids changing
    # many templates while keeping clear blueprint-prefixed endpoints.
    try:
        aliases = {
            'receipts': 'tenant.tenantreceipt',
            'landlord_receipts': 'landlord.landlord_receipts',
            'settings': 'auth.profile',
            'tenants': 'landlord.alltenants',
            'payments': 'landlord.landlord_payments',
            'tenant': 'tenant.tenant'
        }
        for short, full in aliases.items():
            vf = app.view_functions.get(full)
            if vf and short not in app.view_functions:
                # reuse the same rule/path by adding an alias rule that points
                # to the existing view function. Use the existing rule's rule
                # if possible; otherwise map to the same path by calling url_for
                # at runtime (Flask requires a unique rule, so map to the same
                # endpoint path if available).
                try:
                    # Attempt to add a simple alias rule using the same URL path
                    # by inspecting the existing URL map entry for the full endpoint.
                    rule = None
                    for r in app.url_map.iter_rules():
                        if r.endpoint == full:
                            rule = r.rule
                            break
                    if rule:
                        app.add_url_rule(rule, endpoint=short, view_func=vf)
                    else:
                        # Fallback: add a simple path under /alias/<short>
                        app.add_url_rule(f'/{short}', endpoint=short, view_func=vf)
                except Exception:
                    # ignore alias creation errors
                    pass
    except Exception:
        pass

    # Compatibility: wrap Jinja's url_for so templates using short endpoint names
    # (e.g. url_for('tenant')) still work when endpoints are registered under
    # blueprint-prefixed names (e.g. 'tenant.tenant'). This is a non-invasive
    # fallback to avoid editing many templates.
    try:
        from werkzeug.routing import BuildError
        # Prefer the Flask helper directly to avoid indirect wrappers
        from flask import url_for as original_url_for

        def url_for_compat(endpoint, **values):
            # Try the original first
            try:
                return original_url_for(endpoint, **values)
            except Exception as original_err:
                # Quick alias map for common short names used in templates
                aliases = {
                    'receipts': 'tenant.tenantreceipt',
                        'landlord_receipts': 'landlord.landlord_receipts',
                    'settings': 'auth.profile',
                    'tenants': 'landlord.alltenants',
                    'payments': 'landlord.landlord_payments',
                    'tenant': 'tenant.tenant'
                }
                if endpoint in aliases:
                    try:
                        return original_url_for(aliases[endpoint], **values)
                    except Exception:
                        pass
                # Collect candidate endpoints from registered view functions.
                eps = list(app.view_functions.keys())

                def last_segment(ep):
                    return ep.split('.')[-1]

                # helper to attempt building with a candidate and return on success
                def try_build(candidate):
                    try:
                        return original_url_for(candidate, **values)
                    except BuildError:
                        return None

                # 1) exact match (unlikely but safe)
                if endpoint in eps:
                    res = try_build(endpoint)
                    if res:
                        return res

                # 2) match last segment equals endpoint
                for ep in eps:
                    if last_segment(ep) == endpoint:
                        res = try_build(ep)
                        if res:
                            return res

                # 3) match if endpoint is substring of last segment (e.g. 'receipts' -> 'tenantreceipt')
                for ep in eps:
                    if endpoint in last_segment(ep):
                        res = try_build(ep)
                        if res:
                            return res

                # 4) try singular form (naive: drop trailing 's')
                if endpoint.endswith('s'):
                    singular = endpoint[:-1]
                    for ep in eps:
                        if last_segment(ep) == singular or singular in last_segment(ep):
                            res = try_build(ep)
                            if res:
                                return res

                # 5) fallback: any endpoint that endswith '.<endpoint>'
                for ep in eps:
                    if ep.endswith('.' + endpoint):
                        res = try_build(ep)
                        if res:
                            return res

                # Nothing matched — re-raise the original error so Flask shows the useful message
                raise original_err

        app.jinja_env.globals['url_for'] = url_for_compat
    except Exception:
        # Best-effort: if anything fails, leave default url_for in place
        pass

    return app
