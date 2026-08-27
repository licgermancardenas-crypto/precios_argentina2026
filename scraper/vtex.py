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


# IVA general argentino. Jumbo publica su ListPrice neto de IVA y en centavos,
# así que recuperar el precio de góndola es multiplicar por esto y dividir por 100.
IVA = 1.21

# Un precio regular no puede estar por debajo del efectivo ni ser un múltiplo
# desmedido: por encima de 3x es un error de unidad, no un descuento. El techo
# deja afuera rebajas de más del 66%, que en supermercado no existen.
_TOPE_REGULAR = 3


def _precio_regular(oferta: dict, precio_venta: float) -> float:
    """
    Precio regular (pre-descuento) de una oferta VTEX.

    `ListPrice` viene en dos codificaciones distintas según el ítem, y no según
    la cadena. La mayoría de Jumbo lo publica **neto de IVA y en centavos**
    —Price = ListPrice / 100 * 1.21, con el factor 82.645 clavado en 37 de 39
    productos de la canasta—, mientras que Día, Carrefour y algunos ítems del
    propio Jumbo lo mandan en pesos, directo.

    Antes se leía el 82.645 como corrupción y se caía a `PriceWithoutDiscount`,
    que en Jumbo replica el precio efectivo. Eso hacía que **el precio con
    descuento se registrara como precio de lista**: exactamente el tipo de
    contaminación que el índice evita al no usar nunca el promo. Hoy hay al
    menos un producto así (EAN 7790199000013: regular $1259,27 vendido a $1150).

    Decodificar a ciegas rompería el caso inverso —un ítem de Jumbo con
    ListPrice ya en pesos pasaría de $112,39 a $1,36—, así que se prueban las
    dos lecturas y se acepta la que caiga en el rango plausible. Las dos nunca
    califican a la vez: los rangos que las validan son disjuntos.
    """
    candidatos = []
    list_price = oferta.get("ListPrice")
    if list_price:
        candidatos.append(float(list_price))              # en pesos, directo
        candidatos.append(float(list_price) / 100 * IVA)  # neto de IVA, en centavos
    sin_descuento = oferta.get("PriceWithoutDiscount")
    if sin_descuento:
        candidatos.append(float(sin_descuento))

    plausibles = [c for c in candidatos if precio_venta <= c <= precio_venta * _TOPE_REGULAR]
    # Sin ninguna lectura creíble, el efectivo es el mejor dato disponible: se
    # asume que no hay descuento antes que inventar un regular.
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
