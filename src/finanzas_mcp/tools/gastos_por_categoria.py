"""Caso 1: "cuanto gaste el mes pasado y en que".

desglose_gastos responde la pregunta directa, con el reparto por categoria y una
comparacion contra el mes anterior y el promedio de los tres meses previos,
porque un total suelto no dice nada por si mismo.

detectar_gastos_atipicos busca gastos que se salen de la norma de su propia
categoria, que es como aparece una reparacion de equipo sin que nadie supiera de
antemano que la estaba buscando.
"""

from __future__ import annotations

import statistics

from .. import db
from ..analytics import (
    is_valid_month,
    month_add,
    previous_months,
    pct_change,
    z_scores,
)
from ..errors import ToolInputError
from ..formatting import bar, heading, money, percent, table


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


def desglose_gastos(mes: str | None = None, incluir_comparacion: bool = True) -> str:
    """Desglosa los gastos de un mes por categoria.

    Devuelve el total, el reparto por categoria (monto, porcentaje, movimientos,
    fijo o variable), los principales proveedores y los movimientos mas grandes.
    """
    mes = _resolve_month(mes)

    rows = db.category_breakdown(mes, "gasto")
    if not rows:
        return f"No se registraron gastos en {mes}."

    total = sum(row["total"] for row in rows)
    fixed_total = sum(row["total"] for row in rows if row["es_fijo"])

    lines = [heading(f"Desglose de gastos - {mes}")]
    lines.append(f"Total de gastos: {money(total)} en {sum(r['n_transacciones'] for r in rows)} movimientos")
    lines.append(
        f"Gastos fijos: {money(fixed_total)} ({percent(fixed_total / total * 100)})  |  "
        f"Gastos variables: {money(total - fixed_total)} "
        f"({percent((total - fixed_total) / total * 100)})"
    )
    lines.append("")

    breakdown_rows = []
    for row in rows:
        share = row["total"] / total
        breakdown_rows.append(
            [
                row["categoria"],
                "fijo" if row["es_fijo"] else "variable",
                money(row["total"]),
                percent(share * 100),
                str(row["n_transacciones"]),
                bar(share, 16),
            ]
        )
    lines.append(
        table(
            ["Categoria", "Tipo", "Monto", "% del total", "Movs", "Peso"],
            breakdown_rows,
            align_right={2, 3, 4},
        )
    )

    if incluir_comparacion:
        lines.append("")
        lines.append(_comparison_block(mes, total, rows))

    suppliers = db.top_suppliers(mes, limit=5)
    if suppliers:
        lines.append("")
        lines.append("Principales proveedores del mes:")
        lines.append(
            table(
                ["Proveedor", "Compras", "Total"],
                [[s["proveedor"], str(s["n_compras"]), money(s["total"])] for s in suppliers],
                align_right={1, 2},
            )
        )

    largest = db.largest_transactions(mes, "gasto", limit=5)
    if largest:
        lines.append("")
        lines.append("Movimientos individuales mas grandes:")
        lines.append(
            table(
                ["Fecha", "Categoria", "Monto", "Descripcion"],
                [
                    [t["fecha"], t["categoria"], money(t["monto"]), t["descripcion"] or ""]
                    for t in largest
                ],
                align_right={2},
            )
        )

    return "\n".join(lines)


def _comparison_block(mes: str, total: float, rows) -> str:
    """Compara el mes contra el anterior y contra el promedio de los tres previos."""
    expenses_by_month = db.monthly_totals("gasto")

    previous = month_add(mes, -1)
    lines = ["Comparacion:"]

    if previous in expenses_by_month:
        change = pct_change(total, expenses_by_month[previous])
        delta = total - expenses_by_month[previous]
        lines.append(
            f"- vs {previous}: {money(expenses_by_month[previous])} -> {money(total)} "
            f"({money(delta) if delta >= 0 else '-' + money(abs(delta))}, {percent(change, signed=True)})"
        )
    else:
        lines.append(f"- No hay datos del mes anterior ({previous}) para comparar.")

    window = [m for m in previous_months(mes, 4)[:-1] if m in expenses_by_month]
    if window:
        average = statistics.fmean(expenses_by_month[m] for m in window)
        lines.append(
            f"- vs promedio de los {len(window)} meses previos ({money(average)}): "
            f"{percent(pct_change(total, average), signed=True)}"
        )

    # Que categoria se movio mas respecto al mes anterior.
    if previous in expenses_by_month:
        current_by_cat = {row["categoria"]: row["total"] for row in rows}
        previous_by_cat = {
            row["categoria"]: row["total"] for row in db.category_breakdown(previous, "gasto")
        }
        deltas = {
            categoria: current_by_cat.get(categoria, 0.0) - previous_by_cat.get(categoria, 0.0)
            for categoria in set(current_by_cat) | set(previous_by_cat)
        }
        if deltas:
            top = max(deltas.items(), key=lambda item: abs(item[1]))
            direction = "aumento" if top[1] > 0 else "disminuyo"
            lines.append(
                f"- Mayor variacion por categoria: {top[0]} {direction} {money(abs(top[1]))}."
            )

    return "\n".join(lines)


def detectar_gastos_atipicos(meses: int = 12, umbral_z: float = 2.0) -> str:
    """Marca los meses en que una categoria se desvia de su propio historial."""
    if meses < 3:
        raise ToolInputError("El parametro 'meses' debe ser al menos 3 para calcular dispersion.")
    if umbral_z <= 0:
        raise ToolInputError("El parametro 'umbral_z' debe ser mayor que 0 (valor tipico: 2.0).")

    all_months = db.available_months()
    if not all_months:
        raise ToolInputError("La base de datos no contiene transacciones.")

    window = all_months[-meses:]
    series = db.category_month_series("gasto")

    findings: list[tuple[float, str, str, float, float, float]] = []
    for categoria, by_month in series.items():
        values = [by_month.get(month, 0.0) for month in window]
        observed = [value for value in values if value > 0]
        if len(observed) < 4:
            continue

        mean = statistics.fmean(values)
        scores = z_scores(values)
        for month, value, score in zip(window, values, scores):
            if abs(score) >= umbral_z:
                findings.append((abs(score), month, categoria, value, mean, score))

    lines = [heading(f"Deteccion de gastos atipicos (ultimos {len(window)} meses)")]
    lines.append(
        f"Metodo: z-score por categoria sobre su propio historial. Umbral: |z| >= {umbral_z}."
    )
    lines.append("")

    if not findings:
        lines.append(
            "No se detectaron gastos atipicos con este umbral. "
            "Prueba con un umbral_z menor (por ejemplo 1.5) para ver desviaciones mas leves."
        )
        return "\n".join(lines)

    findings.sort(reverse=True)
    rows = []
    for _abs_score, month, categoria, value, mean, score in findings:
        rows.append(
            [
                month,
                categoria,
                money(value),
                money(mean),
                percent(pct_change(value, mean), signed=True),
                f"{score:+.2f}",
            ]
        )
    lines.append(
        table(
            ["Mes", "Categoria", "Monto", "Promedio", "Desviacion", "z"],
            rows,
            align_right={2, 3, 4, 5},
        )
    )

    lines.append("")
    lines.append("Movimientos que explican las desviaciones mas altas:")
    for _abs_score, month, categoria, _value, _mean, _score in findings[:3]:
        largest = db.largest_transactions(month, "gasto", limit=3)
        for transaction in largest:
            if transaction["categoria"] == categoria:
                lines.append(
                    f"- {month} / {categoria}: {money(transaction['monto'])} "
                    f"({transaction['descripcion']}, {transaction['fecha']})"
                )
                break

    return "\n".join(lines)
