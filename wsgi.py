"""WSGI entrypoint for gunicorn.

Run: ``gunicorn -k gevent -b 127.0.0.1:9998 wsgi:app``
"""

from app import create_app

app = create_app()
