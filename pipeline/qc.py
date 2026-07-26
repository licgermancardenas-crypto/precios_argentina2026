"""
Control de calidad diario (robustez de datos).

Valida la SALUD DEL RELEVAMIENTO: cuántos productos devolvió el scraper de cada
cadena (desde los snapshots crudos) vs lo esperado, para detectar caídas de una
cadena o de su API. Marca un estado global y escribe data/public/qc.json (queda
versionado como audit trail) y registra warnings.

Se cuentan los productos del crudo, NO los que matchean la canasta por EAN: una
cadena puede no stockear un SKU exacto sin que su scraper haya fallado.

Estados:
  - ok        : todas las cadenas con cobertura >= UMBRAL_OK
  - warning   : alguna cadena por debajo del umbral (pero relevó algo)
  - critical  : una cadena no trajo NADA, o no hay datos para la fecha

El paso de "alerta" del workflow hace fallar el job (y dispara el mail de GitHub)
solo cuando el estado es `critical` — así una caída de una cadena se nota, sin
perder los datos de las que sí funcionaron.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from scraper.config import CANASTA, CADENAS

log = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")
OUT_PATH = Path("data/public/qc.json")

ESPERADO = len(CANASTA)                 # productos que debería relevar cada scraper
UMBRAL_OK = 0.90                        # cobertura mínima sin warning


def _ultima_fecha() -> str | None:
    fechas = [p.stem for p in RAW_DIR.glob("*/*.json")]
    return max(fechas) if fechas else None


def _productos_crudos(fuente: str, fecha: str) -> int | None:
    """Productos que devolvió el scraper de la cadena ese día (None si no hay snapshot)."""
    ruta = RAW_DIR / fuente / f"{fecha}.json"
    if not ruta.exists():
        return None
    snap = json.loads(ruta.read_text(encoding="utf-8"))
    return int(snap.get("total_ok", len(snap.get("productos", []))))


def generar(out_path: Path = OUT_PATH) -> dict:
    ultima = _ultima_fecha()
    esperadas = [c["fuente"] for c in CADENAS]

    cadenas, alertas, estado = {}, [], "ok"
    for f in esperadas:
        crudos = _productos_crudos(f, ultima) if ultima else None
        n = crudos if crudos is not None else 0
        cobertura = round(n / ESPERADO * 100, 1) if ESPERADO else 0.0
        if n == 0:
            est = "critical"; estado = "critical"
            alertas.append(f"{f}: NO relevó ningún producto")
        elif n < ESPERADO * UMBRAL_OK:
            est = "warning"; estado = "critical" if estado == "critical" else "warning"
            alertas.append(f"{f}: relevó {n}/{ESPERADO} ({cobertura:.0f}%)")
        else:
            est = "ok"
        cadenas[f] = {"productos": n, "cobertura_pct": cobertura, "estado": est}

    if not ultima:
        estado = "critical"; alertas.append("Sin datos para ninguna fecha")

    resultado = {
        "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fecha": ultima,
        "esperado_por_cadena": ESPERADO,
        "cadenas": cadenas,
        "estado_global": estado,
        "alertas": alertas,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")

    nivel = {"ok": log.info, "warning": log.warning, "critical": log.error}[estado]
    nivel("QC %s: estado=%s | %s", ultima, estado,
          " · ".join(alertas) if alertas else "todas las cadenas OK")
    return resultado


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    r = generar()
    # Modo alerta: falla el job (mail de GitHub) solo si es crítico.
    if "--alert" in sys.argv and r["estado_global"] == "critical":
        log.error("QC CRÍTICO — ver alertas.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
