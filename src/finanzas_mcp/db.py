"""Acceso a la base de datos SQLite.

La base es un solo archivo que se construye la primera vez que se usa, a partir
de schema.sql (DDL) y seed.sql (DML). 

Todas las consultas son de solo lectura y parametrizadas; ninguna herramienta
arma SQL con texto que venga del modelo.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent.parent

SCHEMA_FILE = PACKAGE_DIR / "schema.sql"
SEED_FILE = PACKAGE_DIR / "seed.sql"

# Variable de entorno para que el chatbot o una prueba apunten a otro archivo.
DB_PATH_ENV = "FINANZAS_DB_PATH"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "finanzas.db"


class DatabaseError(RuntimeError):
    """No se pudo abrir o construir la base de datos."""


def resolve_db_path() -> Path:
    """Devuelve la ruta de la base, respetando FINANZAS_DB_PATH."""
    override = os.getenv(DB_PATH_ENV, "").strip()
    return Path(override).expanduser() if override else DEFAULT_DB_PATH


def build_database(path: Path) -> None:
    """Crea el archivo de la base y lo llena con los scripts SQL del paquete."""
    if not SCHEMA_FILE.exists() or not SEED_FILE.exists():
        raise DatabaseError(f"faltan los scripts SQL. Se esperaban {SCHEMA_FILE} y {SEED_FILE}.")

    path.parent.mkdir(parents=True, exist_ok=True)
    # Se construye en un archivo temporal para que un fallo a medio camino no deje
    # una base a medio llenar.
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.unlink(missing_ok=True)

    connection = sqlite3.connect(tmp_path)
    try:
        connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        connection.executescript(SEED_FILE.read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()

    tmp_path.replace(path)


def ensure_database(path: Path | None = None) -> Path:
    """Devuelve la ruta de una base lista para usar, construyendola si hace falta."""
    db_path = Path(path) if path is not None else resolve_db_path()
    if not db_path.exists() or db_path.stat().st_size == 0:
        build_database(db_path)
    return db_path


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Abre una conexion cuyas filas se acceden por nombre de columna."""
    db_path = ensure_database(path)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def query(sql: str, params: tuple[Any, ...] = (), path: Path | None = None) -> list[sqlite3.Row]:
    """Ejecuta un SELECT parametrizado y devuelve todas las filas."""
    with connect(path) as connection:
        return connection.execute(sql, params).fetchall()


def query_one(sql: str, params: tuple[Any, ...] = (), path: Path | None = None) -> sqlite3.Row | None:
    """Ejecuta un SELECT parametrizado y devuelve la primera fila, si hay."""
    with connect(path) as connection:
        return connection.execute(sql, params).fetchone()


def available_months(path: Path | None = None) -> list[str]:
    """Meses con al menos una transaccion, del mas viejo al mas nuevo."""
    rows = query(
        "SELECT DISTINCT substr(fecha, 1, 7) AS mes FROM transacciones ORDER BY mes",
        path=path,
    )
    return [row["mes"] for row in rows]


def latest_month(path: Path | None = None) -> str:
    """El mes mas reciente registrado."""
    months = available_months(path)
    if not months:
        raise DatabaseError("el libro de transacciones esta vacio")
    return months[-1]


def monthly_totals(tipo: str, path: Path | None = None) -> dict[str, float]:
    """Total de ingresos o de gastos por mes."""
    rows = query(
        """
        SELECT substr(fecha, 1, 7) AS mes, ROUND(SUM(monto), 2) AS total
        FROM transacciones
        WHERE tipo = ?
        GROUP BY mes
        ORDER BY mes
        """,
        (tipo,),
        path=path,
    )
    return {row["mes"]: row["total"] for row in rows}


def category_breakdown(mes: str, tipo: str, path: Path | None = None) -> list[sqlite3.Row]:
    """Totales por categoria de un mes, de mayor a menor."""
    return query(
        """
        SELECT c.nombre        AS categoria,
               c.es_fijo       AS es_fijo,
               COUNT(*)        AS n_transacciones,
               ROUND(SUM(t.monto), 2) AS total
        FROM transacciones t
        JOIN categorias c ON c.id = t.categoria_id
        WHERE substr(t.fecha, 1, 7) = ? AND t.tipo = ?
        GROUP BY c.id
        ORDER BY total DESC
        """,
        (mes, tipo),
        path=path,
    )


def category_month_series(tipo: str, path: Path | None = None) -> dict[str, dict[str, float]]:
    """Totales mensuales por categoria: {categoria: {'YYYY-MM': total}}."""
    rows = query(
        """
        SELECT c.nombre AS categoria,
               substr(t.fecha, 1, 7) AS mes,
               ROUND(SUM(t.monto), 2) AS total
        FROM transacciones t
        JOIN categorias c ON c.id = t.categoria_id
        WHERE t.tipo = ?
        GROUP BY c.id, mes
        ORDER BY c.nombre, mes
        """,
        (tipo,),
        path=path,
    )
    series: dict[str, dict[str, float]] = {}
    for row in rows:
        series.setdefault(row["categoria"], {})[row["mes"]] = row["total"]
    return series


def top_suppliers(mes: str, limit: int = 5, path: Path | None = None) -> list[sqlite3.Row]:
    """Proveedores a los que mas se les pago en un mes."""
    return query(
        """
        SELECT p.nombre AS proveedor,
               COUNT(*) AS n_compras,
               ROUND(SUM(t.monto), 2) AS total
        FROM transacciones t
        JOIN proveedores p ON p.id = t.proveedor_id
        WHERE substr(t.fecha, 1, 7) = ? AND t.tipo = 'gasto'
        GROUP BY p.id
        ORDER BY total DESC
        LIMIT ?
        """,
        (mes, limit),
        path=path,
    )


def fixed_categories(path: Path | None = None) -> list[str]:
    """Nombres de las categorias de gasto marcadas como fijas."""
    rows = query(
        "SELECT nombre FROM categorias WHERE tipo = 'gasto' AND es_fijo = 1 ORDER BY nombre",
        path=path,
    )
    return [row["nombre"] for row in rows]


def largest_transactions(
    mes: str, tipo: str, limit: int = 5, path: Path | None = None
) -> list[sqlite3.Row]:
    """Los movimientos individuales mas grandes de un mes."""
    return query(
        """
        SELECT t.fecha, t.monto, t.descripcion, c.nombre AS categoria
        FROM transacciones t
        JOIN categorias c ON c.id = t.categoria_id
        WHERE substr(t.fecha, 1, 7) = ? AND t.tipo = ?
        ORDER BY t.monto DESC
        LIMIT ?
        """,
        (mes, tipo, limit),
        path=path,
    )


def payroll_snapshot(path: Path | None = None) -> list[sqlite3.Row]:
    """Planilla activa con su costo mensual."""
    return query(
        """
        SELECT nombre, puesto, salario_mensual
        FROM empleados
        WHERE activo = 1
        ORDER BY salario_mensual DESC
        """,
        path=path,
    )
