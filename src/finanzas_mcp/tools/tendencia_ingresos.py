"""Caso 2: "mis ventas van subiendo o bajando".

tendencia_ingresos responde con tres niveles de evidencia, porque un solo
porcentaje mes contra mes es facil de malinterpretar: la comparacion con el mes
anterior, la del mismo mes del año pasado (que cancela la estacionalidad) y una
tendencia ajustada por minimos cuadrados con su R2, para dejar claro que tan
confiable es la pendiente.
"""

from __future__ import annotations

from .. import db
from ..analytics import (
    is_valid_month,
    linear_trend,
    month_add,
    pct_change,
    previous_months,
)
from ..errors import ToolInputError
from ..formatting import bar, heading, money, percent, table, trend_arrow


def _resolve_month(mes: str | None) -> str:
    """Valida el mes recibido; si viene vacio usa el ultimo mes con datos."""
    months = db.available_months()
    if not months:
        raise ToolInputError("La base de datos no contiene transacciones.")
    if mes is None or not str(mes).strip():
        return months[-1]

    mes = str(mes).strip()
    if not is_valid_month(mes):
        raise ToolInputError(
            f"Mes invalido: '{mes}'. Usa el formato 'YYYY-MM', por ejemplo '2026-08'. "
            f"Meses disponibles: {months[0]} a {months[-1]}."
        )
    if mes not in months:
        raise ToolInputError(
            f"No hay transacciones registradas en {mes}. "
            f"El periodo disponible va de {months[0]} a {months[-1]}."
        )
    return mes


def tendencia_ingresos(mes: str | None = None, meses: int = 6) -> str:
    """Analiza la tendencia de ingresos en una ventana que termina en el mes dado."""
    if not 3 <= meses <= 24:
        raise ToolInputError(
            f"El parametro 'meses' debe estar entre 3 y 24 (recibido: {meses})."
        )

    mes = _resolve_month(mes)
    income = db.monthly_totals("ingreso")

    window = [month for month in previous_months(mes, meses) if month in income]
    if len(window) < 3:
        raise ToolInputError(
            f"Solo hay {len(window)} mes(es) de historial hasta {mes}; "
            "se necesitan al menos 3 para analizar la tendencia."
        )

    values = [income[month] for month in window]
    trend = linear_trend(values)
    current = income[mes]

    lines = [heading(f"Tendencia de ingresos - ventana de {len(window)} meses hasta {mes}")]

    previous = month_add(mes, -1)
    if previous in income:
        change = pct_change(current, income[previous])
        delta = current - income[previous]
        lines.append(
            f"Mes anterior ({previous}): {money(income[previous])}\n"
            f"Mes actual   ({mes}): {money(current)}\n"
            f"Variacion: {money(delta) if delta >= 0 else '-' + money(abs(delta))} "
            f"({percent(change, signed=True)}) {trend_arrow(change)}"
        )
    else:
        lines.append(f"Mes actual ({mes}): {money(current)} (sin mes previo para comparar)")

    year_ago = month_add(mes, -12)
    if year_ago in income:
        yoy = pct_change(current, income[year_ago])
        lines.append(
            f"\nComparacion interanual ({year_ago} -> {mes}): "
            f"{money(income[year_ago])} -> {money(current)} ({percent(yoy, signed=True)})\n"
            "  (esta comparacion elimina el efecto de la estacionalidad del mes)"
        )

    reliability = (
        "alta" if trend.r2 >= 0.7 else "media" if trend.r2 >= 0.4 else "baja"
    )
    lines.append("")
    lines.append(
        f"Tendencia ajustada (minimos cuadrados sobre {len(window)} meses): {trend.direction.upper()}\n"
        f"- Pendiente: {money(trend.slope)} por mes "
        f"({percent(trend.monthly_pct, signed=True)} del promedio mensual)\n"
        f"- Promedio de la ventana: {money(trend.mean)}\n"
        f"- R2: {trend.r2:.3f} (confiabilidad {reliability})"
    )
    if trend.r2 < 0.4:
        lines.append(
            "  Nota: un R2 bajo indica que los ingresos son muy irregulares; "
            "la pendiente es orientativa, no predictiva."
        )

    lines.append("")
    maximum = max(values)
    rows = []
    for index, month in enumerate(window):
        value = income[month]
        previous_value = income.get(month_add(month, -1))
        change = pct_change(value, previous_value) if previous_value else None
        rows.append(
            [
                month,
                money(value),
                percent(change, signed=True) if change is not None else "-",
                bar(value / maximum if maximum else 0, 24),
            ]
        )
    lines.append(
        table(["Mes", "Ingresos", "vs mes previo", "Nivel"], rows, align_right={1, 2})
    )

    return "\n".join(lines)


def estado_resultados(mes: str | None = None) -> str:
    """Arma el estado de resultados de un mes: ingresos, gastos, utilidad y margen."""
    mes = _resolve_month(mes)

    income_rows = db.category_breakdown(mes, "ingreso")
    expense_rows = db.category_breakdown(mes, "gasto")

    total_income = sum(row["total"] for row in income_rows)
    total_expense = sum(row["total"] for row in expense_rows)
    fixed = sum(row["total"] for row in expense_rows if row["es_fijo"])
    variable = total_expense - fixed
    profit = total_income - total_expense
    margin = (profit / total_income * 100) if total_income else None

    lines = [heading(f"Estado de resultados - {mes}")]

    lines.append("INGRESOS")
    lines.append(
        table(
            ["Categoria", "Monto", "% ingresos"],
            [
                [
                    row["categoria"],
                    money(row["total"]),
                    percent(row["total"] / total_income * 100) if total_income else "n/d",
                ]
                for row in income_rows
            ],
            align_right={1, 2},
        )
    )
    lines.append(f"Total ingresos: {money(total_income)}")

    lines.append("")
    lines.append("GASTOS")
    lines.append(
        table(
            ["Categoria", "Tipo", "Monto", "% ingresos"],
            [
                [
                    row["categoria"],
                    "fijo" if row["es_fijo"] else "variable",
                    money(row["total"]),
                    percent(row["total"] / total_income * 100) if total_income else "n/d",
                ]
                for row in expense_rows
            ],
            align_right={2, 3},
        )
    )
    lines.append(
        f"Gastos fijos: {money(fixed)}  |  Gastos variables: {money(variable)}  |  "
        f"Total: {money(total_expense)}"
    )

    lines.append("")
    resultado = "UTILIDAD" if profit >= 0 else "PERDIDA"
    lines.append(
        f"{resultado} NETA: {money(abs(profit))}   Margen neto: {percent(margin, signed=True)}"
    )

    previous = month_add(mes, -1)
    income_by_month = db.monthly_totals("ingreso")
    expense_by_month = db.monthly_totals("gasto")
    if previous in income_by_month:
        previous_profit = income_by_month[previous] - expense_by_month.get(previous, 0.0)
        lines.append(
            f"Mes anterior ({previous}): ingresos {money(income_by_month[previous])}, "
            f"gastos {money(expense_by_month.get(previous, 0.0))}, "
            f"resultado {money(previous_profit)}"
        )

    return "\n".join(lines)
