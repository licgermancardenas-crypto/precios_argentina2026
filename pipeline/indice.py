"""
Índice Canasta Atlas — única fuente de verdad del cálculo.

Lo consumen el export público, el forecast, la comparativa vs IPC y el
dashboard: un solo lugar donde vive la metodología, para que los cuatro no
puedan divergir.

Metodología: **índice encadenado** (matched pairs). Entre dos días
consecutivos se compara sólo el subconjunto de productos con precio en AMBOS
días, y los ratios se encadenan:

    I_t = I_{t-1} · ( Σ p_t[m] / Σ p_{t-1}[m] )      m = presentes en t-1 y en t

Es el estándar de los índices de precios, y reemplaza a la versión anterior
(suma simple sobre los productos con serie completa desde la base). Aquella
descartaba de forma permanente cualquier producto sumado a la canasta después
del primer día: con 45 productos relevados el índice corría sobre 23, mientras
metadata.json publicaba 45. Encadenar incorpora las altas el día que empiezan a
tener par, sin reiniciar la base ni inventar precios hacia atrás.

Los frescos de balanza (`peso_variable`) quedan fuera: el precio publicado es el
de una pieza cuyo peso cambia entre relevamientos, así que sus saltos no son
inflación. Se siguen relevando y publicando en precios.csv.
"""

from __future__ import annotations

import pandas as pd

# Columnas que las distintas queries del proyecto usan para identificar el
# producto (el dashboard pivotea por nombre_original, el pipeline por
# nombre_normalizado); el cálculo es el mismo.
COL_FECHA = "fecha"
COL_PRECIO = "precio_lista"


def _pivot(df: pd.DataFrame, col_producto: str, col_precio: str) -> pd.DataFrame:
    return df.pivot_table(
        index=COL_FECHA, columns=col_producto, values=col_precio
    ).sort_index()


def indice_encadenado(
    df: pd.DataFrame, col_producto: str = "producto", col_precio: str = COL_PRECIO
) -> pd.Series:
    """
    Serie fecha → índice base 100 en el primer día, encadenando ratios sobre los
    productos presentes en cada par de días consecutivos.

    `df` ya viene filtrado por cadena y por canasta (y sin peso variable).
    """
    piv = _pivot(df, col_producto, col_precio)
    if piv.empty:
        return pd.Series(dtype=float)

    valores = [100.0]
    for i in range(1, len(piv)):
        ayer, hoy = piv.iloc[i - 1], piv.iloc[i]
        pareados = ayer.notna() & hoy.notna()
        base = ayer[pareados].sum()
        # Sin productos pareados no hay variación medible: el índice se sostiene
        # en su último valor en vez de saltar por un cambio de composición.
        ratio = hoy[pareados].sum() / base if pareados.any() and base else 1.0
        valores.append(valores[-1] * ratio)

    return pd.Series(valores, index=piv.index).round(2)


def costo_canasta(
    df: pd.DataFrame, col_producto: str = "producto", col_precio: str = COL_PRECIO
) -> pd.Series:
    """
    Serie fecha → costo de la canasta a composición constante, en pesos.

    Se ancla en el ÚLTIMO día (el de canasta más completa: es el costo real de
    comprarla hoy, verificable contra la góndola) y se reconstruye hacia atrás
    con el índice encadenado. Así `costo_t / costo_s == indice_t / indice_s`
    para cualquier par de días: el CSV público sigue siendo internamente
    consistente, y los consumidores que trabajan con ratios (nowcast vs IPC) no
    necesitan cambiar nada.
    """
    indice = indice_encadenado(df, col_producto, col_precio)
    if indice.empty:
        return pd.Series(dtype=float)

    piv = _pivot(df, col_producto, col_precio)
    ancla = piv.iloc[-1].dropna().sum()
    return (indice / indice.iloc[-1] * ancla).round(2)


def productos_del_indice(
    df: pd.DataFrame, col_producto: str = "producto", col_precio: str = COL_PRECIO
) -> int:
    """Cuántos productos distintos llegaron a entrar al índice (para metadata)."""
    piv = _pivot(df, col_producto, col_precio)
    return int(piv.notna().any().sum())
