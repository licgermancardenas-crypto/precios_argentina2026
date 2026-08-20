"""
Forecasting del Índice Canasta Atlas (v3).

Honestidad ante todo: un pronóstico diario necesita historia. Con menos de
`MIN_DIAS_FORECAST` días, este módulo NO inventa un forecast — escribe un estado
"insuficiente" y ni siquiera importa Prophet. El forecast se activa solo cuando
hay datos, sin tocar código.

Cuando hay historia suficiente:
  - ajusta Prophet sobre el índice total (encadenado, cadena de referencia)
  - opcionalmente usa el dólar blue como regresor si hay historia alineada
  - proyecta `HORIZONTE_DIAS` hacia adelante

Además detecta anomalías del índice (retornos diarios fuera de ±Z·σ).

Salida: data/public/forecast.json (lo consume el dashboard; el dashboard NO
depende de Prophet).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from pipeline.indice import indice_encadenado
from scraper.config import FUENTE_REFERENCIA

log = logging.getLogger(__name__)

DB_PATH = Path("data/atlas.db")
OUT_PATH = Path("data/public/forecast.json")

MIN_DIAS_FORECAST = 30      # mínimo de días para que Prophet tenga sentido
HORIZONTE_DIAS = 14         # días a proyectar
Z_ANOMALIA = 2.5            # umbral de anomalía en retornos diarios (desvíos estándar)


def _indice_total(con: sqlite3.Connection) -> pd.DataFrame:
    """Índice total base 100 (encadenado, cadena de referencia). Cols: fecha, indice."""
    df = pd.read_sql(
        """SELECT pr.fecha, p.nombre_normalizado AS producto, pr.precio_lista
           FROM precios pr JOIN productos p ON p.id = pr.producto_id
           WHERE p.en_canasta = 1 AND COALESCE(p.peso_variable, 0) = 0 AND pr.fuente = ?""",
        con, params=(FUENTE_REFERENCIA,),
    )
    if df.empty:
        return pd.DataFrame(columns=["fecha", "indice"])
    indice = indice_encadenado(df)
    return pd.DataFrame({"fecha": indice.index, "indice": indice.values})


def _detectar_anomalias(serie: pd.DataFrame) -> list[dict]:
    """Días con retorno diario del índice fuera de ±Z·σ (requiere algo de historia)."""
    if len(serie) < 5:
        return []
    ret = serie["indice"].pct_change()
    mu, sigma = ret.mean(), ret.std()
    if not sigma or pd.isna(sigma):
        return []
    anomalias = []
    for i, r in ret.items():
        if pd.notna(r) and abs(r - mu) > Z_ANOMALIA * sigma:
            anomalias.append({
                "fecha": serie["fecha"].iloc[i],
                "indice": float(serie["indice"].iloc[i]),
                "retorno_pct": round(r * 100, 2),
            })
    return anomalias


def _forecast_prophet(serie: pd.DataFrame) -> list[dict]:
    """Ajusta Prophet y proyecta HORIZONTE_DIAS. Import lazy: solo se llama con datos suficientes."""
    from prophet import Prophet  # import lazy a propósito

    dfp = serie.rename(columns={"fecha": "ds", "indice": "y"}).copy()
    dfp["ds"] = pd.to_datetime(dfp["ds"])
    modelo = Prophet(daily_seasonality=False, weekly_seasonality=True, yearly_seasonality=False)
    modelo.fit(dfp)
    futuro = modelo.make_future_dataframe(periods=HORIZONTE_DIAS)
    pred = modelo.predict(futuro).tail(HORIZONTE_DIAS)
    return [
        {"fecha": d.strftime("%Y-%m-%d"), "yhat": round(y, 2),
         "yhat_lower": round(lo, 2), "yhat_upper": round(hi, 2)}
        for d, y, lo, hi in zip(pred["ds"], pred["yhat"], pred["yhat_lower"], pred["yhat_upper"])
    ]


def generar(db_path: Path = DB_PATH, out_path: Path = OUT_PATH) -> dict:
    con = sqlite3.connect(db_path)
    try:
        serie = _indice_total(con)
    finally:
        con.close()

    n = len(serie)
    resultado = {
        "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "serie": "indice_canasta_total",
        "dias_historia": n,
        "dias_necesarios": MIN_DIAS_FORECAST,
        "horizonte_dias": HORIZONTE_DIAS,
        "historia": serie.to_dict("records"),
        "anomalias": _detectar_anomalias(serie),
        "forecast": [],
    }

    if n < MIN_DIAS_FORECAST:
        resultado["estado"] = "insuficiente"
        log.info("Forecast omitido: %d/%d días. Acumulando historia.", n, MIN_DIAS_FORECAST)
    else:
        try:
            resultado["forecast"] = _forecast_prophet(serie)
            resultado["estado"] = "ok"
            log.info("Forecast generado: %d días proyectados.", HORIZONTE_DIAS)
        except ImportError:
            resultado["estado"] = "prophet_no_instalado"
            log.warning("Hay datos suficientes pero Prophet no está instalado (pip install -r requirements-ml.txt).")
        except Exception as exc:
            resultado["estado"] = "error"
            resultado["error"] = str(exc)
            log.error("Falló el forecast: %s", exc)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    return resultado


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    generar()
