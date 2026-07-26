"""
Ingesta de regresores externos (v3): series que ayudan a explicar/pronosticar
la inflación de la canasta.

Series:
  - dólar oficial y blue (dolarapi.com, diario)
  - IPC Nivel General Nacional de INDEC (mensual, API de series de datos.gob.ar)

El dólar guarda el valor del día; el IPC se backfillea (últimos meses) porque es
mensual y se publica con rezago. Idempotente: INSERT OR IGNORE por (fecha, serie).
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

# IPC Nivel General Nacional (base dic 2016) — API de Series de Tiempo de datos.gob.ar
_IPC_SERIE_ID = "148.3_INIVELNAL_DICI_M_26"
_IPC_URL = ("https://apis.datos.gob.ar/series/api/series/"
            f"?ids={_IPC_SERIE_ID}&limit=36&sort=desc&format=json")


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


def _fetch_ipc() -> list[tuple[str, float]]:
    """Retorna [(fecha_mensual, valor_indice)] del IPC Nivel General (últimos meses)."""
    req = urllib.request.Request(_IPC_URL, headers={"User-Agent": "atlas-precios/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read())
    return [(row[0], float(row[1])) for row in payload.get("data", []) if row[1] is not None]


def ingestar(db_path: Path = DB_PATH, fecha: str | None = None) -> None:
    fecha = fecha or date.today().isoformat()
    con = sqlite3.connect(db_path)
    try:
        _asegurar_tabla(con)

        # Dólar (valor del día)
        try:
            dolar = _fetch_dolar()
            with con:
                for serie, valor in dolar.items():
                    con.execute(
                        "INSERT OR IGNORE INTO regresores (fecha, serie, valor) VALUES (?, ?, ?)",
                        (fecha, serie, valor),
                    )
            log.info("Dólar %s: %s", fecha, dolar)
        except Exception as exc:
            log.error("No se pudo obtener el dólar: %s", exc)

        # IPC (mensual, backfill de los últimos meses)
        try:
            ipc = _fetch_ipc()
            with con:
                nuevos = con.executemany(
                    "INSERT OR IGNORE INTO regresores (fecha, serie, valor) VALUES (?, 'ipc', ?)",
                    ipc,
                ).rowcount
            ultimo = max(ipc)[0] if ipc else "N/A"
            log.info("IPC: %d meses (último %s), %d nuevos", len(ipc), ultimo, nuevos)
        except Exception as exc:
            log.error("No se pudo obtener el IPC: %s", exc)
    finally:
        con.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    ingestar()
