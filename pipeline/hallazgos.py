"""
Hallazgos publicables de Atlas Precios.

Dos tipos de hallazgo, sobre datos limpios:
  - Dispersión de precios: el mismo producto (match por EAN) cuesta muy distinto
    según la cadena. Se calcula sobre la fecha con mayor cobertura, para productos
    con precio en >=2 cadenas.
  - Eventos: reduflación y cambios de presentación detectados por el pipeline (solo
    cadena de referencia, deduplicados — sin el ruido cross-cadena).

Genera data/public/hallazgos.json.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

DB_PATH = Path("data/atlas.db")
OUT_PATH = Path("data/public/hallazgos.json")


def _dispersion(con: sqlite3.Connection) -> dict:
    df = pd.read_sql(
        """SELECT pr.fecha, pr.fuente, pr.precio_lista,
                  p.nombre_original AS producto, p.categoria, p.ean
           FROM precios pr JOIN productos p ON p.id = pr.producto_id
           WHERE p.en_canasta = 1""", con)
    if df.empty:
        return {}

    # Fecha con mayor cobertura de cadenas
    cad = df.groupby("fecha")["fuente"].nunique()
    fecha = cad[cad == cad.max()].index.max()
    d = df[df["fecha"] == fecha]

    piv = d.pivot_table(index=["producto", "categoria"], columns="fuente", values="precio_lista")
    # Productos con precio en >=2 cadenas
    piv = piv[piv.notna().sum(axis=1) >= 2]
    if piv.empty:
        return {"fecha": fecha, "n_productos": 0, "top": []}

    minimo = piv.min(axis=1)
    maximo = piv.max(axis=1)
    disp = ((maximo / minimo - 1) * 100).round(1)
    barata = piv.idxmin(axis=1)
    cara = piv.idxmax(axis=1)

    tabla = pd.DataFrame({
        "producto": [i[0] for i in piv.index],
        "categoria": [i[1] for i in piv.index],
        "precio_min": minimo.values, "precio_max": maximo.values,
        "dispersion_pct": disp.values,
        "mas_barata": barata.values, "mas_cara": cara.values,
    }).sort_values("dispersion_pct", ascending=False)

    return {
        "fecha": fecha,
        "n_productos": int(len(tabla)),
        "dispersion_media_pct": round(float(disp.mean()), 1),
        "dispersion_maxima_pct": round(float(disp.max()), 1),
        "top": tabla.head(15).to_dict("records"),
    }


def _eventos(con: sqlite3.Connection) -> list[dict]:
    df = pd.read_sql(
        """SELECT e.fecha, e.tipo, p.nombre_original AS producto, e.detalle
           FROM eventos e JOIN productos p ON p.id = e.producto_id
           WHERE e.tipo IN ('reduflacion', 'cambio_presentacion', 'outlier')
           ORDER BY e.fecha DESC""", con)
    return df.to_dict("records")


def generar(db_path: Path = DB_PATH, out_path: Path = OUT_PATH) -> dict:
    con = sqlite3.connect(db_path)
    try:
        dispersion = _dispersion(con)
        eventos = _eventos(con)
    finally:
        con.close()

    resultado = {
        "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dispersion": dispersion,
        "eventos": eventos,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Hallazgos: %d productos con dispersión (máx %.1f%%), %d eventos",
             dispersion.get("n_productos", 0), dispersion.get("dispersion_maxima_pct", 0), len(eventos))
    return resultado


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    generar()
