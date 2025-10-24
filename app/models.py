"""Compatibility shim: re-export top-level models as `app.models`.

Some parts of the code import `app.models` (the package-style layout). The
project's actual database helpers live in the top-level `models.py`. To avoid
duplicating logic and to make both import styles work, this module simply
re-exports the public symbols from the top-level module.

This is a small, low-risk shim intended for local/dev use while the codebase
is migrated to a single package layout.
"""
try:
    # Prefer absolute import from project root
    from models import *  # noqa: F401,F403
except Exception:
    # As a fallback, try a relative import (rarely needed)
    try:
        from . import models as _m
        globals().update({k: getattr(_m, k) for k in dir(_m) if not k.startswith('_')})
    except Exception:
        raise

__all__ = [n for n in globals().keys() if not n.startswith('_')]
