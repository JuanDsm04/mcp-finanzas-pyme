"""Implementacion de las herramientas, un modulo por tipo de pregunta.

Cada funcion publica devuelve un reporte de texto y lanza ToolInputError si los
argumentos no sirven. server.py solo las registra, asi que todo el analisis se
puede usar sin una conexion MCP de por medio.
"""

from .gastos_por_categoria import desglose_gastos, detectar_gastos_atipicos
from .proyeccion_flujo import proyeccion_flujo_caja, salud_financiera
from .tendencia_ingresos import estado_resultados, tendencia_ingresos

__all__ = [
    "desglose_gastos",
    "detectar_gastos_atipicos",
    "tendencia_ingresos",
    "estado_resultados",
    "proyeccion_flujo_caja",
    "salud_financiera",
]
