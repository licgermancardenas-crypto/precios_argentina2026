"""
Scraper genérico para cadenas sobre plataforma VTEX (Día, Carrefour, Jumbo, ...).

Usa la API pública `catalog_system/pub/products/search`:
  - por EAN exacto:  ?fq=alternateIds_Ean:<ean>   (máxima precisión, EAN fijado)
  - por texto:       ?ft=<nombre>                  (fallback, primer resultado)

Produce el mismo dict crudo por producto que `scraper.coto`, de modo que el
pipeline de normalización lo procesa sin ramas especiales por cadena.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import date

from scraper.base import delay, guardar_snapshot, raw_path
from scraper.config import CANASTA, USER_AGENT

log = logging.getLogger(__name__)


def _get(url: str) -> list[dict]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _buscar_por_ean(dominio: str, ean: str) -> dict | None:
    url = f"{dominio}/api/catalog_system/pub/products/search?fq=alternateIds_Ean:{ean}"
    for p in _get(url):
        for it in p.get("items", []):
            if str(it.get("ean")) == str(ean):
                return p
    return None


def _buscar_por_texto(dominio: str, texto: str) -> dict | None:
    query = urllib.parse.quote(texto)
    url = f"{dominio}/api/catalog_system/pub/products/search?ft={query}&_from=0&_to=4"
    resultados = _get(url)
    return resultados[0] if resultados else None


def _parsear_producto(prod: dict, categoria: str, nombre_ref: str) -> dict | None:
    """Convierte un producto VTEX al formato del snapshot crudo (shape de coto)."""
    items = prod.get("items") or []
    if not items:
        return None
    it = items[0]
    sellers = it.get("sellers") or []
    if not sellers:
        return None
    oferta = sellers[0].get("commertialOffer", {})

    # 'Price' es el precio efectivo (a pagar). 'ListPrice' es el precio regular "de",
    # pero algunas cadenas (Jumbo) lo devuelven corrupto (>>Price): en ese caso lo
    # descartamos y usamos el precio efectivo como regular.
    precio_venta = oferta.get("Price")
    list_price = oferta.get("ListPrice")
    if not precio_venta:
        return None
    if list_price and list_price <= precio_venta * 3:
        precio_lista = list_price
    else:
        precio_lista = oferta.get("PriceWithoutDiscount") or precio_venta

    # Si el precio efectivo es menor al regular, hay promo real.
    precio_promo = precio_venta if precio_venta < precio_lista else None

    formato_qty = it.get("unitMultiplier") or 1
    unidad = (it.get("measurementUnit") or "").upper()
    precio_unitario = None
    if precio_lista and formato_qty and unidad in ("KG", "LT", "L"):
        precio_unitario = round(precio_lista / float(formato_qty), 2)

    imagenes = it.get("images") or []
    return {
        "nombre_original":       prod.get("productName"),
        "nombre_ref":            nombre_ref,
        "categoria":             categoria,
        "ean":                   it.get("ean"),
        "sku_plu":               it.get("itemId"),
        "marca":                 prod.get("brand"),
        "formato":               it.get("name"),
        "formato_qty":           formato_qty,
        "unidad_medida":         unidad,
        "precio_lista":          precio_lista,
        "precio_promo":          precio_promo,
        "precio_unitario":       precio_unitario,
        "precios_por_sucursal":  [],
        "imagen_url":            imagenes[0].get("imageUrl") if imagenes else None,
        "url_producto":          prod.get("link"),
        "disponible_sucursales": [],
    }


def correr_scraper(fuente: str, dominio: str) -> None:
    """Scrapea la Canasta Atlas en una cadena VTEX y guarda el snapshot del día."""
    hoy = date.today().isoformat()
    if raw_path(fuente, hoy).exists():
        log.info("[%s] Ya existe snapshot para hoy (%s), saliendo.", fuente, hoy)
        return

    resultados: list[dict] = []
    errores: list[dict] = []

    for item in CANASTA:
        nombre_ref = item["nombre_ref"]
        categoria = item["categoria"]
        ean_fijado = item.get("ean")

        log.info("[%s] Buscando: %s (EAN: %s)", fuente, nombre_ref, ean_fijado or "ninguno")
        try:
            prod = None
            if ean_fijado:
                prod = _buscar_por_ean(dominio, str(ean_fijado))
            if not prod:
                prod = _buscar_por_texto(dominio, nombre_ref)

            producto = _parsear_producto(prod, categoria, nombre_ref) if prod else None
            if producto:
                resultados.append(producto)
                log.info("  OK → %s | $%s", producto["nombre_original"], producto["precio_lista"])
            else:
                log.warning("  SIN RESULTADO para: %s", nombre_ref)
                errores.append({"nombre_ref": nombre_ref, "motivo": "sin_resultado"})
        except Exception as exc:
            log.error("  ERROR en '%s': %s", nombre_ref, exc)
            errores.append({"nombre_ref": nombre_ref, "motivo": str(exc)})

        delay()

    guardar_snapshot(fuente, hoy, resultados, errores)
