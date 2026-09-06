"""Punto de entrada del servidor MCP.

Expone el asistente financiero por el transporte stdio: el anfitrion lo lanza
como subproceso y le habla JSON-RPC 2.0 por stdin/stdout.

Se ejecuta con: python -m finanzas_mcp.server
"""

from __future__ import annotations

import argparse
import os
import sys

from mcp.server.fastmcp import FastMCP

from . import db
from .tools import (
    desglose_gastos as _desglose_gastos,
    detectar_gastos_atipicos as _detectar_gastos_atipicos,
    estado_resultados as _estado_resultados,
    proyeccion_flujo_caja as _proyeccion_flujo_caja,
    salud_financiera as _salud_financiera,
    tendencia_ingresos as _tendencia_ingresos,
)

SERVER_NAME = "finanzas-pyme"

INSTRUCTIONS = """Asistente financiero para una PYME (panaderia) con contabilidad simulada.

Usa estas herramientas cuando el usuario pregunte por gastos, ingresos, rentabilidad,
tendencias o si le alcanzara el dinero. Todos los montos estan en quetzales (GTQ).
Los meses se expresan como 'YYYY-MM'; si el usuario no especifica un mes, omite el
parametro y la herramienta usara el ultimo mes con datos.

Nunca inventes cifras: si una herramienta devuelve un error, leelo y corrige la llamada."""

mcp = FastMCP(SERVER_NAME, instructions=INSTRUCTIONS)


@mcp.tool()
def desglose_gastos(mes: str | None = None, incluir_comparacion: bool = True) -> str:
    """Desglosa los gastos de un mes por categoria (proveedores, nomina, servicios, etc.).

    Responde preguntas como "cuanto gaste en julio" o "en que se me fue el dinero
    el mes pasado". Devuelve el total, el reparto por categoria con porcentajes,
    la separacion entre gastos fijos y variables, los principales proveedores y
    los movimientos individuales mas grandes.

    Args:
        mes: Mes a analizar en formato 'YYYY-MM' (ej. '2026-08'). Si se omite,
            se usa el ultimo mes con datos registrados.
        incluir_comparacion: Si es True, agrega la comparacion contra el mes
            anterior y contra el promedio de los tres meses previos.
    """
    return _desglose_gastos(mes=mes, incluir_comparacion=incluir_comparacion)


@mcp.tool()
def detectar_gastos_atipicos(meses: int = 12, umbral_z: float = 2.0) -> str:
    """Detecta gastos inusuales comparando cada categoria contra su propio historial.

    Util para responder "hubo algun gasto raro?" o para explicar por que un mes
    salio mal. Calcula el z-score de cada categoria por mes y reporta las
    desviaciones que superan el umbral, junto con el movimiento que las explica.

    Args:
        meses: Cuantos meses hacia atras inspeccionar (minimo 3).
        umbral_z: Desviaciones estandar minimas para reportar un gasto como
            atipico. 2.0 es estricto; 1.5 muestra mas casos.
    """
    return _detectar_gastos_atipicos(meses=meses, umbral_z=umbral_z)


@mcp.tool()
def tendencia_ingresos(mes: str | None = None, meses: int = 6) -> str:
    """Analiza si los ingresos estan creciendo o bajando, con numeros concretos.

    Responde "mis ventas van subiendo o bajando?". Entrega tres niveles de
    evidencia: la variacion contra el mes anterior, la comparacion interanual
    (que elimina el efecto de la estacionalidad) y una tendencia ajustada por
    minimos cuadrados con su R2 para indicar que tan confiable es.

    Args:
        mes: Ultimo mes de la ventana de analisis en formato 'YYYY-MM'. Si se
            omite, se usa el ultimo mes con datos.
        meses: Tamano de la ventana de analisis, entre 3 y 24 meses.
    """
    return _tendencia_ingresos(mes=mes, meses=meses)


@mcp.tool()
def estado_resultados(mes: str | None = None) -> str:
    """Genera el estado de resultados de un mes: ingresos, gastos, utilidad y margen.

    Responde "gane o perdi dinero en mayo?". Muestra los ingresos y gastos
    desglosados por categoria, separa gastos fijos de variables y calcula la
    utilidad neta y el margen, con el mes anterior como referencia.

    Args:
        mes: Mes en formato 'YYYY-MM'. Si se omite, se usa el ultimo mes con datos.
    """
    return _estado_resultados(mes=mes)


@mcp.tool()
def proyeccion_flujo_caja(
    meses: int = 1,
    saldo_inicial: float | None = None,
    ventana: int = 6,
) -> str:
    """Proyecta si alcanzara el dinero para cubrir los gastos del proximo mes.

    Responde "me va a alcanzar el mes que viene?". Proyecta los ingresos con una
    tendencia corregida por estacionalidad, los gastos fijos categoria por
    categoria (lo que hace que julio con Bono 14 y diciembre con aguinaldo salgan
    correctos) y los gastos variables como proporcion de los ingresos. Devuelve
    el flujo neto, el saldo proyectado y una respuesta directa.

    Args:
        meses: Cuantos meses proyectar hacia adelante, entre 1 y 6.
        saldo_inicial: Saldo en caja al inicio de la proyeccion, en quetzales.
            Si se omite se usa el resultado acumulado de los ultimos 6 meses
            como aproximacion, y se advierte en la respuesta.
        ventana: Cuantos meses de historial usar para ajustar la tendencia (3 a 18).
    """
    return _proyeccion_flujo_caja(meses=meses, saldo_inicial=saldo_inicial, ventana=ventana)


@mcp.tool()
def salud_financiera() -> str:
    """Resumen general del negocio en una sola pantalla.

    Util como primera llamada cuando el usuario pregunta algo amplio como "como
    va mi negocio?". Devuelve promedios de los ultimos 6 meses, margen neto,
    cobertura de gastos fijos, peso de la nomina, meses con perdida en el ultimo
    ano y la planilla activa.
    """
    return _salud_financiera()


@mcp.resource("finanzas://esquema", mime_type="text/plain")
def recurso_esquema() -> str:
    """DDL completo de la base de datos simulada (5 tablas y una vista)."""
    return db.SCHEMA_FILE.read_text(encoding="utf-8")


@mcp.resource("finanzas://catalogo/categorias", mime_type="text/plain")
def recurso_categorias() -> str:
    """Catalogo de categorias de ingreso y gasto, con la marca de fijo/variable."""
    rows = db.query(
        "SELECT nombre, tipo, es_fijo, descripcion FROM categorias ORDER BY tipo, nombre"
    )
    lines = ["nombre|tipo|es_fijo|descripcion"]
    lines += [
        f"{row['nombre']}|{row['tipo']}|{row['es_fijo']}|{row['descripcion']}" for row in rows
    ]
    return "\n".join(lines)


@mcp.resource("finanzas://meses", mime_type="text/plain")
def recurso_meses() -> str:
    """Meses con datos disponibles, uno por linea."""
    return "\n".join(db.available_months())


@mcp.prompt()
def revision_mensual(mes: str = "") -> str:
    """Plantilla para una revision financiera completa de un mes."""
    objetivo = mes.strip() or "el ultimo mes con datos"
    return (
        f"Hazme una revision financiera de {objetivo} de mi negocio. "
        "Usa las herramientas disponibles para: "
        "1) obtener el estado de resultados del mes, "
        "2) desglosar los gastos por categoria, "
        "3) revisar si la tendencia de ingresos viene subiendo o bajando, y "
        "4) detectar gastos atipicos. "
        "Al final dame tres conclusiones concretas y una recomendacion accionable, "
        "en lenguaje sencillo, sin jerga contable."
    )


def main() -> int:
    """Lee los argumentos, prepara la base de datos y sirve por stdio."""
    parser = argparse.ArgumentParser(
        prog="finanzas-mcp",
        description="Servidor MCP: asistente financiero para PYMES sobre una base SQLite simulada.",
    )
    parser.add_argument(
        "--db-path",
        help="Ubicacion del archivo SQLite. Tiene prioridad sobre FINANZAS_DB_PATH. "
        "Se construye solo desde los scripts SQL del paquete si no existe.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Borra y reconstruye la base de datos antes de arrancar.",
    )
    args = parser.parse_args()

    if args.db_path:
        os.environ[db.DB_PATH_ENV] = args.db_path

    db_path = db.resolve_db_path()
    if args.rebuild and db_path.exists():
        db_path.unlink()

    # Se construye la base antes de la primera peticion para que un fallo salga al
    # arrancar y no dentro de una llamada a una herramienta.
    try:
        db.ensure_database(db_path)
    except db.DatabaseError as exc:
        print(f"[finanzas-mcp] {exc}", file=sys.stderr)
        return 1

    print(f"[finanzas-mcp] usando la base {db_path}", file=sys.stderr)
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
