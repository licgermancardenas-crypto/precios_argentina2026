"""
Scraper de Coto Digital usando Playwright.
Recorre las categorías definidas en config.py, pagina hasta agotar resultados
y guarda el snapshot crudo del día en data/raw/YYYY-MM-DD.json.
El crudo nunca se modifica: si hay un bug en la normalización, se reprocesa desde acá.
"""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import date
from pathlib import Path

from playwright.sync_api import Browser, Page, sync_playwright

from scraper.config import (
    CATEGORIAS_COTO,
    DELAY_MAX_SEG,
    DELAY_MIN_SEG,
    MAX_REINTENTOS,
    USER_AGENT,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")


def _delay() -> None:
    time.sleep(random.uniform(DELAY_MIN_SEG, DELAY_MAX_SEG))


def _extraer_productos_pagina(page: Page) -> list[dict]:
    """Extrae todos los productos visibles en la página actual de Coto Digital."""
    productos = []
    items = page.query_selector_all(".product-pod")

    for item in items:
        try:
            nombre_el = item.query_selector(".product-pod--name")
            precio_el = item.query_selector(".atg_store_newPrice")
            promo_el  = item.query_selector(".atg_store_productSale")
            sku_el    = item.query_selector("[data-product-id]")
            url_el    = item.query_selector("a.product-pod--name")

            nombre = nombre_el.inner_text().strip() if nombre_el else None
            precio_texto = precio_el.inner_text().strip() if precio_el else None
            promo_texto  = promo_el.inner_text().strip()  if promo_el  else None
            sku          = sku_el.get_attribute("data-product-id") if sku_el else None
            url          = url_el.get_attribute("href") if url_el else None

            if not nombre or not precio_texto:
                continue

            productos.append({
                "nombre_original": nombre,
                "precio_lista_texto": precio_texto,
                "precio_promo_texto": promo_texto,
                "ean_o_sku": sku,
                "url": f"https://www.cotodigital3.com.ar{url}" if url else None,
            })
        except Exception as exc:
            log.warning("Error extrayendo producto: %s", exc)

    return productos


def _scrapear_categoria(page: Page, nombre: str, url: str) -> list[dict]:
    """Scrapea una categoría completa paginando hasta el final."""
    productos: list[dict] = []
    page.goto(url, timeout=60_000)
    _delay()

    pagina_num = 1
    while True:
        log.info("  Categoría '%s' — página %d", nombre, pagina_num)
        nuevos = _extraer_productos_pagina(page)
        productos.extend(nuevos)
        log.info("  → %d productos en esta página (%d total)", len(nuevos), len(productos))

        siguiente = page.query_selector("a.pagination__next:not([disabled])")
        if not siguiente or not nuevos:
            break

        siguiente.click()
        _delay()
        pagina_num += 1

    return [{"categoria": nombre, **p} for p in productos]


def _scrapear_con_reintentos(browser: Browser, nombre: str, url: str) -> list[dict]:
    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()
            resultado = _scrapear_categoria(page, nombre, url)
            context.close()
            return resultado
        except Exception as exc:
            espera = 2 ** intento
            log.warning(
                "Categoría '%s' falló (intento %d/%d): %s — reintentando en %ds",
                nombre, intento, MAX_REINTENTOS, exc, espera,
            )
            time.sleep(espera)
    log.error("Categoría '%s' falló después de %d intentos, se omite.", nombre, MAX_REINTENTOS)
    return []


def correr_scraper() -> Path:
    """
    Punto de entrada principal.
    Retorna el path del archivo JSON crudo generado.
    """
    hoy = date.today().isoformat()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    destino = RAW_DIR / f"{hoy}.json"

    if destino.exists():
        log.info("Ya existe snapshot para hoy (%s), saliendo.", hoy)
        return destino

    todos: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        for cat in CATEGORIAS_COTO:
            log.info("Scrapeando categoría: %s", cat["nombre"])
            productos = _scrapear_con_reintentos(browser, cat["nombre"], cat["url"])
            todos.extend(productos)
            log.info("Categoría '%s' completada: %d productos", cat["nombre"], len(productos))
            _delay()

        browser.close()

    snapshot = {
        "fecha": hoy,
        "fuente": "coto",
        "total_productos": len(todos),
        "productos": todos,
    }

    destino.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Snapshot guardado: %s (%d productos)", destino, len(todos))
    return destino


if __name__ == "__main__":
    correr_scraper()
