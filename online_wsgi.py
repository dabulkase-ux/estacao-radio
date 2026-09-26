"""Entrada de produção: gunicorn --workers 1 --threads 40 online_wsgi:app."""
from backend_online import criar_backend

app, socketio = criar_backend()
