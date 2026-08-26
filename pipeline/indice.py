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


# ---------------------------------------------------------------------------
# Comparación entre cadenas
# ---------------------------------------------------------------------------
# Días comunes mínimos para publicar una comparación entre cadenas. Mismo
# umbral que el forecast: por debajo de esto la serie no aguanta la lectura y
# se muestra el estado, no el número.
DIAS_MINIMOS_COMPARACION = 30

COL_FUENTE = "fuente"


def canasta_comun(
    df: pd.DataFrame, col_producto: str = "producto", col_fuente: str = COL_FUENTE
) -> pd.DataFrame:
    """
    Recorta a los productos y los días presentes en TODAS las cadenas.

    Es el control que hace comparable un índice entre cadenas. Sin él, cada una
    mide su propia canasta y lo que sale es composición disfrazada de inflación:
    Carrefour matchea 34 productos contra los 27 de Día, y sobre canasta propia
    aparecía BAJANDO 1.27% cuando sobre los productos comunes es el que más
    aumenta (+1.83%). El signo se da vuelta.

    Con una sola cadena no hay nada que intersecar y se devuelve `df` igual.
    """
    if df.empty:
        return df
    grupos = [g for _, g in df.groupby(col_fuente)]
    if len(grupos) < 2:
        return df
    productos = set.intersection(*[set(g[col_producto]) for g in grupos])
    return df[df[col_producto].isin(productos) & df[COL_FECHA].isin(_fechas_comunes(df, col_fuente))]


def _fechas_comunes(df: pd.DataFrame, col_fuente: str = COL_FUENTE) -> set:
    """Días con relevamiento en todas las cadenas."""
    grupos = [g for _, g in df.groupby(col_fuente)]
    if len(grupos) < 2:
        return set(df[COL_FECHA])
    return set.intersection(*[set(g[COL_FECHA]) for g in grupos])


def indices_por_cadena(
    df: pd.DataFrame,
    col_producto: str = "producto",
    col_precio: str = COL_PRECIO,
    col_fuente: str = COL_FUENTE,
) -> pd.DataFrame:
    """
    Un índice encadenado por cadena sobre la canasta común, base 100 al primer
    día compartido. Cols: fecha, fuente, indice.

    `df` viene filtrado por canasta y sin peso variable, igual que
    `indice_encadenado`. Acá NO se filtra por cadena: se esperan todas juntas.
    """
    comun = canasta_comun(df, col_producto, col_fuente)
    if comun.empty:
        return pd.DataFrame(columns=[COL_FECHA, col_fuente, "indice"])

    series = []
    for fuente, g in comun.groupby(col_fuente):
        serie = indice_encadenado(g, col_producto, col_precio)
        if serie.empty:
            continue
        series.append(pd.DataFrame(
            {COL_FECHA: serie.index, col_fuente: fuente, "indice": serie.to_numpy()}
        ))
    if not series:
        return pd.DataFrame(columns=[COL_FECHA, col_fuente, "indice"])
    return pd.concat(series, ignore_index=True)


def contraste_composicion(
    df: pd.DataFrame,
    col_producto: str = "producto",
    col_precio: str = COL_PRECIO,
    col_fuente: str = COL_FUENTE,
) -> pd.DataFrame:
    """
    El hallazgo, en tabla: cuánto varió cada cadena medida sobre su propia
    canasta y cuánto sobre la común, con cuántos productos sostiene cada una.

    Publicar solo la columna controlada esconde por qué hace falta controlar.
    Las dos juntas son el resultado: la diferencia entre ambas es exactamente el
    sesgo de composición que se le estaría atribuyendo a los precios.

    Cols: fuente, var_propia, var_comun, productos_propios, productos_comunes.
    """
    if df.empty:
        return pd.DataFrame(
            columns=[col_fuente, "var_propia", "var_comun",
                     "productos_propios", "productos_comunes"]
        )

    comun = canasta_comun(df, col_producto, col_fuente)
    # Las dos columnas se miden sobre la MISMA ventana: si a la canasta propia
    # se le deja su rango completo, la diferencia entre ambas ya no es solo
    # composición sino también período. Coto arrancó 7 días antes que las otras
    # tres, y sin este recorte su var_propia salía 1.88 en vez de 1.37.
    en_ventana = df[df[COL_FECHA].isin(_fechas_comunes(df, col_fuente))]

    def _variacion(g: pd.DataFrame) -> float | None:
        serie = indice_encadenado(g, col_producto, col_precio)
        return round(float(serie.iloc[-1]) - 100, 2) if len(serie) else None

    filas = []
    for fuente, g in en_ventana.groupby(col_fuente):
        g_comun = comun[comun[col_fuente] == fuente]
        filas.append({
            col_fuente: fuente,
            "var_propia": _variacion(g),
            "var_comun": _variacion(g_comun) if not g_comun.empty else None,
            "productos_propios": int(g[col_producto].nunique()),
            "productos_comunes": int(g_comun[col_producto].nunique()),
        })
    return pd.DataFrame(filas).sort_values(col_fuente).reset_index(drop=True)
