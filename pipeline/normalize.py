"""
Pipeline de normalización: lee el snapshot crudo del día y actualiza atlas.db.
Matching principal por EAN (directo de la API — muy confiable).
Detecta reduflación (mismo EAN, precio estable ±2%, contenido baja).
Detecta outliers (variación > 50% en un día).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import unicodedata
from datetime import date
from pathlib import Path

from scraper.config import CANASTA, FUENTE_REFERENCIA

# EAN de los productos que integran la Canasta Atlas. Un producto es de canasta
# solo si su EAN está acá; los sustitutos que devuelven las cadenas cuando no
# stockean el SKU exacto (otro EAN) NO son canasta.
CANASTA_EANS = {str(p["ean"]) for p in CANASTA if p.get("ean")}

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

DB_PATH = Path("data/atlas.db")
RAW_DIR = Path("data/raw")
SCHEMA  = Path("pipeline/schema.sql")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _sin_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def normalizar_nombre(nombre: str) -> str:
    stopwords = {"oferta", "nuevo", "nueva", "promo", "pack", "combo"}
    texto = _sin_tildes(nombre.lower())
    texto = re.sub(r"[^\w\s]", " ", texto)
    return " ".join(t for t in texto.split() if t not in stopwords)


def _unidad_normalizada(raw: str) -> str:
    """Convierte la unidad de la API a formato estándar del schema."""
    mapa = {
        "KG": "kg", "LT": "l", "L": "l",
        "ML": "ml", "G": "g", "UNI": "unidad", "": "unidad",
    }
    return mapa.get((raw or "").upper(), (raw or "").lower())


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
# Upsert de productos
# ---------------------------------------------------------------------------

def _upsert_producto(con: sqlite3.Connection, p: dict, fuente: str = FUENTE_REFERENCIA) -> int:
    """
    Inserta o actualiza un producto. Retorna el producto_id.
    Matching por EAN (primario) o nombre_normalizado (fallback para frescos sin EAN).

    La detección de cambio de presentación solo corre para la cadena de referencia:
    distintas cadenas reportan el contenido de forma distinta (unitMultiplier, balanza),
    lo que dispararía falsos positivos si se comparara cross-cadena.
    """
    ean = str(p["ean"]) if p.get("ean") else None
    nombre_norm = normalizar_nombre(p["nombre_original"])
    contenido_valor = float(p["formato_qty"]) if p.get("formato_qty") else None
    contenido_unidad = _unidad_normalizada(p.get("unidad_medida", ""))

    # Buscar existente
    existente = None
    if ean:
        existente = con.execute("SELECT * FROM productos WHERE ean = ?", (ean,)).fetchone()
    if not existente:
        existente = con.execute(
            "SELECT * FROM productos WHERE nombre_normalizado = ?", (nombre_norm,)
        ).fetchone()

    if existente:
        # Detectar cambio de presentación (reduflación potencial) — solo cadena de
        # referencia, y sin duplicar un evento idéntico ya registrado.
        detalle = f"Contenido: {existente['contenido_valor']} → {contenido_valor} {contenido_unidad}"
        if (
            fuente == FUENTE_REFERENCIA
            and contenido_valor
            and existente["contenido_valor"]
            and contenido_valor != existente["contenido_valor"]
            and not _evento_existe(con, existente["id"], "cambio_presentacion", detalle)
        ):
            con.execute(
                "INSERT INTO eventos (producto_id, fecha, tipo, detalle) VALUES (?, ?, ?, ?)",
                (existente["id"], date.today().isoformat(), "cambio_presentacion", detalle),
            )
        con.execute(
            "UPDATE productos SET nombre_original = ?, activo = 1 WHERE id = ?",
            (p["nombre_original"], existente["id"]),
        )
        return existente["id"]

    en_canasta = 1 if ean in CANASTA_EANS else 0
    cur = con.execute(
        """INSERT INTO productos
           (ean, nombre_normalizado, nombre_original, categoria,
            presentacion, contenido_valor, contenido_unidad, en_canasta)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ean,
            nombre_norm,
            p["nombre_original"],
            p.get("categoria", ""),
            p.get("formato", ""),
            contenido_valor,
            contenido_unidad,
            en_canasta,
        ),
    )
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Detección de anomalías
# ---------------------------------------------------------------------------

def _evento_existe(con: sqlite3.Connection, producto_id: int, tipo: str, detalle: str) -> bool:
    """True si ya existe un evento idéntico (evita duplicados al reprocesar/diario)."""
    return con.execute(
        "SELECT 1 FROM eventos WHERE producto_id=? AND tipo=? AND detalle=? LIMIT 1",
        (producto_id, tipo, detalle),
    ).fetchone() is not None


def _detectar_reduflacion(
    con: sqlite3.Connection,
    producto_id: int,
    fecha: str,
    precio_nuevo: float,
    contenido_nuevo: float | None,
    fuente: str,
) -> None:
    if not contenido_nuevo:
        return
    anterior = con.execute(
        """SELECT p.precio_lista, pr.contenido_valor
           FROM precios p
           JOIN productos pr ON pr.id = p.producto_id
           WHERE p.producto_id = ? AND p.fuente = ? AND p.fecha < ?
           ORDER BY p.fecha DESC LIMIT 1""",
        (producto_id, fuente, fecha),
    ).fetchone()
    if not anterior or not anterior["precio_lista"] or not anterior["contenido_valor"]:
        return

    variacion_precio = abs(precio_nuevo - anterior["precio_lista"]) / anterior["precio_lista"]
    if variacion_precio <= 0.02 and contenido_nuevo < anterior["contenido_valor"]:
        detalle = (
            f"Precio estable ({variacion_precio:.1%}). "
            f"Contenido: {anterior['contenido_valor']} → {contenido_nuevo}"
        )
        if not _evento_existe(con, producto_id, "reduflacion", detalle):
            con.execute(
                "INSERT INTO eventos (producto_id, fecha, tipo, detalle) VALUES (?, ?, ?, ?)",
                (producto_id, fecha, "reduflacion", detalle),
            )
            log.info("REDUFLACION detectada — producto_id=%d: %s", producto_id, detalle)


def _detectar_outlier(
    con: sqlite3.Connection,
    producto_id: int,
    fecha: str,
    precio_nuevo: float,
    fuente: str,
) -> None:
    anterior = con.execute(
        "SELECT precio_lista FROM precios WHERE producto_id = ? AND fuente = ? ORDER BY fecha DESC LIMIT 1",
        (producto_id, fuente),
    ).fetchone()
    if not anterior or not anterior["precio_lista"]:
        return
    variacion = abs(precio_nuevo - anterior["precio_lista"]) / anterior["precio_lista"]
    if variacion > 0.50:
        con.execute(
            "INSERT INTO eventos (producto_id, fecha, tipo, detalle) VALUES (?, ?, ?, ?)",
            (producto_id, fecha, "outlier", f"Variación {variacion:.1%}: {anterior['precio_lista']} → {precio_nuevo}"),
        )
        log.warning("OUTLIER — producto_id=%d: variación %s", producto_id, f"{variacion:.1%}")


# ---------------------------------------------------------------------------
# Cálculo del Índice Canasta Atlas
# ---------------------------------------------------------------------------

def calcular_indice(con: sqlite3.Connection, fecha: str, fuente: str = FUENTE_REFERENCIA) -> float | None:
    """
    Suma los precios de los 26 productos de la canasta para la fecha dada, en una cadena.
    Usa forward fill (último precio conocido, máximo 7 días) si falta alguno.
    """
    productos_canasta = con.execute(
        "SELECT id FROM productos WHERE en_canasta = 1 AND activo = 1"
    ).fetchall()

    if not productos_canasta:
        return None

    suma = 0.0
    faltantes = 0

    for row in productos_canasta:
        pid = row["id"]
        # Busca el último precio en los últimos 7 días (forward fill), dentro de la cadena
        precio = con.execute(
            """SELECT precio_lista FROM precios
               WHERE producto_id = ? AND fuente = ? AND fecha <= ? AND fecha >= date(?, '-7 days')
               ORDER BY fecha DESC LIMIT 1""",
            (pid, fuente, fecha, fecha),
        ).fetchone()
        if precio:
            suma += precio["precio_lista"]
        else:
            faltantes += 1

    if faltantes > 0:
        log.warning("Índice con %d productos faltantes (forward fill agotado)", faltantes)

    return round(suma, 2)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def _snapshots_de_fecha(fecha: str) -> list[Path]:
    """Todos los snapshots crudos de una fecha, uno por cadena: data/raw/{cadena}/{fecha}.json."""
    return sorted(RAW_DIR.glob(f"*/{fecha}.json"))


def _procesar_snapshot(con: sqlite3.Connection, crudo_path: Path, fecha: str) -> None:
    snapshot = json.loads(crudo_path.read_text(encoding="utf-8"))
    productos_crudos: list[dict] = snapshot.get("productos", [])
    fuente: str = snapshot.get("fuente", "coto")

    log.info("Normalizando %d productos del %s (fuente: %s)", len(productos_crudos), fecha, fuente)
    procesados = 0

    for crudo in productos_crudos:
        if not crudo.get("precio_lista"):
            continue

        producto_id = _upsert_producto(con, crudo, fuente)
        precio_lista = float(crudo["precio_lista"])
        precio_promo = float(crudo["precio_promo"]) if crudo.get("precio_promo") else None
        # Guard de sanidad: un promo válido siempre es menor al precio de lista.
        # Descarta valores absurdos que quedaron en snapshots crudos previos al fix del scraper.
        if precio_promo is not None and not (0 < precio_promo < precio_lista):
            precio_promo = None
        precio_unitario = float(crudo["precio_unitario"]) if crudo.get("precio_unitario") else None

        _detectar_outlier(con, producto_id, fecha, precio_lista, fuente)
        # La reduflación se evalúa solo en la cadena de referencia (evita ruido de
        # contenido reportado distinto entre cadenas).
        if fuente == FUENTE_REFERENCIA:
            _detectar_reduflacion(
                con, producto_id, fecha, precio_lista,
                float(crudo["formato_qty"]) if crudo.get("formato_qty") else None,
                fuente,
            )

        con.execute(
            """INSERT OR IGNORE INTO precios
               (producto_id, fecha, precio_lista, precio_promo, precio_unitario, fuente)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (producto_id, fecha, precio_lista, precio_promo, precio_unitario, fuente),
        )
        procesados += 1

    indice = calcular_indice(con, fecha, fuente)
    log.info(
        "  %s: %d productos | Índice Canasta: $%s",
        fuente, procesados, f"{indice:,.2f}" if indice else "N/A",
    )


def normalizar(fecha: str | None = None) -> None:
    fecha = fecha or date.today().isoformat()
    snapshots = _snapshots_de_fecha(fecha)

    if not snapshots:
        log.error("No existen snapshots crudos para %s en %s", fecha, RAW_DIR)
        return

    con = conectar()
    with con:
        for crudo_path in snapshots:
            _procesar_snapshot(con, crudo_path, fecha)
    con.close()


if __name__ == "__main__":
    import sys
    normalizar(sys.argv[1] if len(sys.argv) > 1 else None)
