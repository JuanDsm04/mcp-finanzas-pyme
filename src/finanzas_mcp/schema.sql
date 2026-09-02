-- mcp-finanzas-pyme - DDL
--
-- Contabilidad simulada de un negocio pequeno guatemalteco ("Panaderia La
-- Espiga"). Los montos estan en quetzales (GTQ).
--
-- Cinco tablas: categorias (marcadas como fijas o variables), proveedores,
-- clientes, empleados y transacciones, que es el libro de movimientos.

PRAGMA foreign_keys = ON;

-- Categorias de ingreso y gasto. El campo es_fijo es el que hace posible la
-- proyeccion de flujo de caja: los gastos fijos se proyectan como una base
-- recurrente y los variables como una proporcion de los ingresos.
CREATE TABLE categorias (
    id          INTEGER PRIMARY KEY,
    nombre      TEXT    NOT NULL UNIQUE,
    tipo        TEXT    NOT NULL CHECK (tipo IN ('ingreso', 'gasto')),
    es_fijo     INTEGER NOT NULL DEFAULT 0 CHECK (es_fijo IN (0, 1)),
    descripcion TEXT
);

-- Proveedores. dias_credito representa el plazo de pago (0 = contra entrega).
CREATE TABLE proveedores (
    id           INTEGER PRIMARY KEY,
    nombre       TEXT    NOT NULL UNIQUE,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id),
    dias_credito INTEGER NOT NULL DEFAULT 0,
    activo       INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))
);

-- Clientes que generan ingresos recurrentes e identificables. Las ventas de
-- mostrador se registran sin cliente.
CREATE TABLE clientes (
    id            INTEGER PRIMARY KEY,
    nombre        TEXT    NOT NULL UNIQUE,
    segmento      TEXT    NOT NULL CHECK (segmento IN ('corporativo', 'eventos', 'mayoreo')),
    fecha_alta    TEXT    NOT NULL,
    activo        INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))
);

-- Planilla. El gasto mensual de nomina sale de los empleados activos
CREATE TABLE empleados (
    id               INTEGER PRIMARY KEY,
    nombre           TEXT    NOT NULL,
    puesto           TEXT    NOT NULL,
    salario_mensual  REAL    NOT NULL CHECK (salario_mensual > 0),
    fecha_ingreso    TEXT    NOT NULL,
    fecha_salida     TEXT,
    activo           INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))
);

-- El libro de movimientos: una fila por transaccion. proveedor_id se llena en
-- los gastos pagados a un proveedor y cliente_id en los ingresos atribuibles a
-- un cliente conocido.
CREATE TABLE transacciones (
    id           INTEGER PRIMARY KEY,
    fecha        TEXT    NOT NULL,                  -- ISO 'YYYY-MM-DD'
    tipo         TEXT    NOT NULL CHECK (tipo IN ('ingreso', 'gasto')),
    monto        REAL    NOT NULL CHECK (monto > 0),
    categoria_id INTEGER NOT NULL REFERENCES categorias(id),
    proveedor_id INTEGER REFERENCES proveedores(id),
    cliente_id   INTEGER REFERENCES clientes(id),
    metodo_pago  TEXT    NOT NULL CHECK (metodo_pago IN ('efectivo', 'transferencia', 'tarjeta', 'cheque')),
    descripcion  TEXT
);

-- Indices para los tres patrones de acceso que usan todas las herramientas:
CREATE INDEX idx_transacciones_fecha     ON transacciones(fecha);
CREATE INDEX idx_transacciones_tipo      ON transacciones(tipo, fecha);
CREATE INDEX idx_transacciones_categoria ON transacciones(categoria_id, fecha);

-- Vista de apoyo: totales mensuales por categoria.
CREATE VIEW v_resumen_mensual AS
SELECT
    substr(t.fecha, 1, 7) AS mes,
    c.tipo                AS tipo,
    c.id                  AS categoria_id,
    c.nombre              AS categoria,
    c.es_fijo             AS es_fijo,
    COUNT(*)              AS n_transacciones,
    ROUND(SUM(t.monto), 2) AS total
FROM transacciones t
JOIN categorias c ON c.id = t.categoria_id
GROUP BY mes, c.id;