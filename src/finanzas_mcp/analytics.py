"""Calculos financieros.

Se recibe diccionarios y listas de numeros y devuelve numeros.
No se toca SQL ni MCP, asi que se puede probar por separado.

"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

# Peso de la correccion estacional. Con 1.0 se confiaria por completo en una sola
# observacion previa del mes; 0.5 la aprovecha sin sobreajustar.
SEASONAL_DAMPING = 0.5

# Meses de historial que usan por defecto la tendencia y las proyecciones.
DEFAULT_WINDOW = 6


def month_add(month: str, delta: int) -> str:
    """Suma (o resta) meses a una clave 'YYYY-MM'."""
    year, mon = int(month[:4]), int(month[5:7])
    total = year * 12 + (mon - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def month_number(month: str) -> int:
    """Devuelve el numero de mes (1 a 12) de una clave 'YYYY-MM'."""
    return int(month[5:7])


def previous_months(month: str, count: int) -> list[str]:
    """Devuelve los ultimos 'count' meses terminando en 'month', del mas viejo al mas nuevo."""
    return [month_add(month, -offset) for offset in range(count - 1, -1, -1)]


def is_valid_month(month: str) -> bool:
    """Indica si el texto tiene el formato 'YYYY-MM' con un mes real."""
    if len(month) != 7 or month[4] != "-":
        return False
    if not (month[:4].isdigit() and month[5:].isdigit()):
        return False
    return 1 <= int(month[5:]) <= 12


def pct_change(current: float, previous: float) -> float | None:
    """Variacion porcentual entre dos valores; None si la base es cero."""
    if previous == 0:
        return None
    return (current - previous) / previous * 100.0


@dataclass(frozen=True)
class Trend:
    """Resultado de ajustar una recta a una serie mensual.

    slope es el cambio en quetzales por mes, r2 va de 0 a 1 (valores bajos
    significan que la serie es muy irregular para confiar en la pendiente) y
    direction es 'creciente', 'estable' o 'decreciente'.
    """

    slope: float
    intercept: float
    r2: float
    mean: float
    direction: str

    @property
    def monthly_pct(self) -> float | None:
        """La pendiente expresada como porcentaje del promedio de la ventana."""
        if self.mean == 0:
            return None
        return self.slope / self.mean * 100.0


def linear_trend(values: list[float], flat_threshold_pct: float = 1.0) -> Trend:
    """Ajusta y = slope * x + intercept por minimos cuadrados.

    Una pendiente menor a flat_threshold_pct del promedio se reporta como
    'estable' en vez de como crecimiento o caida.
    """
    n = len(values)
    if n < 2:
        raise ValueError("se necesitan al menos dos puntos para ajustar una tendencia")

    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n

    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    slope = sxy / sxx if sxx else 0.0
    intercept = mean_y - slope * mean_x

    ss_tot = sum((y - mean_y) ** 2 for y in values)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, values))
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 1.0

    relative = abs(slope) / mean_y * 100 if mean_y else 0.0
    if relative < flat_threshold_pct:
        direction = "estable"
    else:
        direction = "creciente" if slope > 0 else "decreciente"

    return Trend(
        slope=slope,
        intercept=intercept,
        r2=max(0.0, min(1.0, r2)),
        mean=mean_y,
        direction=direction,
    )


def z_scores(values: list[float]) -> list[float]:
    """Puntajes estandar de una serie; todos cero si no hay dispersion."""
    if len(values) < 2:
        return [0.0] * len(values)
    mean = statistics.fmean(values)
    stdev = statistics.pstdev(values)
    if stdev == 0:
        return [0.0] * len(values)
    return [(value - mean) / stdev for value in values]
