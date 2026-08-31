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


# Un precio regular no puede estar por debajo del efectivo ni ser un múltiplo
# desmedido: por encima de 3x es un error de unidad, no un descuento. El techo
# deja afuera rebajas de más del 66%, que en supermercado no existen.
_TOPE_REGULAR = 3


def _precio_regular(oferta: dict, precio_venta: float) -> float:
    """
    Precio regular (pre-descuento) de una oferta VTEX.

    Día y Carrefour publican `ListPrice` en pesos: si es mayor al efectivo, hay
    descuento. Jumbo lo publica **neto de IVA y en centavos**, y de ahí el ×80
    que parecía corrupción — el factor es 100 dividido la alícuota.

    **Ese campo no sirve para detectar promos en Jumbo**, y conviene dejarlo
    escrito porque la trampa es sutil. La alícuota varía por producto: 21% en
    general, 10,5% en la canasta básica (harina, carne). Decodificar todo al 21%
    hace que un producto al 10,5% aparezca con un "descuento" de 1,21/1,105 =
    8,68% que no existe. Se probó, y produjo 21 promos falsas por día sobre 45
    productos: 19 por ruido de punto flotante y 2 por la alícuota reducida.
    Sondeados los 39 productos con precio, los 39 decodifican EXACTO al efectivo
    con su alícuota: Jumbo no está ocultando descuentos, no los tiene.

    Así que solo se acepta el `ListPrice` cuando ya viene en pesos y en un rango
    plausible; si no, manda `PriceWithoutDiscount` y, en última instancia, el
    precio efectivo. Asumir que no hay descuento es preferible a inventar uno.
    """
    candidatos = []
    list_price = oferta.get("ListPrice")
    if list_price:
        candidatos.append(float(list_price))
    sin_descuento = oferta.get("PriceWithoutDiscount")
    if sin_descuento:
        candidatos.append(float(sin_descuento))

    plausibles = [c for c in candidatos if precio_venta <= c <= precio_venta * _TOPE_REGULAR]
    return max(plausibles) if plausibles else float(precio_venta)


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

    precio_venta = oferta.get("Price")
    if not precio_venta:
        return None
    precio_lista = _precio_regular(oferta, precio_venta)

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
