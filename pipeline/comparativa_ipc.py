"""
Contraste Índice Canasta Atlas vs IPC oficial de INDEC (el diferencial del proyecto).

Nuestro índice es diario y en tiempo real; el IPC oficial es mensual y se publica
con ~6 semanas de rezago. Eso convierte a la Canasta Atlas en un *nowcast* de la
inflación: mide el mes en curso antes de que INDEC lo publique.

Genera data/public/comparativa_ipc.json con:
  - mes_en_curso: variación acumulada (parcial) de nuestra canasta en el mes actual
  - ipc_ultimo: último dato oficial disponible
  - mensual: meses completos con ambas cifras (var canasta MoM vs var IPC MoM)

El bloque `mensual` se llena solo a medida que se acumulan meses completos y INDEC
publica — hasta entonces queda vacío y solo se muestra el nowcast.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from pipeline.export import _costo_canasta_fija
from scraper.config import FUENTE_REFERENCIA

log = logging.getLogger(__name__)

DB_PATH = Path("data/atlas.db")
OUT_PATH = Path("data/public/comparativa_ipc.json")


def _indice_diario(con: sqlite3.Connection) -> pd.Series:
    """Índice base 100 diario (canasta fija, cadena de referencia)."""
    df = pd.read_sql(
        """SELECT pr.fecha, p.nombre_normalizado AS producto, pr.precio_lista
           FROM precios pr JOIN productos p ON p.id = pr.producto_id
           WHERE p.en_canasta = 1 AND pr.fuente = ?""",
        con, params=(FUENTE_REFERENCIA,),
    )
    if df.empty:
        return pd.Series(dtype=float)
    costo = _costo_canasta_fija(df)
    costo.index = pd.to_datetime(costo.index)
    return (costo / costo.iloc[0] * 100).round(3)


def _ipc_mensual(con: sqlite3.Connection) -> pd.DataFrame:
    """IPC INDEC con variación mensual. Cols: mes (Period-M str), var_pct."""
    ipc = pd.read_sql("SELECT fecha, valor FROM regresores WHERE serie='ipc' ORDER BY fecha", con)
    if ipc.empty:
        return pd.DataFrame(columns=["mes", "var_pct"])
    ipc["mes"] = pd.to_datetime(ipc["fecha"]).dt.to_period("M").astype(str)
    ipc["var_pct"] = (ipc["valor"].pct_change() * 100).round(2)
    return ipc.dropna(subset=["var_pct"])[["mes", "var_pct"]]


def generar(db_path: Path = DB_PATH, out_path: Path = OUT_PATH) -> dict:
    con = sqlite3.connect(db_path)
    try:
        indice = _indice_diario(con)
        ipc = _ipc_mensual(con)
    finally:
        con.close()

    resultado = {
        "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "nota": ("El IPC oficial de INDEC se publica con ~6 semanas de rezago; "
                 "la Canasta Atlas mide el mes en curso en tiempo real (nowcast)."),
        "mes_en_curso": None,
        "ipc_ultimo": None,
        "mensual": [],
    }

    if indice.empty:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
        return resultado

    # Nowcast: variación acumulada de la canasta en el mes en curso
    periodo = indice.index.to_period("M")
    mes_actual = periodo[-1]
    mes_data = indice[periodo == mes_actual]
    resultado["mes_en_curso"] = {
        "mes": str(mes_actual),
        "estado": "parcial",
        "dias_observados": int(len(mes_data)),
        "desde": mes_data.index[0].strftime("%Y-%m-%d"),
        "var_canasta_pct": round(float(mes_data.iloc[-1] / mes_data.iloc[0] - 1) * 100, 2),
    }

    # Último IPC oficial
    if not ipc.empty:
        u = ipc.iloc[-1]
        resultado["ipc_ultimo"] = {"mes": u["mes"], "var_pct": float(u["var_pct"])}

    # Meses COMPLETOS de nuestra canasta (var MoM sobre valor de fin de mes) vs IPC
    fin_de_mes = indice.groupby(periodo).last()
    var_canasta = (fin_de_mes.pct_change() * 100).round(2).dropna()
    ipc_map = dict(zip(ipc["mes"], ipc["var_pct"])) if not ipc.empty else {}
    for per, var_c in var_canasta.items():
        # Solo meses ya cerrados (no el mes en curso)
        if per == mes_actual:
            continue
        resultado["mensual"].append({
            "mes": str(per),
            "var_canasta_pct": float(var_c),
            "var_ipc_pct": ipc_map.get(str(per)),
        })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Comparativa IPC: nowcast %s %.2f%% | %d meses completos",
             resultado["mes_en_curso"]["mes"], resultado["mes_en_curso"]["var_canasta_pct"],
             len(resultado["mensual"]))
    return resultado


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    generar()
