"""
Scraper de Coto Digital via Constructor.io API.
No requiere Playwright — es una API HTTP pura, más estable que parsear HTML.
Busca cada producto de la Canasta Atlas por nombre y fija el EAN en el primer run.
"""

from __future__ import annotations

import json
import logging
import random
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from scraper.config import CANASTA, DELAY_MAX_SEG, DELAY_MIN_SEG, USER_AGENT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")

# API key pública de Constructor.io embebida en el JS del sitio
_CNSTRC_KEY = "key_r6xzz4IAoTWcipni"
_SEARCH_URL  = "https://ac.cnstrc.com/search/{query}?key={key}&num_results_per_page=5&section=Products"


def _delay() -> None:
    time.sleep(random.uniform(DELAY_MIN_SEG, DELAY_MAX_SEG))


def _buscar_producto(nombre_ref: str) -> list[dict]:
    """Llama a la API de Constructor.io y retorna los resultados crudos."""
    query = urllib.parse.quote(nombre_ref)
    url = _SEARCH_URL.format(query=query, key=_CNSTRC_KEY)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Referer": "https://www.coto.com.ar/",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data.get("response", {}).get("results", [])


def _extraer_precio_promo(discounts: list[dict]) -> float | None:
    """
    Extrae precio promocional si existe descuento directo de precio.
    Ignora promos condicionales (2do 70%, cuotas sin interés, etc.).
    """
    for d in discounts:
        texto = d.get("discountText") or ""
        precio_str = d.get("discountPrice") or ""
        # Solo tomamos descuentos con porcentaje directo (ej: "25%Dto")
        if "Dto" in texto or "dto" in texto:
            try:
                limpio = precio_str.replace("$", "").replace(".", "").replace(",", ".")
                return float(limpio)
            except ValueError:
                pass
    return None


def _parsear_resultado(raw: dict, categoria: str, nombre_ref: str) -> dict:
    """Convierte un resultado de la API al formato del snapshot crudo."""
    d = raw.get("data", {})

    precio_lista = d.get("product_list_price")
    precio_promo = _extraer_precio_promo(d.get("discounts", []))

    # precio_unitario: si el producto se vende por kg/l, calculamos $/unidad
    formato_qty = d.get("product_format_quantity") or 1
    unidad = (d.get("product_unit_of_measure") or "").upper()
    precio_unitario = None
    if precio_lista and formato_qty and unidad in ("KG", "LT", "L"):
        precio_unitario = round(precio_lista / float(formato_qty), 2)

    return {
        "nombre_original":     d.get("sku_display_name") or d.get("sku_description"),
        "nombre_ref":          nombre_ref,
        "categoria":           categoria,
        "ean":                 d.get("product_main_ean"),
        "sku_plu":             d.get("sku_plu"),
        "marca":               d.get("product_brand"),
        "formato":             d.get("product_format"),
        "formato_qty":         formato_qty,
        "unidad_medida":       unidad,
        "precio_lista":        precio_lista,
        "precio_promo":        precio_promo,
        "precio_unitario":     precio_unitario,
        "precios_por_sucursal": [
            {"sucursal": p["store"], "precio": p["listPrice"]}
            for p in d.get("price", [])
        ],
        "imagen_url":          d.get("product_large_image_url"),
        "url_producto":        f"https://www.coto.com.ar/{d.get('url', '')}",
        "disponible_sucursales": d.get("store_availability", []),
    }


def _buscar_por_ean(ean: str) -> dict | None:
    """Busca un producto por EAN exacto via Constructor.io."""
    resultados = _buscar_producto(ean)
    for r in resultados:
        if str(r.get("data", {}).get("product_main_ean")) == str(ean):
            return r
    return None


def correr_scraper() -> Path:
    """
    Punto de entrada principal.
    Busca cada producto de la Canasta Atlas y guarda el snapshot crudo del día.
    """
    hoy = date.today().isoformat()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    destino = RAW_DIR / f"{hoy}.json"

    if destino.exists():
        log.info("Ya existe snapshot para hoy (%s), saliendo.", hoy)
        return destino

    resultados: list[dict] = []
    errores: list[dict] = []

    for item in CANASTA:
        nombre_ref = item["nombre_ref"]
        categoria  = item["categoria"]
        ean_fijado = item.get("ean")

        log.info("Buscando: %s (EAN fijado: %s)", nombre_ref, ean_fijado or "ninguno")

        try:
            # Si ya tenemos EAN, buscamos por EAN para máxima precisión
            raw = None
            if ean_fijado:
                raw = _buscar_por_ean(str(ean_fijado))

            # Fallback: búsqueda por nombre
            if not raw:
                candidatos = _buscar_producto(nombre_ref)
                raw = candidatos[0] if candidatos else None

            if raw:
                producto = _parsear_resultado(raw, categoria, nombre_ref)
                resultados.append(producto)
                log.info(
                    "  OK → %s | EAN: %s | Precio: $%s",
                    producto["nombre_original"],
                    producto["ean"],
                    producto["precio_lista"],
                )
            else:
                log.warning("  SIN RESULTADO para: %s", nombre_ref)
                errores.append({"nombre_ref": nombre_ref, "motivo": "sin_resultado"})

        except Exception as exc:
            log.error("  ERROR en '%s': %s", nombre_ref, exc)
            errores.append({"nombre_ref": nombre_ref, "motivo": str(exc)})

        _delay()

    snapshot = {
        "fecha":          hoy,
        "fuente":         "coto",
        "total_ok":       len(resultados),
        "total_errores":  len(errores),
        "errores":        errores,
        "productos":      resultados,
    }

    destino.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(
        "Snapshot guardado: %s (%d productos, %d errores)",
        destino, len(resultados), len(errores),
    )
    return destino


if __name__ == "__main__":
    correr_scraper()
