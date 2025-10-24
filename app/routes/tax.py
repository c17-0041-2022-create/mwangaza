from flask import Blueprint, render_template

bp = Blueprint('tax', __name__)


@bp.route('/tax_compliance', endpoint='taxcompliance')
def tax_compliance():
    """Render a simple tax compliance summary page.

    This exists so `url_for('taxcompliance')` used in templates resolves.
    """
    return render_template('tax_compliance.html')
from flask import Blueprint, render_template

bp = Blueprint('tax', __name__)


@bp.route('/tax_compliance')
def taxcompliance():
    """Simple tax compliance page for landlords/tenants.

    Renders the `tax_compliance.html` template if present. Kept minimal to
    satisfy imports and provide a usable page during development.
    """
    return render_template('tax_compliance.html')
