"""Funciones para dar formato al texto que devuelven las herramientas.

La salida la leen dos publicos a la vez: el modelo, que necesita numeros claros,
y la persona que ve la terminal.
"""

from __future__ import annotations

CURRENCY = "Q"


def money(amount: float) -> str:
    """Formatea un monto en quetzales con separador de miles."""
    return f"{CURRENCY}{amount:,.2f}"


def percent(value: float | None, signed: bool = False, decimals: int = 1) -> str:
    """Formatea un porcentaje, o 'n/d' si no esta definido."""
    if value is None:
        return "n/d"
    if signed:
        return f"{value:+.{decimals}f}%"
    return f"{value:.{decimals}f}%"


def bar(fraction: float, width: int = 20) -> str:
    """Dibuja una proporcion (de 0 a 1) como una barra de ancho fijo."""
    clamped = max(0.0, min(1.0, fraction))
    filled = round(clamped * width)
    return "#" * filled + "." * (width - filled)


def table(headers: list[str], rows: list[list[str]], align_right: set[int] | None = None) -> str:
    """Arma una tabla de texto con columnas alineadas.

    En align_right van los indices de las columnas numericas.
    """
    align_right = align_right or set()
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def render_row(cells: list[str]) -> str:
        parts = []
        for index, cell in enumerate(cells):
            parts.append(
                cell.rjust(widths[index]) if index in align_right else cell.ljust(widths[index])
            )
        return "  ".join(parts).rstrip()

    separator = "  ".join("-" * width for width in widths)
    return "\n".join([render_row(headers), separator, *(render_row(row) for row in rows)])


def heading(text: str) -> str:
    """Devuelve un titulo subrayado con '='."""
    return f"{text}\n{'=' * len(text)}"


def bullet_list(items: list[str]) -> str:
    """Devuelve una lista con vinetas."""
    return "\n".join(f"- {item}" for item in items)


def trend_arrow(value: float | None) -> str:
    """Devuelve una flecha de texto segun el signo de un cambio."""
    if value is None:
        return "->"
    if value > 0.5:
        return "^"
    if value < -0.5:
        return "v"
    return "->"
