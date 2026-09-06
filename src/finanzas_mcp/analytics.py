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


def seasonal_index(
    series: dict[str, float], target_month: str, damping: float = SEASONAL_DAMPING
) -> float:
    """Cuanto se desvia un mes del calendario respecto al promedio general.

    Un 1.18 significa "este mes suele facturar 18% arriba de un mes promedio". Si
    el mes nunca se ha observado devuelve 1.0, para que quien llama se quede con
    la tendencia sin corregir. La proporcion se amortigua porque el historial es
    corto.
    """
    if not series:
        return 1.0

    overall_mean = statistics.fmean(series.values())
    if overall_mean == 0:
        return 1.0

    target = month_number(target_month)
    same_month = [value for key, value in series.items() if month_number(key) == target]
    if not same_month:
        return 1.0

    raw_ratio = statistics.fmean(same_month) / overall_mean
    return 1.0 + (raw_ratio - 1.0) * damping


@dataclass(frozen=True)
class Projection:
    """Un mes proyectado: el valor final, la base antes de la correccion y el factor usado."""

    month: str
    value: float
    base: float
    seasonal_factor: float


def project(
    series: dict[str, float],
    months_ahead: int = 1,
    window: int = DEFAULT_WINDOW,
) -> list[Projection]:
    """Proyecta una serie mensual con tendencia mas estacionalidad amortiguada."""
    if len(series) < 2:
        raise ValueError("se necesitan al menos dos meses de historial para proyectar")

    ordered = sorted(series.items())
    recent = ordered[-window:] if len(ordered) >= window else ordered
    values = [value for _month, value in recent]
    trend = linear_trend(values)

    last_month = ordered[-1][0]
    projections: list[Projection] = []

    for step in range(1, months_ahead + 1):
        target_month = month_add(last_month, step)
        # El indice x sigue avanzando mas alla del final de la ventana ajustada.
        x = len(values) - 1 + step
        base = trend.slope * x + trend.intercept
        factor = seasonal_index(series, target_month)
        projections.append(
            Projection(
                month=target_month,
                value=max(0.0, base * factor),
                base=base,
                seasonal_factor=factor,
            )
        )

    return projections


def zero_fill(series: dict[str, float], months: list[str]) -> dict[str, float]:
    """Completa la serie con ceros en los meses que faltan."""
    return {month: series.get(month, 0.0) for month in months}


def project_stable(
    series: dict[str, float],
    months_ahead: int = 1,
    window: int = DEFAULT_WINDOW,
    damping: float = 1.0,
) -> list[Projection]:
    """Proyecta un gasto recurrente como nivel por indice estacional."""
    if not series:
        raise ValueError("no se puede proyectar una serie vacia")

    ordered = sorted(series.items())
    recent = ordered[-window:] if len(ordered) >= window else ordered
    level = statistics.fmean(value for _month, value in recent)

    last_month = ordered[-1][0]
    projections: list[Projection] = []
    for step in range(1, months_ahead + 1):
        target_month = month_add(last_month, step)
        factor = seasonal_index(series, target_month, damping=damping)
        projections.append(
            Projection(
                month=target_month,
                value=max(0.0, level * factor),
                base=level,
                seasonal_factor=factor,
            )
        )
    return projections


def ratio_to_income(
    expense_series: dict[str, float],
    income_series: dict[str, float],
    window: int = DEFAULT_WINDOW,
) -> float:
    """Proporcion mediana de los ingresos que se lleva una serie de gastos.

    Los gastos variables se proyectan con esta proporcion y no con su propia
    tendencia, porque suben y bajan justamente porque las ventas suben y bajan.
    """
    months = sorted(set(expense_series) & set(income_series))[-window:]
    ratios = [
        expense_series[month] / income_series[month]
        for month in months
        if income_series.get(month)
    ]
    return statistics.median(ratios) if ratios else 0.0


def runway_months(cash: float, monthly_burn: float) -> float | None:
    """Cuantos meses de gastos fijos cubre un saldo; None si no hay gasto."""
    if monthly_burn <= 0:
        return None
    return cash / monthly_burn
