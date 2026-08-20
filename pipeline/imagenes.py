"""
Fotos de producto: URLs de las CDNs de los retailers.

Las imágenes NO se descargan ni se versionan en el repo. Son assets de las
cadenas: la licencia CC BY 4.0 de Atlas cubre la serie de precios que
construimos, no las fotos de los supermercados. El dashboard enlaza a la CDN de
origen, que es lo que hace cualquier comparador de precios, y así además no se
sirven imágenes desactualizadas.

Este módulo resuelve una sola cosa: pedir la miniatura en vez del original.
Verificado el 2026-08-20 contra las cuatro cadenas — el original de Carrefour
pesa 273 KB, la miniatura 9 KB, y una grilla de 45 productos pasa de ~5 MB a
~400 KB.

  Coto  → sirve variantes por carpeta en el path: /large/ y /medium/
          (/small/ devuelve 404, no existe).
  VTEX  → día, Carrefour y Jumbo comparten plataforma: el tamaño se pide
          insertando -ANCHO-ALTO en el segmento /arquivos/ids/<id>.
"""

from __future__ import annotations

import base64
import re
import urllib.request

# La CDN de Coto negocia contenido: si el navegador manda `Accept: image/webp`,
# responde `Content-Type: image/webp` pero con bytes JPEG. Chrome detecta el
# desajuste y bloquea la respuesta (net::ERR_BLOCKED_BY_ORB), incluso desde el
# mismo origen — o sea que no es algo que se arregle del lado del dashboard.
# Diagnosticado el 2026-08-20 con Chrome headless. Esas fotos se traen desde el
# servidor (Python no manda ese Accept y recibe el image/jpeg correcto) y se
# embeben como data URI. Las tres cadenas VTEX se enlazan directo, sin costo.
_CDN_ROTA = "cotodigital"

# Ancho/alto que pide el dashboard para las miniaturas de grilla y de tarjeta.
MINIATURA_PX = 200


def requiere_proxy(url: str | None) -> bool:
    """True si la CDN no se puede enlazar directo desde el navegador."""
    return bool(url) and _CDN_ROTA in url


def como_data_uri(url: str, timeout: int = 8) -> str | None:
    """
    Descarga la imagen y la devuelve como data URI.

    Sólo para las CDNs que el navegador rechaza. Devuelve None ante cualquier
    fallo: una foto es decorativa, nunca puede tumbar el dashboard ni colgarlo
    esperando a un tercero (de ahí el timeout corto).
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "image/jpeg"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status != 200:
                return None
            datos = r.read()
        return "data:image/jpeg;base64," + base64.b64encode(datos).decode("ascii")
    except Exception:
        return None


def miniatura(url: str | None, px: int = MINIATURA_PX) -> str | None:
    """
    Devuelve la URL de la versión chica de `url`, o la original si la CDN no
    expone variantes conocidas. Nunca falla: ante cualquier formato inesperado
    devuelve lo que recibió (peor rendimiento, nunca una imagen rota).
    """
    if not url:
        return None

    if "cotodigital" in url:
        return url.replace("/large/", "/medium/")

    if "vteximg.com.br" in url or "vtexassets.com" in url:
        # .../arquivos/ids/343644/Leche-....jpg  →  .../arquivos/ids/343644-200-200/Leche-....jpg
        nueva, n = re.subn(r"(/arquivos/ids/\d+)(?=/)", rf"\1-{px}-{px}", url, count=1)
        if n:
            return nueva

    return url
