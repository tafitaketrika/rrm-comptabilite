#!/usr/bin/env python3
"""
Point d'entrée de l'application RRM Antsirabe - Gestion Comptable & Financière
Compatible local + Render (Gunicorn)
"""
import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    print("=" * 60)
    print("  RRM Antsirabe - Application de Gestion Comptable")
    print("=" * 60)
    print(f"  Accès : http://127.0.0.1:{port}")
    print("  Admin : admin / AdminRRM2026!")
    print("=" * 60)
    app.run(debug=debug, host='0.0.0.0', port=port)
