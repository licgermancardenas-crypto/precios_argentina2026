"""
Reglas de comparación de precios entre cadenas.

El dashboard compara, para un mismo producto, lo que cobra cada cadena. Eso solo
tiene sentido si los precios son del mismo momento: acá vive el criterio de qué
lecturas son comparables entre sí.
"""

from __future__ import annotations

import pandas as pd

# Tolerancia, en días, entre lecturas de cadenas distintas para considerarlas
# comparables. El relevamiento no siempre cae el mismo día en las 4 cadenas, y
# un día de desfasaje es ruido normal, no un precio viejo.
DIAS_COMPARABLES = 3


def ultimo_por_cadena(df: pd.DataFrame, extra: tuple[str, ...] = ()) -> pd.DataFrame:
    """
    Último precio de cada cadena por producto, sin las lecturas rancias.

    Cuando una cadena deja de listar un producto, su último precio queda en la
    base para siempre. Compararlo contra los precios de hoy es comparar contra
    el pasado: el arroz Ala salía $1025 en Carrefour el 05-08, y ese número le
    ganaba a los $1079 que Día cobra hoy, así que el comparador coronaba a
    Carrefour con un precio que ya no existe.

    Se toma como referencia la lectura más fresca que tenga el producto en
    cualquier cadena —no la fecha del último relevamiento global, que haría
    desaparecer productos enteros— y se descartan las cadenas que quedaron más
    de `DIAS_COMPARABLES` atrás.

    `extra` son columnas que hay que arrastrar en el agrupamiento (categoria,
    ean) porque las vistas las necesitan después.
    """
    if df.empty:
        return df
    claves = ["producto_id", "nombre_original", *extra, "fuente"]
    ult = df.sort_values("fecha").groupby(claves, as_index=False).last()
    fechas = pd.to_datetime(ult["fecha"])
    mas_fresca = pd.to_datetime(ult.groupby("producto_id")["fecha"].transform("max"))
    return ult[(mas_fresca - fechas).dt.days <= DIAS_COMPARABLES]
