"""Genera el archivo seed.sql con los datos simulados.

El generador es determinista (semilla fija), asi que volver a correrlo produce
exactamente el mismo archivo.

"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

SEED = 20260906
RNG = random.Random(SEED)

START = date(2025, 1, 1)
END = date(2026, 8, 31)

OUTPUT = Path(__file__).resolve().parent.parent / "src" / "finanzas_mcp" / "seed.sql"


# (id, nombre, tipo, es_fijo, descripcion)
CATEGORIAS = [
    (1, "Ventas mostrador", "ingreso", 0, "Venta diaria al publico en el local"),
    (2, "Pedidos corporativos", "ingreso", 0, "Ordenes recurrentes de empresas"),
    (3, "Eventos", "ingreso", 0, "Pedidos especiales para eventos y celebraciones"),
    (4, "Alquiler", "gasto", 1, "Renta mensual del local"),
    (5, "Nomina", "gasto", 1, "Sueldos, Bono 14 y aguinaldo"),
    (6, "Servicios", "gasto", 1, "Energia electrica, agua e internet"),
    (7, "Seguros", "gasto", 1, "Poliza de local y equipo (pago trimestral)"),
    (8, "Insumos", "gasto", 0, "Harina, azucar, lacteos y demas materia prima"),
    (9, "Marketing", "gasto", 0, "Publicidad en redes y material impreso"),
    (10, "Mantenimiento", "gasto", 0, "Reparacion de hornos, refrigeracion y local"),
    (11, "Transporte", "gasto", 0, "Combustible y reparto de pedidos"),
    (12, "Impuestos", "gasto", 0, "IVA e ISR sobre ventas"),
]

# (id, nombre, categoria_id, dias_credito, activo)
PROVEEDORES = [
    (1, "Molinos del Valle", 8, 30, 1),
    (2, "Distribuidora Lacteos Xela", 8, 15, 1),
    (3, "Azucarera Central", 8, 30, 1),
    (4, "Empaques y Cajas GT", 8, 0, 1),
    (5, "Publicidad Creativa", 9, 0, 1),
    (6, "Refrigeracion Tecnica", 10, 0, 1),
    (7, "Servicios Hornos Industriales", 10, 0, 1),
    (8, "Combustibles La Ruta", 11, 0, 1),
]

# (id, nombre, segmento, fecha_alta, activo)
CLIENTES = [
    (1, "Cafeteria El Portal", "corporativo", "2025-01-10", 1),
    (2, "Hotel Vista Real", "corporativo", "2025-01-22", 1),
    (3, "Colegio San Jose", "corporativo", "2025-03-05", 1),
    (4, "Restaurante La Cocina", "corporativo", "2025-06-18", 1),
    (5, "Eventos Villa Nueva", "eventos", "2025-02-14", 1),
    (6, "Banquetes Antigua", "eventos", "2025-09-02", 1),
    (7, "Tienda Mayoreo Zona 5", "mayoreo", "2026-01-15", 1),
]

# (id, nombre, puesto, salario, ingreso, salida, activo)
EMPLEADOS = [
    (1, "Maria Lopez", "Panadero jefe", 5500.00, "2024-08-01", None, 1),
    (2, "Carlos Ramirez", "Panadero", 3800.00, "2024-11-15", None, 1),
    (3, "Ana Gutierrez", "Auxiliar de panaderia", 3200.00, "2025-01-06", None, 1),
    (4, "Jorge Morales", "Cajero", 3300.00, "2025-01-06", None, 1),
    (5, "Luis Perez", "Repartidor", 3400.00, "2025-02-03", "2026-04-30", 0),
    (6, "Sofia Castillo", "Auxiliar de ventas", 3100.00, "2025-09-01", None, 1),
    # Contratados conforme crece el negocio, para que la planilla siga a las ventas.
    (7, "Pedro Chavez", "Panadero auxiliar", 3400.00, "2025-06-02", None, 1),
    (8, "Elena Marroquin", "Cajero fin de semana", 3100.00, "2025-11-03", None, 1),
    (9, "Diego Herrera", "Repostero", 4200.00, "2026-03-02", None, 1),
]

# Multiplicadores de estacionalidad de las ventas de mostrador
SEASONALITY = {
    1: 0.86, 2: 0.88, 3: 0.97, 4: 1.02, 5: 1.05, 6: 0.99,
    7: 1.03, 8: 1.01, 9: 0.98, 10: 1.04, 11: 1.12, 12: 1.28,
}

BASE_DAILY_SALES = 2100.0
MONTHLY_GROWTH = 0.014

# Caida deliberada: estos meses llevan un factor extra para que las herramientas
# de tendencia tengan algo real que reportar.
SOFT_PATCH = {"2026-05": 0.90, "2026-06": 0.87, "2026-07": 0.95}

# Anomalias plantadas: (fecha, categoria_id, proveedor_id, monto, descripcion)
ANOMALIAS = [
    ("2026-03-11", 10, 7, 18500.00, "Reemplazo de horno rotativo principal"),
    ("2025-11-06", 9, 5, 7200.00, "Campana publicitaria fin de ano"),
]

METODOS = ["efectivo", "transferencia", "tarjeta", "cheque"]


def month_keys(start: date, end: date) -> list[str]:
    """Devuelve todas las claves 'YYYY-MM' del intervalo."""
    keys: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        keys.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return keys


def days_in_month(year: int, month: int) -> int:
    """Cantidad de dias de un mes."""
    if month == 12:
        return (date(year + 1, 1, 1) - date(year, month, 1)).days
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def growth_factor(month_index: int) -> float:
    """Crecimiento compuesto aplicado al mes numero month_index."""
    return (1 + MONTHLY_GROWTH) ** month_index


def sql_str(value: str | None) -> str:
    """Convierte un valor en un literal SQL, escapando las comillas simples."""
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def money(value: float) -> float:
    """Redondea a centavos."""
    return round(value + 0.0, 2)


def active_employees(month_key: str) -> list[tuple]:
    """Empleados en planilla durante el mes dado."""
    result = []
    for emp in EMPLEADOS:
        _id, _nombre, _puesto, _salario, ingreso, salida, _activo = emp
        if ingreso[:7] > month_key:
            continue
        if salida is not None and salida[:7] < month_key:
            continue
        result.append(emp)
    return result


class Ledger:
    """Acumula las transacciones y las convierte en sentencias INSERT."""

    def __init__(self) -> None:
        self.rows: list[tuple] = []
        self._next_id = 1

    def add(
        self,
        fecha: str,
        tipo: str,
        monto: float,
        categoria_id: int,
        metodo: str,
        descripcion: str,
        proveedor_id: int | None = None,
        cliente_id: int | None = None,
    ) -> None:
        self.rows.append(
            (
                self._next_id,
                fecha,
                tipo,
                money(monto),
                categoria_id,
                proveedor_id,
                cliente_id,
                metodo,
                descripcion,
            )
        )
        self._next_id += 1

    def sort_by_date(self) -> None:
        """Renumera los ids para que sigan el orden cronologico."""
        self.rows.sort(key=lambda r: (r[1], r[0]))
        self.rows = [(i + 1, *row[1:]) for i, row in enumerate(self.rows)]


def generate() -> Ledger:
    """Genera todo el libro de movimientos del periodo configurado."""
    ledger = Ledger()
    months = month_keys(START, END)

    for index, month_key in enumerate(months):
        year, month = int(month_key[:4]), int(month_key[5:])
        n_days = days_in_month(year, month)
        last_day = min(date(year, month, n_days), END)

        season = SEASONALITY[month]
        growth = growth_factor(index)
        damp = SOFT_PATCH.get(month_key, 1.0)
        daily_base = BASE_DAILY_SALES * season * growth * damp

        month_income = _counter_sales(ledger, year, month, last_day, daily_base)
        month_income += _corporate_orders(ledger, year, month, last_day, growth, damp)
        month_income += _events(ledger, year, month, last_day, growth, damp)

        _fixed_costs(ledger, year, month, month_key, last_day)
        _variable_costs(ledger, year, month, last_day, month_income)

    _planted_anomalies(ledger)
    ledger.sort_by_date()
    return ledger


def _counter_sales(ledger: Ledger, year: int, month: int, last_day: date, daily: float) -> float:
    """Ventas diarias de mostrador; los domingos no se abre."""
    total = 0.0
    day = date(year, month, 1)
    while day <= last_day:
        if day.weekday() != 6:  # domingo: cerrado
            # El fin de semana se vende mas que entre semana.
            weekday_factor = 1.25 if day.weekday() >= 4 else 0.95
            amount = daily * weekday_factor * RNG.uniform(0.86, 1.14)
            method = RNG.choices(METODOS[:3], weights=[0.62, 0.10, 0.28])[0]
            ledger.add(
                day.isoformat(),
                "ingreso",
                amount,
                1,
                method,
                "Venta de mostrador del dia",
            )
            total += amount
        day += timedelta(days=1)
    return total


def _corporate_orders(
    ledger: Ledger, year: int, month: int, last_day: date, growth: float, damp: float
) -> float:
    """Pedidos recurrentes de los clientes corporativos activos en el mes."""
    month_key = f"{year:04d}-{month:02d}"
    available = [c for c in CLIENTES if c[2] != "eventos" and c[3][:7] <= month_key]
    total = 0.0

    for cliente in available:
        for _ in range(RNG.randint(1, 3)):
            day = RNG.randint(1, last_day.day)
            amount = RNG.uniform(1400, 4200) * growth * damp
            ledger.add(
                date(year, month, day).isoformat(),
                "ingreso",
                amount,
                2,
                RNG.choices(["transferencia", "cheque"], weights=[0.8, 0.2])[0],
                f"Pedido recurrente - {cliente[1]}",
                cliente_id=cliente[0],
            )
            total += amount
    return total


def _events(
    ledger: Ledger, year: int, month: int, last_day: date, growth: float, damp: float
) -> float:
    """Pedidos para eventos, mas frecuentes en noviembre y diciembre."""
    month_key = f"{year:04d}-{month:02d}"
    available = [c for c in CLIENTES if c[2] == "eventos" and c[3][:7] <= month_key]
    if not available:
        return 0.0

    n_events = RNG.randint(2, 4) if month in (11, 12) else RNG.randint(0, 2)
    total = 0.0
    for _ in range(n_events):
        cliente = RNG.choice(available)
        day = RNG.randint(1, last_day.day)
        amount = RNG.uniform(2800, 9500) * growth * damp
        ledger.add(
            date(year, month, day).isoformat(),
            "ingreso",
            amount,
            3,
            "transferencia",
            f"Pedido para evento - {cliente[1]}",
            cliente_id=cliente[0],
        )
        total += amount
    return total


def _fixed_costs(ledger: Ledger, year: int, month: int, month_key: str, last_day: date) -> None:
    """Alquiler, nomina, servicios y la poliza trimestral."""
    # Alquiler: se paga el 1, con un aumento en enero de 2026.
    rent = 6500.00 if month_key < "2026-01" else 7000.00
    ledger.add(
        date(year, month, 1).isoformat(),
        "gasto",
        rent,
        4,
        "transferencia",
        "Alquiler del local",
    )

    # Nomina: se paga el ultimo dia del mes.
    roster = active_employees(month_key)
    payroll = sum(emp[3] for emp in roster)
    concept = "Nomina mensual"
    if month == 7:  # Bono 14: un salario mensual extra en julio.
        payroll += sum(emp[3] for emp in roster)
        concept = "Nomina mensual + Bono 14"
    elif month == 12:  # Aguinaldo, en diciembre.
        payroll += sum(emp[3] for emp in roster)
        concept = "Nomina mensual + aguinaldo"
    ledger.add(
        last_day.isoformat(), "gasto", payroll, 5, "transferencia", concept
    )

    # Servicios: suben en los meses calidos por la refrigeracion.
    utilities = RNG.uniform(1750, 2250) * (1.18 if month in (3, 4, 5) else 1.0)
    ledger.add(
        date(year, month, min(15, last_day.day)).isoformat(),
        "gasto",
        utilities,
        6,
        "transferencia",
        "Energia electrica, agua e internet",
    )

    # Seguro: prima trimestral.
    if month in (1, 4, 7, 10):
        ledger.add(
            date(year, month, min(10, last_day.day)).isoformat(),
            "gasto",
            2850.00,
            7,
            "transferencia",
            "Poliza trimestral de local y equipo",
        )


def _variable_costs(
    ledger: Ledger, year: int, month: int, last_day: date, month_income: float
) -> None:
    """Gastos que suben con las ventas: insumos, transporte, impuestos y marketing."""
    # Insumos y empaque: ~44% de los ingresos, repartidos en unas 8 compras. Esa
    # proporcion es la que deja el margen neto en el rango de una panaderia real.
    target_inputs = month_income * RNG.uniform(0.42, 0.46)
    suppliers = [p for p in PROVEEDORES if p[2] == 8]
    n_purchases = RNG.randint(7, 10)
    weights = [RNG.uniform(0.6, 1.4) for _ in range(n_purchases)]
    scale = target_inputs / sum(weights)
    for weight in weights:
        proveedor = RNG.choice(suppliers)
        day = RNG.randint(1, last_day.day)
        ledger.add(
            date(year, month, day).isoformat(),
            "gasto",
            weight * scale,
            8,
            RNG.choices(["transferencia", "efectivo", "cheque"], weights=[0.6, 0.25, 0.15])[0],
            f"Compra de insumos - {proveedor[1]}",
            proveedor_id=proveedor[0],
        )

    # Transporte: combustible y reparto semanal.
    for week in range(4):
        day = min(3 + week * 7, last_day.day)
        ledger.add(
            date(year, month, day).isoformat(),
            "gasto",
            RNG.uniform(320, 620),
            11,
            "efectivo",
            "Combustible y reparto",
            proveedor_id=8,
        )

    # Marketing: una o dos acciones al mes.
    for _ in range(RNG.randint(1, 2)):
        day = RNG.randint(1, last_day.day)
        ledger.add(
            date(year, month, day).isoformat(),
            "gasto",
            RNG.uniform(450, 1400),
            9,
            RNG.choice(["transferencia", "tarjeta"]),
            "Publicidad en redes sociales",
            proveedor_id=5,
        )

    # Mantenimiento: no todos los meses.
    if RNG.random() < 0.55:
        day = RNG.randint(1, last_day.day)
        ledger.add(
            date(year, month, day).isoformat(),
            "gasto",
            RNG.uniform(600, 2100),
            10,
            RNG.choice(["efectivo", "transferencia"]),
            "Mantenimiento preventivo de equipo",
            proveedor_id=RNG.choice([6, 7]),
        )

    # Impuestos: pago mensual proporcional a los ingresos.
    ledger.add(
        last_day.isoformat(),
        "gasto",
        month_income * RNG.uniform(0.048, 0.056),
        12,
        "transferencia",
        "Pago mensual de impuestos",
    )


def _planted_anomalies(ledger: Ledger) -> None:
    """Dos gastos grandes y puntuales, para probar la deteccion de atipicos."""
    for fecha, categoria_id, proveedor_id, monto, descripcion in ANOMALIAS:
        ledger.add(
            fecha,
            "gasto",
            monto,
            categoria_id,
            "cheque",
            descripcion,
            proveedor_id=proveedor_id,
        )


def render(ledger: Ledger) -> str:
    """Convierte todo el conjunto de datos en un script SQL."""
    out: list[str] = []
    add = out.append

    add("-- mcp-finanzas-pyme - DML (datos simulados)")
    add("--")
    add("-- ARCHIVO GENERADO - no editar a mano.")
    add("-- Regenerar con:  python scripts/generate_seed.py")
    add(f"-- Semilla del generador: {SEED}")
    add(f"-- Periodo cubierto: {START.isoformat()} .. {END.isoformat()}")
    add(f"-- Transacciones: {len(ledger.rows)}")
    add("")
    add("BEGIN TRANSACTION;")
    add("")

    add("-- Categorias")
    for cid, nombre, tipo, es_fijo, desc in CATEGORIAS:
        add(
            "INSERT INTO categorias (id, nombre, tipo, es_fijo, descripcion) VALUES "
            f"({cid}, {sql_str(nombre)}, {sql_str(tipo)}, {es_fijo}, {sql_str(desc)});"
        )
    add("")

    add("-- Proveedores")
    for pid, nombre, cat, credito, activo in PROVEEDORES:
        add(
            "INSERT INTO proveedores (id, nombre, categoria_id, dias_credito, activo) VALUES "
            f"({pid}, {sql_str(nombre)}, {cat}, {credito}, {activo});"
        )
    add("")

    add("-- Clientes")
    for cid, nombre, segmento, alta, activo in CLIENTES:
        add(
            "INSERT INTO clientes (id, nombre, segmento, fecha_alta, activo) VALUES "
            f"({cid}, {sql_str(nombre)}, {sql_str(segmento)}, {sql_str(alta)}, {activo});"
        )
    add("")

    add("-- Empleados")
    for eid, nombre, puesto, salario, ingreso, salida, activo in EMPLEADOS:
        add(
            "INSERT INTO empleados (id, nombre, puesto, salario_mensual, fecha_ingreso, "
            "fecha_salida, activo) VALUES "
            f"({eid}, {sql_str(nombre)}, {sql_str(puesto)}, {salario:.2f}, "
            f"{sql_str(ingreso)}, {sql_str(salida)}, {activo});"
        )
    add("")

    add("-- Transacciones")
    for row in ledger.rows:
        tid, fecha, tipo, monto, cat, prov, cli, metodo, desc = row
        add(
            "INSERT INTO transacciones (id, fecha, tipo, monto, categoria_id, proveedor_id, "
            "cliente_id, metodo_pago, descripcion) VALUES "
            f"({tid}, {sql_str(fecha)}, {sql_str(tipo)}, {monto:.2f}, {cat}, "
            f"{prov if prov is not None else 'NULL'}, "
            f"{cli if cli is not None else 'NULL'}, {sql_str(metodo)}, {sql_str(desc)});"
        )
    add("")
    add("COMMIT;")
    add("")
    return "\n".join(out)


def main() -> None:
    ledger = generate()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(ledger), encoding="utf-8")
    print(f"Wrote {OUTPUT} with {len(ledger.rows)} transactions.")


if __name__ == "__main__":
    main()
