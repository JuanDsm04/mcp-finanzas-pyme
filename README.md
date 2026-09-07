# finanzas-mcp — SME finance assistant (MCP server)

An **MCP (Model Context Protocol) server** that lets an LLM answer real finance
questions for a small business owner with no accountant: *what did I spend last
month and on what, are my sales growing, and will I have enough money next
month?*

It runs locally over the **stdio** transport and speaks JSON-RPC 2.0, so any MCP
host — Claude Desktop, VS Code, or a custom chatbot — can use it.

## What it does

The server does not just run SELECTs. Each tool applies a documented method and
returns a report that states its own assumptions:

| Tool | Question it answers | Method |
|------|--------------------|--------|
| `desglose_gastos` | "How much did I spend in July, and on what?" | Category breakdown with shares, fixed/variable split, comparison against the previous month and the 3-month average |
| `tendencia_ingresos` | "Are my sales growing or falling?" | Month-over-month, year-over-year, and a least-squares trend reported **with its R²** |
| `proyeccion_flujo_caja` | "Will I have enough money next month?" | Income as a damped seasonal trend; fixed costs as level × seasonal index; variable costs as a median share of income |
| `estado_resultados` | "Did I make or lose money in May?" | Profit-and-loss statement with net margin |
| `detectar_gastos_atipicos` | "Was there any unusual expense?" | Per-category z-scores against each category's own history |
| `salud_financiera` | "How is my business doing overall?" | Trailing averages, fixed-cost coverage, payroll weight, loss-making months |

## The simulated business

"Panadería La Espiga", a small bakery.  Covering **2025-01 to 2026-08** (20 months, 1,088 transactions).

## Installation

Requires **Python 3.10+**. No database server and no API key: the SQLite file is
built automatically on first run from the two bundled SQL scripts.

```bash
git clone https://github.com/JuanDsm04/mcp-finanzas-pyme.git
cd mcp-finanzas-pyme

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -e .
```

Verify it starts:

```bash
python -m finanzas_mcp.server --help
```

> The dependency is pinned to `mcp>=1.27,<2`. The MCP Python SDK v2 renamed
> `FastMCP` to `MCPServer` and changed several public field names; an unpinned
> install picks up 2.x and fails at import.

Running `python -m finanzas_mcp.server` by hand just blocks: it is waiting for
JSON-RPC messages on stdin. That is expected — the host is what launches it.

## Connecting it to a host

**Any MCP host** (generic stdio entry). Once the package is installed in the
environment the host launches, no working directory or `PYTHONPATH` is needed:

```json
{
  "command": "python",
  "args": ["-m", "finanzas_mcp.server"]
}
```

**Claude Desktop:** add to `claude_desktop_config.json`, using an absolute
interpreter path since it does not inherit your shell's virtual environment:

```json
{
  "mcpServers": {
    "finanzas-pyme": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "finanzas_mcp.server"]
    }
  }
}
```

**MCP Inspector:** `npx @modelcontextprotocol/inspector python -m finanzas_mcp.server`

## Usage

Questions a user can ask in plain language, and the tool that answers them:

| You ask | The model calls |
|---------|-----------------|
| "¿Cuánto gasté en agosto?" | `desglose_gastos(mes="2026-08")` |
| "¿En qué se me fue el dinero el mes pasado?" | `desglose_gastos()` |
| "¿Mis ventas están subiendo o bajando?" | `tendencia_ingresos()` |
| "¿Gané dinero en marzo?" | `estado_resultados(mes="2026-03")` |
| "¿Me va a alcanzar el próximo mes? Tengo Q45,000" | `proyeccion_flujo_caja(meses=1, saldo_inicial=45000)` |
| "¿Hubo algún gasto raro este año?" | `detectar_gastos_atipicos()` |
| "¿Cómo va mi negocio?" | `salud_financiera()` |


## Configuration

| Variable / flag | Default | Purpose |
|-----------------|---------|---------|
| `FINANZAS_DB_PATH` | `data/finanzas.db` | Where the SQLite file lives |
| `--db-path PATH` | — | Same, as a flag (takes precedence) |
| `--rebuild` | off | Delete and rebuild the database before starting |

## Server specification

### Identity and transport

| Field | Value |
|-------|-------|
| Server name | `finanzas-pyme` |
| Implementation | `finanzas-mcp` 0.1.0 |
| Protocol | Model Context Protocol over JSON-RPC 2.0 |
| Transport | stdio (the host launches the server as a subprocess) |
| Launch command | `python -m finanzas_mcp.server` |
| SDK | MCP Python SDK v1 (`mcp>=1.27,<2`), `FastMCP` |

Capabilities advertised at `initialize`:

```json
{
  "tools":     { "listChanged": false },
  "resources": { "subscribe": false, "listChanged": false },
  "prompts":   { "listChanged": false }
}
```

The server also returns an `instructions` string telling the host that amounts
are in GTQ, that months use `YYYY-MM`, and that omitting the month selects the
latest month with data. It writes nothing to stdout, since on the stdio transport
stdout is the protocol channel; diagnostics go to stderr.

### Tools

**`desglose_gastos`** — breaks one month's expenses down by category.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mes` | `string \| null` | `null` | Month, `YYYY-MM`. Null = latest month with data. |
| `incluir_comparacion` | `boolean` | `true` | Add comparison vs previous month and 3-month average. |

Returns the total and movement count; the fixed/variable split; a table per
category with amount, share, movements and a bar; optionally the comparison
block; the top 5 suppliers; the top 5 individual movements. Errors on a
malformed month or a month outside the available period.

**`tendencia_ingresos`** — analyses whether income is growing or shrinking.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mes` | `string \| null` | `null` | Last month of the window, `YYYY-MM`. |
| `meses` | `integer` | `6` | Window size, 3 to 24. |

Returns the month-over-month change; the year-over-year comparison when 12
months of history exist; the least-squares trend with slope per month, slope as
a percentage of the window average, and **R²** with a reliability label (`alta`
≥ 0.7, `media` ≥ 0.4, `baja` below). When R² < 0.4 it explicitly warns that the
slope is indicative, not predictive. Errors when `meses` is outside 3..24 or
there are fewer than 3 months of history.

**`proyeccion_flujo_caja`** — projects income, expenses and cash balance.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `meses` | `integer` | `1` | Months to project, 1 to 6. |
| `saldo_inicial` | `number \| null` | `null` | Cash on hand in GTQ. Null = use the accumulated result of the last 6 months as a proxy (stated in the output). |
| `ventana` | `integer` | `6` | Trailing months used to fit, 3 to 18. |

Method, printed in the output so it is auditable:

1. **Income** — least squares over the last `ventana` months, extrapolated, then
   multiplied by the seasonal index of the target calendar month, damped by 0.5
   because the history is short.
2. **Fixed costs** — per category as `level × seasonal_index`, where the level is
   the mean of the trailing window over a zero-filled series and the index is not
   damped.
3. **Variable costs** — the median share of income they absorbed over the window,
   applied to projected income.

Returns a table per projected month (income, fixed, variable, net flow, running
balance); the composition of the first month's fixed costs; a verdict — `SI`
(covers everything), `AJUSTADO` (covers fixed but not variable), or `NO`; the
coverage ratio, runway in months, lowest projected balance; and a warning that
the projection ignores commitments not present in the data. Errors on `meses`
outside 1..6, `ventana` outside 3..18, or a negative `saldo_inicial`.

**`estado_resultados`** — profit-and-loss statement for one month.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mes` | `string \| null` | `null` | Month, `YYYY-MM`. |

Returns income by category with shares; expenses by category tagged fixed or
variable, each as a percentage of income; subtotals; net profit or loss and net
margin; the previous month for reference.

**`detectar_gastos_atipicos`** — flags months where a category deviates from its
own norm.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `meses` | `integer` | `12` | Trailing months to inspect, minimum 3. |
| `umbral_z` | `number` | `2.0` | Minimum absolute z-score to report. |

For each expense category with at least four observations in the window, monthly
totals are converted to standard scores against that category's own mean and
population standard deviation. Returns a table sorted by |z| plus the individual
transactions explaining the three largest deviations. When nothing exceeds the
threshold it says so and suggests a lower one. Errors on `meses` < 3 or
`umbral_z` ≤ 0.

**`salud_financiera`** — one-screen snapshot. No parameters. Returns the latest
closed month and available history; 6-month averages for income, expenses and
result; average net margin; average fixed costs and coverage ratio; payroll cost
and its weight over income; loss-making months in the last year; the active
roster.

### Resources

| URI | MIME type | Content |
|-----|-----------|---------|
| `finanzas://esquema` | `text/plain` | The complete DDL (5 tables and the monthly view) |
| `finanzas://catalogo/categorias` | `text/plain` | `nombre\|tipo\|es_fijo\|descripcion` |
| `finanzas://meses` | `text/plain` | Months with data, one per line |

### Prompts

**`revision_mensual`** (`mes: string`, default `""` = latest month) renders a
reusable instruction that walks the model through a full monthly review: income
statement, expense breakdown, income trend, anomaly detection, then three
conclusions and one actionable recommendation in plain language.

### Data model

```
categorias(id, nombre, tipo, es_fijo, descripcion)
proveedores(id, nombre, categoria_id -> categorias, dias_credito, activo)
clientes(id, nombre, segmento, fecha_alta, activo)
empleados(id, nombre, puesto, salario_mensual, fecha_ingreso, fecha_salida, activo)
transacciones(id, fecha, tipo, monto, categoria_id -> categorias,
              proveedor_id -> proveedores, cliente_id -> clientes,
              metodo_pago, descripcion)

v_resumen_mensual: monthly totals per category
```

`categorias.tipo` and `transacciones.tipo` are both constrained to
`'ingreso' | 'gasto'`; `categorias.es_fijo` is the flag the projection depends
on; `transacciones.monto` must be positive, with direction carried by `tipo`.
Indexes exist on `fecha`, `(tipo, fecha)` and `(categoria_id, fecha)`, the three
access patterns every tool uses.

The database is built on first use into `data/finanzas.db` via a temporary file
that is renamed on success, so a crash mid-import cannot leave a half-populated
database.

### Security notes

Every SQL statement is parameterised; no tool interpolates model-provided strings
into SQL. The server is read-only — no tool writes to the ledger. The database is
local and synthetic: no network access, no credentials, no personal data.

## Regenerating the dataset

`seed.sql` is generated, not hand-written. The generator is deterministic, so
re-running it reproduces the same file:

```bash
python scripts/generate_seed.py
rm -f data/finanzas.db          # rebuilt automatically on the next run
```

To change the simulated business, edit the constants at the top of
[`scripts/generate_seed.py`](scripts/generate_seed.py): period, categories,
suppliers, customers, payroll, seasonality, growth rate and planted anomalies.

## Project structure

```
mcp-finanzas-pyme/
├── src/finanzas_mcp/
│   ├── schema.sql          DDL: 5 tables + 1 view
│   ├── seed.sql            DML: generated, 1,088 transactions
│   ├── db.py               SQLite access; builds the database on first use
│   ├── analytics.py        Trend, seasonality, projection, z-scores
│   ├── formatting.py       Text rendering helpers
│   ├── errors.py           ToolInputError
│   ├── tools/
│   │   ├── gastos_por_categoria.py   desglose_gastos, detectar_gastos_atipicos
│   │   ├── tendencia_ingresos.py     tendencia_ingresos, estado_resultados
│   │   └── proyeccion_flujo.py       proyeccion_flujo_caja, salud_financiera
│   └── server.py           MCP registration + stdio entry point
├── scripts/generate_seed.py
└── docs/ejemplos.md        Worked examples with real output
```

The layering is deliberate: `analytics.py` knows nothing about SQL, the tools
know nothing about MCP, and `server.py` is a thin registration wrapper.

## References

* [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
* [MCP specification](https://modelcontextprotocol.io/specification/2025-06-18)
* [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
* [JSON-RPC 2.0](https://www.jsonrpc.org/)