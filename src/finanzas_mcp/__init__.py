"""Servidor MCP que responde preguntas financieras de una PYME.

La organizacion separa el analisis del protocolo: db.py accede a SQLite,
analytics.py hace los calculos, tools/ arma los reportes y server.py solo los
registra como herramientas MCP.
"""

__version__ = "0.1.0"
