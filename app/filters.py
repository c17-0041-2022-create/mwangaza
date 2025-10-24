from datetime import datetime as _dt
import json

def format_currency(value):
    try:
        if value is None:
            return '—'
        v = float(value)
        if v.is_integer():
            return f"{int(v):,}"
        return f"{v:,.2f}"
    except Exception:
        return value or '—'


def format_date_short(value):
    if not value:
        return '—'
    try:
        if isinstance(value, (int, float)):
            dt = _dt.fromtimestamp(value)
        else:
            s = str(value)
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S.%f'):
                try:
                    dt = _dt.strptime(s, fmt)
                    break
                except Exception:
                    dt = None
            if dt is None:
                return s
        return dt.strftime('%b %d, %Y')
    except Exception:
        return str(value)


def register_filters(app):
    app.add_template_filter(format_currency, 'currency')
    app.add_template_filter(format_date_short, 'date_short')
    # Escape strings for safe insertion into single-quoted JS contexts
    def escapejs(value):
        if value is None:
            return ''
        s = str(value)
        # Escape backslashes first
        s = s.replace('\\', '\\\\')
        # Escape single quotes, newlines and carriage returns
        s = s.replace("'", "\\'")
        s = s.replace('\n', '\\n').replace('\r', '\\r')
        # Avoid closing </script> sequences
        s = s.replace('</', '<\\/')
        return s

    app.add_template_filter(escapejs, 'escapejs')
