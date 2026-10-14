"""
Alias de entrada para compatibilidad. Reutiliza la app principal.

Para producción y desarrollo se recomienda usar src/http/app.py.
"""

from src.http.app import create_app

app = create_app()