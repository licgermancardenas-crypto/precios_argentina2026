"""
Agente de preguntas en lenguaje natural sobre la base de Atlas Precios (v4).

Text-to-SQL: Claude (claude-opus-4-8) recibe el esquema y una tool de SOLO
LECTURA (`consultar_sql`), escribe y ejecuta SELECTs sobre data/atlas.db, y
responde en español citando los números.

Uso:
    export ANTHROPIC_API_KEY=sk-ant-...
    python -m agent.preguntar "¿cuál es la cadena más barata para la canasta?"

Requiere `pip install -r requirements-agent.txt`. El dashboard NO depende de esto.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data/atlas.db")
MODEL = "claude-opus-4-8"

# Solo se permiten consultas de lectura. Guard defensivo además del modo ro de SQLite.
_PROHIBIDO = ("insert", "update", "delete", "drop", "alter", "create",
              "replace", "attach", "detach", "pragma", "vacuum", ";--")

SYSTEM = """\
Sos el analista de datos de "Atlas Precios", un monitor de precios de \
supermercados argentinos. Respondés preguntas consultando una base SQLite de \
solo lectura mediante la tool `consultar_sql`.

Reglas:
- Traducí la pregunta a uno o más SELECT, ejecutalos con `consultar_sql`, y \
respondé en español, claro y conciso, citando los números concretos.
- SOLO consultas de lectura (SELECT / WITH). Nunca modifiques datos.
- Si la pregunta no se puede responder con los datos, decilo con honestidad.
- No inventes cifras: toda cifra debe salir de una consulta.

Esquema (todas las cadenas conviven; filtrá por `fuente` cuando corresponda):

TABLA productos(id, ean, nombre_normalizado, nombre_original, categoria,
  presentacion, contenido_valor, contenido_unidad, en_canasta, activo)
  -- en_canasta=1 son los productos de la Canasta Atlas.

TABLA precios(id, producto_id, fecha 'YYYY-MM-DD', precio_lista, precio_promo,
  precio_unitario, fuente)
  -- fuente ∈ ('coto','dia','carrefour','jumbo'). UNIQUE(producto_id,fecha,fuente).
  -- El índice y el análisis histórico usan precio_lista (precio_promo puede ser NULL).

TABLA eventos(id, producto_id, fecha, tipo, detalle)
  -- tipo ∈ ('outlier','reduflacion','cambio_presentacion',...).

TABLA regresores(fecha, serie, valor)
  -- serie ∈ ('dolar_oficial','dolar_blue',...).

Metodología clave:
- El Índice Canasta Atlas y las series históricas se calculan sobre la cadena \
de referencia 'coto' con precio_lista (canasta fija = productos con serie completa).
- Para comparar precios entre cadenas, uná por producto_id (matchean por EAN) y \
compará el mismo producto. Solo son comparables los productos con precio en las \
cadenas involucradas.
- Los frescos de balanza (queso x kg, pollo, etc.) no matchean entre cadenas.
"""


def _consultar_sql_impl(sql: str) -> str:
    """Ejecuta un SELECT de solo lectura contra la base y devuelve el resultado como texto."""
    limpio = sql.strip().lower()
    if not (limpio.startswith("select") or limpio.startswith("with")):
        return "ERROR: solo se permiten consultas SELECT/WITH."
    if any(tok in limpio for tok in _PROHIBIDO):
        return "ERROR: consulta rechazada (contiene una operación no permitida)."

    try:
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            filas = con.execute(sql).fetchmany(200)
            if not filas:
                return "(sin resultados)"
            cols = filas[0].keys()
            líneas = [" | ".join(cols)]
            for f in filas:
                líneas.append(" | ".join("" if f[c] is None else str(f[c]) for c in cols))
            texto = "\n".join(líneas)
            if len(filas) == 200:
                texto += "\n(resultado truncado a 200 filas)"
            return texto
        finally:
            con.close()
    except sqlite3.Error as exc:
        return f"ERROR de SQL: {exc}"


def preguntar(pregunta: str) -> str:
    """Corre el agente sobre una pregunta y devuelve la respuesta en texto."""
    try:
        import anthropic
        from anthropic import beta_tool
    except ImportError:
        return ("Falta el SDK de Anthropic. Instalá con:\n"
                "  pip install -r requirements-agent.txt")

    @beta_tool
    def consultar_sql(sql: str) -> str:
        """Ejecuta una consulta SQL de SOLO LECTURA (SELECT) sobre la base de Atlas Precios.

        Args:
            sql: Una sentencia SELECT (o WITH ... SELECT) de SQLite.
        """
        print(f"  ⟶ SQL: {sql.strip()}", file=sys.stderr)
        return _consultar_sql_impl(sql)

    try:
        client = anthropic.Anthropic()  # lee ANTHROPIC_API_KEY del entorno
    except Exception as exc:
        return f"No se pudo inicializar el cliente de Anthropic: {exc}"

    if not DB_PATH.exists():
        return f"No existe la base de datos: {DB_PATH}. Corré el pipeline primero."

    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=SYSTEM,
        tools=[consultar_sql],
        messages=[{"role": "user", "content": pregunta}],
    )

    respuesta = ""
    try:
        for message in runner:
            for block in message.content:
                if block.type == "text":
                    respuesta = block.text
    except anthropic.AuthenticationError:
        return "API key inválida o ausente. Exportá ANTHROPIC_API_KEY."
    except anthropic.APIError as exc:
        return f"Error de la API de Anthropic: {exc}"

    return respuesta or "(sin respuesta)"


def main() -> None:
    if len(sys.argv) < 2:
        print('Uso: python -m agent.preguntar "tu pregunta"', file=sys.stderr)
        raise SystemExit(2)
    pregunta = " ".join(sys.argv[1:])
    print(preguntar(pregunta))


if __name__ == "__main__":
    main()
