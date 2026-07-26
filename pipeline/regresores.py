"""
Ingesta de regresores externos (v3): series que ayudan a explicar/pronosticar
la inflación de la canasta.

Hoy: dólar oficial y blue (dolarapi.com, diario). El IPC de INDEC (mensual) se
carga manualmente o por otra fuente cuando esté disponible — la tabla ya lo soporta.

Cada corrida guarda el valor del día en la tabla `regresores` (fecha, serie, valor).
Idempotente: INSERT OR IGNORE por (fecha, serie).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import urllib.request
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

DB_PATH = Path("data/atlas.db")
_DOLAR_URL = "https://dolarapi.com/v1/dolares"

# Casas de dolarapi.com → nombre de serie en la base
_SERIES_DOLAR = {"oficial": "dolar_oficial", "blue": "dolar_blue"}


def _asegurar_tabla(con: sqlite3.Connection) -> None:
    con.execute(
        """CREATE TABLE IF NOT EXISTS regresores (
               fecha TEXT NOT NULL, serie TEXT NOT NULL, valor REAL NOT NULL,
               UNIQUE (fecha, serie))"""
    )


def _fetch_dolar() -> dict[str, float]:
    """Retorna {serie: valor_venta} para las casas de interés."""
    req = urllib.request.Request(_DOLAR_URL, headers={"User-Agent": "atlas-precios/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        casas = json.loads(resp.read())
    out = {}
    for c in casas:
        serie = _SERIES_DOLAR.get(c.get("casa"))
        if serie and c.get("venta"):
            out[serie] = float(c["venta"])
    return out


def ingestar(db_path: Path = DB_PATH, fecha: str | None = None) -> None:
    fecha = fecha or date.today().isoformat()
    con = sqlite3.connect(db_path)
    try:
        _asegurar_tabla(con)
        try:
            valores = _fetch_dolar()
        except Exception as exc:
            log.error("No se pudo obtener el dólar: %s", exc)
            return
        with con:
            for serie, valor in valores.items():
                con.execute(
                    "INSERT OR IGNORE INTO regresores (fecha, serie, valor) VALUES (?, ?, ?)",
                    (fecha, serie, valor),
                )
        log.info("Regresores %s: %s", fecha, valores)
    finally:
        con.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    ingestar()
