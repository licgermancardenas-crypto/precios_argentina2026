"""
Utilidades compartidas por todos los scrapers de cadena.

Cada scraper produce el mismo dict crudo por producto y guarda el snapshot en
`data/raw/{fuente}/{fecha}.json`. El pipeline de normalización recorre todas las
cadenas de una fecha y unifica el mismo producto entre cadenas por EAN.
"""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import date
from pathlib import Path

from scraper.config import DELAY_MAX_SEG, DELAY_MIN_SEG

log = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")


def raw_path(fuente: str, fecha: str | None = None) -> Path:
    """Ruta del snapshot crudo de una cadena para una fecha (default: hoy)."""
    fecha = fecha or date.today().isoformat()
    return RAW_DIR / fuente / f"{fecha}.json"


def delay() -> None:
    """Pausa aleatoria entre requests para scraping de baja frecuencia."""
    time.sleep(random.uniform(DELAY_MIN_SEG, DELAY_MAX_SEG))


def guardar_snapshot(
    fuente: str,
    fecha: str,
    resultados: list[dict],
    errores: list[dict],
) -> Path:
    """Escribe el snapshot crudo del día para una cadena y retorna el path."""
    destino = raw_path(fuente, fecha)
    destino.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "fecha":         fecha,
        "fuente":        fuente,
        "total_ok":      len(resultados),
        "total_errores": len(errores),
        "errores":       errores,
        "productos":     resultados,
    }
    destino.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(
        "Snapshot %s guardado: %s (%d productos, %d errores)",
        fuente, destino, len(resultados), len(errores),
    )
    return destino
