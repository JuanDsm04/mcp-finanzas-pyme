"""Caso 3: "me alcanzara el dinero para cubrir los gastos del proximo mes".

La proyeccion es transparente a proposito, porque la respuesta tiene que poder
defenderse ante el dueño del negocio: los ingresos se proyectan con una tendencia
corregida por estacionalidad, cada gasto fijo con su propio nivel e indice
estacional (asi julio con Bono 14 y diciembre con aguinaldo salen bien) y los
gastos variables como una proporcion de los ingresos, porque se mueven cuando se
mueven las ventas. Todos los numeros intermedios se imprimen.
"""

from __future__ import annotations

import statistics

from .. import db
from ..analytics import (
    DEFAULT_WINDOW,
    project,
    project_stable,
    ratio_to_income,
    runway_months,
    zero_fill,
)
from ..errors import ToolInputError
from ..formatting import bullet_list, heading, money, percent, table


def _fixed_and_variable_series() -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Separa el historial de gastos en series fijas por categoria y un total variable.

    Las series fijas se rellenan con ceros en todos los meses registrados: una
    poliza trimestral solo tiene filas en los meses que se pago, y sin esos ceros
    se proyectaria como si se pagara todos los meses.
    """
    per_category = db.category_month_series("gasto")
    fixed_names = set(db.fixed_categories())
    all_months = db.available_months()

    fixed_series = {
        name: zero_fill(series, all_months)
        for name, series in per_category.items()
        if name in fixed_names
    }

    variable_total: dict[str, float] = {}
    for name, series in per_category.items():
        if name in fixed_names:
            continue
        for month, value in series.items():
            variable_total[month] = variable_total.get(month, 0.0) + value

    return fixed_series, variable_total


def proyeccion_flujo_caja(
    meses: int = 1,
    saldo_inicial: float | None = None,
    ventana: int = DEFAULT_WINDOW,
) -> str:
    """Proyecta ingresos, gastos y saldo de los proximos meses.

    Si no se da un saldo inicial se usa el resultado acumulado de los ultimos 6
    meses como aproximacion, y se advierte en la respuesta.
    """
    if not 1 <= meses <= 6:
        raise ToolInputError(
            f"El parametro 'meses' debe estar entre 1 y 6 (recibido: {meses}). "
            "Proyectar mas alla de 6 meses con este historial no seria confiable."
        )
    if not 3 <= ventana <= 18:
        raise ToolInputError(f"El parametro 'ventana' debe estar entre 3 y 18 (recibido: {ventana}).")
    if saldo_inicial is not None and saldo_inicial < 0:
        raise ToolInputError("El 'saldo_inicial' no puede ser negativo.")

    income = db.monthly_totals("ingreso")
    expenses = db.monthly_totals("gasto")
    if len(income) < 3:
        raise ToolInputError("Se necesitan al menos 3 meses de historial para proyectar.")

    last_month = max(income)
    fixed_series, variable_series = _fixed_and_variable_series()

    income_projection = project(income, months_ahead=meses, window=ventana)

    # Nivel robusto en vez de una recta ajustada: una nomina de julio con Bono 14
    # inclinaria la tendencia e inflaria todos los meses siguientes.
    fixed_projection: dict[str, list[float]] = {}
    for name, series in fixed_series.items():
        if series:
            fixed_projection[name] = [p.value for p in project_stable(series, meses, ventana)]
        else:
            fixed_projection[name] = [0.0] * meses

    variable_ratio = ratio_to_income(variable_series, income, window=ventana)

    assumed_balance = saldo_inicial
    balance_note = ""
    if assumed_balance is None:
        recent_months = sorted(income)[-6:]
        assumed_balance = sum(
            income[month] - expenses.get(month, 0.0) for month in recent_months
        )
        assumed_balance = max(0.0, assumed_balance)
        balance_note = (
            f"No se indico un saldo inicial, asi que se usa el resultado acumulado de los "
            f"ultimos {len(recent_months)} meses ({money(assumed_balance)}) como aproximacion. "
            "Para una respuesta exacta, vuelve a llamar la herramienta indicando tu saldo real."
        )

    lines = [heading(f"Proyeccion de flujo de caja - {meses} mes(es) desde {last_month}")]
    lines.append(
        "Metodo: los ingresos se proyectan con una tendencia de minimos cuadrados "
        f"sobre los ultimos {ventana} meses corregida por estacionalidad; cada gasto "
        "fijo se proyecta con la mediana de su propio historial mas su indice "
        "estacional (asi julio con Bono 14 y diciembre con aguinaldo salen bien); "
        f"los gastos variables se estiman como {percent(variable_ratio * 100)} de los "
        "ingresos proyectados (mediana historica)."
    )
    if balance_note:
        lines.append("")
        lines.append(balance_note)
    lines.append("")

    rows = []
    balance = assumed_balance
    monthly_detail: list[tuple[str, float, float, float, float, float]] = []

    for index, projection in enumerate(income_projection):
        month = projection.month
        projected_income = projection.value
        projected_fixed = sum(values[index] for values in fixed_projection.values())
        projected_variable = projected_income * variable_ratio
        net = projected_income - projected_fixed - projected_variable
        balance += net

        monthly_detail.append(
            (month, projected_income, projected_fixed, projected_variable, net, balance)
        )
        rows.append(
            [
                month,
                money(projected_income),
                money(projected_fixed),
                money(projected_variable),
                money(net) if net >= 0 else "-" + money(abs(net)),
                money(balance) if balance >= 0 else "-" + money(abs(balance)),
            ]
        )

    lines.append(
        table(
            ["Mes", "Ingresos", "Gastos fijos", "Gastos var.", "Flujo neto", "Saldo"],
            rows,
            align_right={1, 2, 3, 4, 5},
        )
    )

    first_month = income_projection[0].month
    lines.append("")
    lines.append(f"Composicion de los gastos fijos proyectados para {first_month}:")
    lines.append(
        table(
            ["Categoria", "Proyectado"],
            [
                [name, money(values[0])]
                for name, values in sorted(
                    fixed_projection.items(), key=lambda item: -item[1][0]
                )
            ],
            align_right={1},
        )
    )

    month, projected_income, projected_fixed, projected_variable, net, _balance = monthly_detail[0]
    lines.append("")
    lines.append(heading(f"Respuesta para {month}"))

    covers_fixed = projected_income >= projected_fixed
    covers_all = net >= 0
    cushion = projected_income - projected_fixed

    if covers_all:
        verdict = (
            f"SI. Los ingresos proyectados ({money(projected_income)}) cubren los gastos fijos "
            f"({money(projected_fixed)}) y los variables ({money(projected_variable)}), "
            f"con un excedente de {money(net)}."
        )
    elif covers_fixed:
        verdict = (
            f"AJUSTADO. Los ingresos proyectados ({money(projected_income)}) cubren los gastos "
            f"fijos ({money(projected_fixed)}), pero al sumar los variables "
            f"({money(projected_variable)}) el flujo del mes queda en {money(net)} negativo. "
            f"Necesitas cubrir esa diferencia con el saldo disponible."
        )
    else:
        verdict = (
            f"NO. Los ingresos proyectados ({money(projected_income)}) no alcanzan a cubrir "
            f"los gastos fijos ({money(projected_fixed)}); faltan {money(abs(cushion))}."
        )
    lines.append(verdict)

    burn = projected_fixed
    months_of_runway = runway_months(assumed_balance, burn)
    observations = [
        f"Excedente de los ingresos sobre los gastos fijos: {money(cushion)} "
        f"(los ingresos cubren "
        f"{projected_income / projected_fixed:.2f}x los gastos fijos)."
        if projected_fixed
        else f"Excedente de los ingresos sobre los gastos fijos: {money(cushion)}.",
    ]
    if months_of_runway is not None:
        observations.append(
            f"Con el saldo asumido, los gastos fijos estan cubiertos por "
            f"{months_of_runway:.1f} mes(es) aun sin ingresos."
        )
    if meses > 1:
        worst = min(monthly_detail, key=lambda item: item[5])
        observations.append(
            f"El saldo mas bajo del periodo proyectado ocurre en {worst[0]}: {money(worst[5])}."
        )
    lines.append("")
    lines.append(bullet_list(observations))

    lines.append("")
    lines.append(
        "Advertencia: esta es una proyeccion estadistica basada en el historial "
        "registrado. No considera compromisos futuros, inversiones planificadas ni "
        "cambios de precios que no esten reflejados en los datos."
    )

    return "\n".join(lines)


def salud_financiera() -> str:
    """Resume en una pantalla como va el negocio.

    Incluye promedios de los ultimos 6 meses, margen, cobertura de gastos fijos,
    peso de la nomina, meses con perdida en el ultimo ano y la planilla activa.
    """
    income = db.monthly_totals("ingreso")
    expenses = db.monthly_totals("gasto")
    if not income:
        raise ToolInputError("La base de datos no contiene transacciones.")

    months = sorted(income)
    last_month = months[-1]
    recent = months[-6:]

    average_income = statistics.fmean(income[month] for month in recent)
    average_expense = statistics.fmean(expenses.get(month, 0.0) for month in recent)
    average_profit = average_income - average_expense

    fixed_series, _variable = _fixed_and_variable_series()
    fixed_recent = [
        sum(series.get(month, 0.0) for series in fixed_series.values()) for month in recent
    ]
    average_fixed = statistics.fmean(fixed_recent)

    losses = [
        month for month in months[-12:] if income[month] - expenses.get(month, 0.0) < 0
    ]
    payroll = db.payroll_snapshot()
    payroll_cost = sum(row["salario_mensual"] for row in payroll)

    lines = [heading("Salud financiera del negocio")]
    lines.append(f"Ultimo mes cerrado: {last_month}")
    lines.append(f"Historial disponible: {months[0]} a {months[-1]} ({len(months)} meses)")
    lines.append("")
    lines.append(
        table(
            ["Indicador", "Valor"],
            [
                ["Ingreso promedio (6 meses)", money(average_income)],
                ["Gasto promedio (6 meses)", money(average_expense)],
                ["Resultado promedio (6 meses)", money(average_profit)],
                [
                    "Margen neto promedio",
                    percent(average_profit / average_income * 100 if average_income else None,
                            signed=True),
                ],
                ["Gastos fijos promedio", money(average_fixed)],
                [
                    "Cobertura de gastos fijos",
                    f"{average_income / average_fixed:.2f}x" if average_fixed else "n/d",
                ],
                ["Nomina activa (mensual)", money(payroll_cost)],
                [
                    "Peso de la nomina sobre ingresos",
                    percent(payroll_cost / average_income * 100 if average_income else None),
                ],
                ["Meses con perdida (ultimos 12)", f"{len(losses)} de {len(months[-12:])}"],
            ],
            align_right={1},
        )
    )

    if losses:
        lines.append("")
        lines.append(f"Meses con resultado negativo: {', '.join(losses)}")
        lines.append(
            "  Revisa esos meses con 'estado_resultados' y 'detectar_gastos_atipicos' "
            "para identificar la causa."
        )

    lines.append("")
    lines.append(f"Personal activo ({len(payroll)} personas):")
    lines.append(
        table(
            ["Nombre", "Puesto", "Salario"],
            [[row["nombre"], row["puesto"], money(row["salario_mensual"])] for row in payroll],
            align_right={2},
        )
    )

    return "\n".join(lines)
