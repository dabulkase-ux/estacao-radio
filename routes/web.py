"""Rotas HTTP da aplicação MicroSerial."""

from __future__ import annotations

from flask import jsonify, render_template

from estado import obter_estado


def registrar_rotas(app) -> None:
    """Registra todas as rotas HTTP da aplicação."""

    @app.route("/")
    def index():
        return render_template(
            "index.html"
        )

    @app.route("/api/data")
    def api_data():
        return jsonify(
            obter_estado()
        )