"""
Pipeline de normalización: lee el snapshot crudo del día y actualiza atlas.db.
Matching por EAN cuando existe; fallback por nombre normalizado + presentación.
Detecta reduflación (mismo EAN, precio estable ±2%, contenido baja).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import unicodedata
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

DB_PATH  = Path("data/atlas.db")
RAW_DIR  = Path("data/raw")
SCHEMA   = Path("pipeline/schema.sql")

STOPWORDS = {"oferta", "nuevo", "nueva", "promo", "pack", "combo", "x"}
UNIDADES_RE = re.compile(r"(\d+[.,]?\d*)\s*(kg|g|l|ml|cc|un|u)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Utilidades de normalización de texto
# ---------------------------------------------------------------------------

def _sin_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def normalizar_nombre(nombre: str) -> str:
    texto = _sin_tildes(nombre.lower())
    texto = re.sub(r"[^\w\s]", " ", texto)
    tokens = [t for t in texto.split() if t not in STOPWORDS]
    return " ".join(tokens)


def extraer_presentacion(nombre: str) -> tuple[float | None, str | None]:
    """Retorna (valor, unidad) extraídos del nombre del producto."""
    match = UNIDADES_RE.search(nombre)
    if not match:
        return None, None
    valor = float(match.group(1).replace(",", "."))
    unidad = match.group(2).lower()
    return valor, unidad


def parsear_precio(texto: str | None) -> float | None:
    if not texto:
        return None
    limpio = re.sub(r"[^\d,.]", "", texto).replace(",", ".")
    try:
        return float(limpio)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------

def conectar() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    if not _tablas_existen(con):
        _crear_schema(con)
    return con


def _tablas_existen(con: sqlite3.Connection) -> bool:
    cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='precios'")
    return cur.fetchone() is not None


def _crear_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.commit()
    log.info("Schema de base de datos creado.")


# ---------------------------------------------------------------------------
# Matching de productos
# ---------------------------------------------------------------------------

def _buscar_por_ean(con: sqlite3.Connection, ean: str) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM productos WHERE ean = ?", (ean,)).fetchone()


def _buscar_por_nombre(con: sqlite3.Connection, nombre_norm: str) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM productos WHERE nombre_normalizado = ?", (nombre_norm,)
    ).fetchone()


def _upsert_producto(con: sqlite3.Connection, datos: dict) -> int:
    existente = None
    if datos.get("ean"):
        existente = _buscar_por_ean(con, datos["ean"])
    if not existente:
        existente = _buscar_por_nombre(con, datos["nombre_normalizado"])

    if existente:
        con.execute(
            "UPDATE productos SET nombre_original = ?, activo = 1 WHERE id = ?",
            (datos["nombre_original"], existente["id"]),
        )
        return existente["id"]

    cur = con.execute(
        """INSERT INTO productos
           (ean, nombre_normalizado, nombre_original, categoria,
            presentacion, contenido_valor, contenido_unidad)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            datos.get("ean"),
            datos["nombre_normalizado"],
            datos["nombre_original"],
            datos["categoria"],
            datos.get("presentacion"),
            datos.get("contenido_valor"),
            datos.get("contenido_unidad"),
        ),
    )
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Detección de reduflación
# ---------------------------------------------------------------------------

def _detectar_reduflacion(
    con: sqlite3.Connection,
    producto_id: int,
    fecha: str,
    precio_nuevo: float,
    contenido_nuevo: float | None,
) -> None:
    """
    Registra evento 'reduflacion' si el precio es estable (±2%) pero el contenido bajó.
    Es el hallazgo más publicable del proyecto.
    """
    if contenido_nuevo is None:
        return

    anterior = con.execute(
        """SELECT p.precio_lista, pr.contenido_valor
           FROM precios p
           JOIN productos pr ON pr.id = p.producto_id
           WHERE p.producto_id = ? AND p.fecha < ?
           ORDER BY p.fecha DESC LIMIT 1""",
        (producto_id, fecha),
    ).fetchone()

    if not anterior:
        return

    precio_ant = anterior["precio_lista"]
    contenido_ant = anterior["contenido_valor"]

    if not precio_ant or not contenido_ant:
        return

    variacion_precio = abs(precio_nuevo - precio_ant) / precio_ant
    if variacion_precio <= 0.02 and contenido_nuevo < contenido_ant:
        detalle = (
            f"Precio: {precio_ant} → {precio_nuevo} ({variacion_precio:.1%}). "
            f"Contenido: {contenido_ant} → {contenido_nuevo}"
        )
        con.execute(
            "INSERT INTO eventos (producto_id, fecha, tipo, detalle) VALUES (?, ?, ?, ?)",
            (producto_id, fecha, "reduflacion", detalle),
        )
        log.info("REDUFLACION detectada — producto_id=%d: %s", producto_id, detalle)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def normalizar(fecha: str | None = None) -> None:
    fecha = fecha or date.today().isoformat()
    crudo_path = RAW_DIR / f"{fecha}.json"

    if not crudo_path.exists():
        log.error("No existe snapshot crudo para %s: %s", fecha, crudo_path)
        return

    snapshot = json.loads(crudo_path.read_text(encoding="utf-8"))
    productos_crudos: list[dict] = snapshot.get("productos", [])
    fuente: str = snapshot.get("fuente", "coto")

    log.info("Normalizando %d productos del %s (fuente: %s)", len(productos_crudos), fecha, fuente)

    con = conectar()
    procesados = 0

    with con:
        for crudo in productos_crudos:
            nombre_orig = crudo.get("nombre_original", "")
            if not nombre_orig:
                continue

            nombre_norm = normalizar_nombre(nombre_orig)
            contenido_valor, contenido_unidad = extraer_presentacion(nombre_orig)
            precio_lista = parsear_precio(crudo.get("precio_lista_texto"))
            precio_promo = parsear_precio(crudo.get("precio_promo_texto"))

            if precio_lista is None:
                continue

            precio_unitario = (
                precio_lista / contenido_valor
                if contenido_valor and contenido_valor > 0
                else None
            )

            datos = {
                "ean": crudo.get("ean_o_sku"),
                "nombre_normalizado": nombre_norm,
                "nombre_original": nombre_orig,
                "categoria": crudo.get("categoria", ""),
                "presentacion": crudo.get("presentacion"),
                "contenido_valor": contenido_valor,
                "contenido_unidad": contenido_unidad,
            }

            producto_id = _upsert_producto(con, datos)

            # Outlier: variación diaria > 50% se registra para revisión
            anterior_precio = con.execute(
                "SELECT precio_lista FROM precios WHERE producto_id = ? ORDER BY fecha DESC LIMIT 1",
                (producto_id,),
            ).fetchone()
            if anterior_precio and anterior_precio["precio_lista"]:
                variacion = abs(precio_lista - anterior_precio["precio_lista"]) / anterior_precio["precio_lista"]
                if variacion > 0.50:
                    con.execute(
                        "INSERT INTO eventos (producto_id, fecha, tipo, detalle) VALUES (?, ?, ?, ?)",
                        (producto_id, fecha, "outlier", f"Variación {variacion:.1%}"),
                    )

            _detectar_reduflacion(con, producto_id, fecha, precio_lista, contenido_valor)

            con.execute(
                """INSERT OR IGNORE INTO precios
                   (producto_id, fecha, precio_lista, precio_promo, precio_unitario, fuente)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (producto_id, fecha, precio_lista, precio_promo, precio_unitario, fuente),
            )
            procesados += 1

    log.info("Normalización completada: %d productos procesados para %s.", procesados, fecha)


if __name__ == "__main__":
    import sys
    fecha_arg = sys.argv[1] if len(sys.argv) > 1 else None
    normalizar(fecha_arg)
