"""Errores del servidor."""

from __future__ import annotations


class ToolInputError(ValueError):
    """Los argumentos que recibio una herramienta no sirven.

    El mensaje esta escrito para el modelo: dice que estuvo mal y como se ve una
    entrada valida, para que pueda corregir la llamada y reintentar.
    """
