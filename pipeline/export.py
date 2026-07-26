"""
Export de datos públicos de Atlas Precios.

Genera archivos versionados en data/public/ que funcionan como API estática
(las URLs raw de GitHub son consumibles por cualquiera):

  precios.csv           serie completa de precios (todas las cadenas)
  indice_canasta.csv    índice base 100 diario: total + 6 categorías (cadena ref)
  comparador.csv        último precio por cadena de cada producto comparable
  metadata.json         esquema, cadenas, fechas, licencia

Metodología del índice: suma del precio_lista de la canasta por día, base 100 en
el primer día (idéntica a la del dashboard). El total y cada categoría se
calculan solo sobre la cadena de referencia.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from scraper.config import FUENTE_REFERENCIA

log = logging.getLogger(__name__)

DB_PATH = Path("data/atlas.db")
OUT_DIR = Path("data/public")


def _leer_precios(con: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql(
        """
        SELECT pr.fecha, pr.fuente, p.categoria, p.ean,
               p.nombre_normalizado AS producto,
               pr.precio_lista, pr.precio_promo
        FROM precios pr
        JOIN productos p ON p.id = pr.producto_id
        WHERE p.en_canasta = 1
        ORDER BY pr.fecha, pr.fuente, p.categoria
        """,
        con,
    )


def _costo_canasta_fija(g: pd.DataFrame) -> pd.Series:
    """
    Costo diario de una canasta FIJA: solo productos con precio todos los días.
    Evita artefactos de composición (un producto que aparece/desaparece no mueve
    el índice). Devuelve una serie fecha → costo.
    """
    piv = g.pivot_table(index="fecha", columns="producto", values="precio_lista").sort_index()
    completos = piv.dropna(axis=1)
    return completos.sum(axis=1)


def _filas_indice(costos: pd.Series, categoria: str) -> list[dict]:
    base = costos.iloc[0]
    return [
        {"fecha": fecha, "categoria": categoria,
         "costo_canasta": round(costo, 2), "indice_base100": round(costo / base * 100, 2)}
        for fecha, costo in costos.items()
    ]


def _construir_indice(df: pd.DataFrame) -> pd.DataFrame:
    """Índice diario total + por categoría (canasta fija, cadena de referencia)."""
    ref = df[df["fuente"] == FUENTE_REFERENCIA]
    filas = _filas_indice(_costo_canasta_fija(ref), "TOTAL")
    for cat, g in ref.groupby("categoria"):
        costos = _costo_canasta_fija(g)
        if not costos.empty:
            filas += _filas_indice(costos, cat)
    return pd.DataFrame(filas).sort_values(["categoria", "fecha"])


def _construir_comparador(df: pd.DataFrame) -> pd.DataFrame:
    """Último precio de cada producto por cadena + cuál es la más barata."""
    ult = (
        df.sort_values("fecha")
        .groupby(["ean", "producto", "categoria", "fuente"], as_index=False)
        .last()
    )
    piv = ult.pivot_table(
        index=["producto", "categoria", "ean"], columns="fuente", values="precio_lista"
    )
    fuentes = list(piv.columns)
    piv["mas_barata"] = piv[fuentes].idxmin(axis=1)
    piv["dif_pct_max"] = (
        (piv[fuentes].max(axis=1) - piv[fuentes].min(axis=1)) / piv[fuentes].min(axis=1) * 100
    ).round(1)
    return piv.reset_index()


def exportar(db_path: Path = DB_PATH, out_dir: Path = OUT_DIR) -> None:
    if not db_path.exists():
        log.error("No existe la base de datos: %s", db_path)
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        precios = _leer_precios(con)
    finally:
        con.close()

    if precios.empty:
        log.error("Sin precios para exportar.")
        return

    indice = _construir_indice(precios)
    comparador = _construir_comparador(precios)

    # Regresores externos (v3): dólar, IPC. Puede no existir aún.
    con = sqlite3.connect(db_path)
    try:
        regresores = pd.read_sql("SELECT fecha, serie, valor FROM regresores ORDER BY fecha, serie", con)
    except Exception:
        regresores = pd.DataFrame(columns=["fecha", "serie", "valor"])
    finally:
        con.close()

    # CSVs
    precios.to_csv(out_dir / "precios.csv", index=False)
    indice.to_csv(out_dir / "indice_canasta.csv", index=False)
    comparador.to_csv(out_dir / "comparador.csv", index=False)
    if not regresores.empty:
        regresores.to_csv(out_dir / "regresores.csv", index=False)

    # JSON del índice (cómodo para consumir desde JS/apps)
    indice.to_json(out_dir / "indice_canasta.json", orient="records", force_ascii=False)

    # Metadata
    fuentes = sorted(precios["fuente"].unique())
    metadata = {
        "proyecto": "Atlas Precios",
        "descripcion": "Serie histórica de precios de canasta de supermercado en Argentina, relevada diariamente.",
        "actualizado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cadenas": fuentes,
        "cadena_referencia_indice": FUENTE_REFERENCIA,
        "fecha_desde": precios["fecha"].min(),
        "fecha_hasta": precios["fecha"].max(),
        "n_dias": int(precios["fecha"].nunique()),
        "n_productos_canasta": int(precios["producto"].nunique()),
        "metodologia_indice": "Suma de precio_lista de la canasta por día, base 100 en el primer día. Total y por categoría sobre la cadena de referencia.",
        "licencia": "CC BY 4.0 — citar 'Atlas Precios'",
        "archivos": {
            "precios.csv": "Serie completa de precios (todas las cadenas).",
            "indice_canasta.csv": "Índice base 100 diario: total + 6 categorías.",
            "indice_canasta.json": "Idem en JSON.",
            "comparador.csv": "Último precio por cadena de cada producto comparable.",
            "regresores.csv": "Series externas: dólar oficial/blue (diario) e IPC INDEC (mensual).",
            "forecast.json": "Proyección del índice (Prophet) + anomalías; estado 'insuficiente' hasta acumular historia.",
            "comparativa_ipc.json": "Índice Canasta vs IPC oficial de INDEC (nowcast del mes en curso + histórico mensual).",
            "hallazgos.json": "Hallazgos publicables: dispersión de precios entre cadenas + eventos (reduflación, cambios de presentación).",
        },
    }
    (out_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    log.info(
        "Export público OK → %s (%d filas precios, %d días, %d cadenas)",
        out_dir, len(precios), metadata["n_dias"], len(fuentes),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    exportar()
