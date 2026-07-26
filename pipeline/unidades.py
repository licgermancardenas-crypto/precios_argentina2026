"""
Normalización de precio por unidad ($/kg, $/L, $/unidad).

Los scrapers no extraen el contenido real (contenido_valor queda en 1.0). El
tamaño vive en el texto, así que se parsea desde la `presentacion` del config
(controlada, una por producto de canasta) y se calcula el precio por unidad base.

Bases: kg (masa), L (volumen), un (conteo).
"""

from __future__ import annotations

import re

from scraper.config import CANASTA


def parse_presentacion(s: str | None) -> tuple[float, str]:
    """Extrae (cantidad_en_base, unidad_base) de una presentación. base ∈ {kg, L, un}."""
    if not s:
        return (1.0, "un")
    t = s.lower().replace(",", ".")
    if "por kg" in t or "xkg" in t or "x kg" in t:
        return (1.0, "kg")
    m = re.search(r"(\d+(?:\.\d+)?)", t)
    val = float(m.group(1)) if m else 1.0
    if re.search(r"\b(kg|kilo)", t):
        return (val, "kg")
    if re.search(r"\b(g|gr|grs|gramos)\b", t):
        return (val / 1000, "kg")
    if re.search(r"\b(l|lt|lts|litro)\b", t):
        return (val, "L")
    if re.search(r"(ml|cc)\b", t):
        return (val / 1000, "L")
    return (val, "un")


# EAN → presentación (de la canasta). Clave estable para mapear a la base.
PRESENTACION_POR_EAN: dict[str, str] = {
    str(p["ean"]): p["presentacion"] for p in CANASTA if p.get("ean") and p.get("presentacion")
}


def precio_por_unidad(precio: float, ean: str | None) -> tuple[float, str] | None:
    """(precio_por_unidad_base, 'kg'|'L'|'un') para un producto de canasta, o None."""
    pres = PRESENTACION_POR_EAN.get(str(ean)) if ean else None
    if not pres or not precio:
        return None
    cantidad, base = parse_presentacion(pres)
    if cantidad <= 0:
        return None
    return (round(precio / cantidad, 2), base)
