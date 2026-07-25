"""
Orquestador de scraping: corre todas las cadenas del registro CADENAS.

  python -m scraper            # todas las cadenas
  python -m scraper coto dia   # solo las indicadas
"""

from __future__ import annotations

import logging
import sys

from scraper import coto, vtex
from scraper.config import CADENAS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main(seleccion: list[str] | None = None) -> None:
    cadenas = [c for c in CADENAS if not seleccion or c["fuente"] in seleccion]
    for cadena in cadenas:
        fuente = cadena["fuente"]
        try:
            if cadena["motor"] == "coto":
                coto.correr_scraper()
            elif cadena["motor"] == "vtex":
                vtex.correr_scraper(fuente, cadena["dominio"])
            else:
                log.error("Motor desconocido para %s: %s", fuente, cadena["motor"])
        except Exception as exc:
            # Una cadena caída no debe tumbar al resto.
            log.error("Cadena %s falló por completo: %s", fuente, exc)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
