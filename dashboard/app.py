"""
Dashboard Atlas Precios — Streamlit
5 vistas: Resumen (índice + nowcast), Categorías y movimientos, Por Producto,
Comparador de cadenas, Proyección & Contexto.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# Streamlit Cloud arranca este archivo como módulo principal (no vía
# streamlit_app.py), así que sys.path[0] es dashboard/ y la raíz del repo no
# queda importable: `import pipeline` explota con ModuleNotFoundError. Agregarla
# acá hace que el dashboard funcione con cualquiera de los dos entrypoints.
_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from pipeline.comparador import ultimo_por_cadena  # noqa: E402
from pipeline.imagenes import como_data_uri, miniatura, requiere_proxy  # noqa: E402  (necesita el sys.path de arriba)
from pipeline.indice import costo_canasta, indice_encadenado  # noqa: E402
from pipeline.unidades import precio_por_unidad  # noqa: E402

# ---------------------------------------------------------------------------
# Identidad visual — tokens de marca (una sola fuente de verdad)
# ---------------------------------------------------------------------------
# Tema oscuro. Dos superficies: la página y la tarjeta que la contiene; todo el
# contenido vive en tarjetas, así que los gráficos se dibujan sobre CARD.
COLORES = {
    "bg":      "#0f1729",   # fondo de página
    "card":    "#18213a",   # superficie de tarjeta
    "card_2":  "#1f2a47",   # tarjeta elevada / hover
    "borde":   "#26324f",
    "texto":   "#e8edf7",   # 13.6:1 sobre card
    "texto_2": "#8b96ad",   # 5.4:1  sobre card — mínimo para texto legible
    "grilla":  "#253150",   # recesiva a propósito
    "cyan":    "#22d3ee",   # acento de marca
    "teal":    "#2dd4bf",
    "verde":   "#34d399",   # baja de precios (buena)
    "rojo":    "#f87171",   # suba de precios (mala)
}

# Paleta categórica: orden FIJO, nunca cíclico. Validada con el script del skill
# de dataviz contra las dos superficies oscuras
# (banda de luminosidad, piso de croma, separación CVD, visión normal, contraste).
# El cyan de marca NO está acá: con L 0.797 se sale de la banda oscura (0.48–0.67),
# así que es acento de UI y de serie única, no un slot categórico.
# Ojo al extender: con 4+ slots el set sólo cierra en el pairlist ADYACENTE
# (líneas y barras, que es lo que usa este dashboard). Para scatter de puntos
# habría que cortar en 3 o facetar.
_COLORWAY = [
    "#3987e5",  # azul
    "#d95926",  # naranja
    "#199e70",  # aqua
    "#c98500",  # amarillo
    "#d55181",  # magenta
    "#008300",  # verde
    "#9085e9",  # violeta
    "#e66767",  # rojo
]
_FUENTE = "IBM Plex Sans, sans-serif"

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

DB_PATH = Path(__file__).parent.parent / "data" / "atlas.db"

st.set_page_config(
    page_title="Atlas Precios",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Template de Plotly de marca — se aplica a TODOS los gráficos automáticamente.
# Transparente sobre la tarjeta: el gráfico hereda la superficie en la que cae.
pio.templates["atlas"] = go.layout.Template(
    layout=dict(
        font=dict(family=_FUENTE, color=COLORES["texto_2"], size=13),
        colorway=_COLORWAY,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor=COLORES["grilla"], showline=False, zeroline=False,
                   tickfont=dict(color=COLORES["texto_2"], size=11)),
        yaxis=dict(gridcolor=COLORES["grilla"], showline=False, zeroline=False,
                   tickfont=dict(color=COLORES["texto_2"], size=11)),
        hoverlabel=dict(bgcolor=COLORES["card_2"], bordercolor=COLORES["borde"],
                        font=dict(family=_FUENTE, size=12, color=COLORES["texto"])),
        margin=dict(t=30, b=20, l=10, r=24),
        legend=dict(orientation="h", y=1.14, x=0, font=dict(color=COLORES["texto_2"], size=11)),
        colorscale=dict(sequential=[[0, "#1b3550"], [1, COLORES["cyan"]]]),
    )
)
pio.templates.default = "atlas"

# Estilos de la app. La referencia es un dashboard de tarjetas: superficie
# elevada, radio generoso, bordes de 1px muy sutiles y acento cyan sólo en lo
# que está activo o es la cifra principal.
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

    :root {
        --bg: #0f1729;  --card: #18213a;  --card-2: #1f2a47;  --borde: #26324f;
        --txt: #e8edf7; --txt-2: #8b96ad; --cyan: #22d3ee;    --teal: #2dd4bf;
        --pos: #34d399; --neg: #f87171;
    }

    html, body, [class*="css"], .stApp, [data-testid="stMarkdownContainer"] {
        font-family: 'IBM Plex Sans', sans-serif;
    }
    .stApp { background: var(--bg); }
    h1, h2, h3 { color: var(--txt); font-weight: 600; letter-spacing: -0.015em; }
    h1 { font-weight: 700; }

    /* --- Tarjetas: el contenedor base de todo el layout --- */
    .atlas-card {
        background: var(--card);
        border: 1px solid var(--borde);
        border-radius: 16px;
        padding: 18px 20px;
        margin-bottom: 14px;
    }
    .atlas-card h4 {
        color: var(--txt-2); font-size: .78rem; font-weight: 600;
        text-transform: uppercase; letter-spacing: .06em; margin: 0 0 12px;
    }

    /* --- KPI: la cifra manda, el label se retira --- */
    [data-testid="stMetric"] {
        background: var(--card);
        border: 1px solid var(--borde);
        border-radius: 16px;
        padding: 16px 18px 14px;
    }
    [data-testid="stMetricLabel"] p {
        color: var(--txt-2); font-weight: 500; font-size: .78rem;
        text-transform: uppercase; letter-spacing: .05em;
    }
    [data-testid="stMetricValue"] {
        color: var(--txt); font-weight: 600; font-size: 2rem; letter-spacing: -.02em;
    }
    /* --- Tabs como pills segmentadas (la nav de la referencia) ---
       Streamlit 1.62 ya no emite los data-baseweb viejos: el elemento con
       role=tab ES [data-testid="stTab"], y el texto vive en un markdown adentro. */
    [data-testid="stTabs"] [role="tablist"] {
        gap: 4px; background: var(--card); border: 1px solid var(--borde);
        border-radius: 12px; padding: 5px; margin-bottom: 6px;
    }
    [data-testid="stTabs"] [role="tablist"] > div:last-child:empty,
    [data-testid="stTabs"] [data-baseweb="tab-highlight"],
    [data-testid="stTabs"] [data-baseweb="tab-border"] { display: none !important; }
    [data-testid="stTabs"] [role="tablist"] { border-bottom: 1px solid var(--borde); }

    [data-testid="stTab"] {
        border-radius: 8px; padding: 6px 14px; transition: background .12s ease;
    }
    [data-testid="stTab"] p { color: var(--txt-2); font-weight: 500; font-size: .88rem; }
    [data-testid="stTab"]:hover { background: var(--card-2); }
    [data-testid="stTab"]:hover p { color: var(--txt); }
    [data-testid="stTab"][aria-selected="true"] { background: var(--cyan); }
    [data-testid="stTab"][aria-selected="true"] p { color: #0b1220; font-weight: 600; }

    /* --- Cada gráfico vive en una tarjeta (el layout de la referencia) --- */
    [data-testid="stPlotlyChart"] {
        background: var(--card); border: 1px solid var(--borde);
        border-radius: 16px; padding: 14px 16px 10px; margin-bottom: 4px;
    }
    [data-testid="stPlotlyChart"] > div,
    .js-plotly-plot, .plot-container, .svg-container { background: transparent !important; }

    /* Títulos de sección: chicos y en versalita, como los de la referencia,
       para que la cifra del gráfico sea lo que pesa y no el encabezado. */
    [data-testid="stHeadingWithActionElements"] h3 {
        font-size: 1.02rem; font-weight: 600; letter-spacing: .01em;
        margin: 4px 0 2px;
    }
    [data-testid="stAlert"] { border-radius: 14px; border: 1px solid var(--borde); }

    /* --- Contenedores con borde = las tarjetas del layout --- */
    [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {
        background: var(--card); border: 1px solid var(--borde);
        border-radius: 16px;
    }
    /* El KPI destacado lleva el acento; el resto queda neutro para que no compitan. */
    .st-key-kpi_hero [data-testid="stMetric"] {
        background: linear-gradient(150deg, #1c2b4d 0%, var(--card) 62%);
        border-color: #2f4670;
    }
    .st-key-kpi_hero [data-testid="stMetricValue"] { color: var(--cyan); }

    /* --- Controles --- */
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        border: 1px solid var(--borde); border-radius: 12px;
    }
    .stSelectbox div[data-baseweb="select"] > div,
    .stMultiSelect div[data-baseweb="select"] > div {
        background: var(--card); border-color: var(--borde); border-radius: 10px;
    }
    .stDownloadButton button, .stButton button {
        background: var(--card-2); color: var(--txt);
        border: 1px solid var(--borde); border-radius: 10px; font-weight: 500;
    }
    .stDownloadButton button:hover, .stButton button:hover {
        border-color: var(--cyan); color: var(--cyan);
    }
    [data-testid="stExpander"] {
        background: var(--card); border: 1px solid var(--borde); border-radius: 14px;
    }
    hr, [data-testid="stDivider"] { border-color: var(--borde); }

    /* --- Densidad: la referencia apila tarjetas juntas, sin aire muerto --- */
    [data-testid="stVerticalBlock"] { gap: .62rem; }
    [data-testid="stHorizontalBlock"] { gap: .7rem; }
    [data-testid="stElementContainer"]:has(> [data-testid="stMarkdownContainer"] > hr) {
        margin: .1rem 0;
    }
    hr { margin: .5rem 0; border-color: var(--borde); opacity: .55; }
    [data-testid="stCaptionContainer"] p { color: var(--txt-2); font-size: .82rem; }

    /* --- Header compacto: marca a la izquierda, estado a la derecha --- */
    .atlas-head {
        display: flex; align-items: center; justify-content: space-between;
        gap: 16px; flex-wrap: wrap;
        background: var(--card); border: 1px solid var(--borde);
        border-radius: 16px; padding: 14px 20px; margin-bottom: 12px;
    }
    .atlas-head .marca { display: flex; align-items: center; gap: 12px; }
    .atlas-head .logo {
        width: 38px; height: 38px; border-radius: 11px; flex: none;
        background: linear-gradient(140deg, var(--cyan), #2f6ed4);
        display: grid; place-items: center; font-size: 19px;
    }
    .atlas-head h1 {
        margin: 0; font-size: 1.32rem; font-weight: 700; letter-spacing: -.02em;
        line-height: 1.15;
    }
    .atlas-head .bajada { margin: 1px 0 0; color: var(--txt-2); font-size: .8rem; }
    .atlas-head .chip {
        display: inline-flex; align-items: center; gap: 7px;
        background: var(--card-2); border: 1px solid var(--borde);
        border-radius: 999px; padding: 6px 13px;
        color: var(--txt-2); font-size: .78rem; white-space: nowrap;
    }
    .atlas-head .punto {
        width: 7px; height: 7px; border-radius: 50%; background: var(--pos);
        box-shadow: 0 0 0 3px rgba(52,211,153,.16);
    }

    /* --- Comparador con fotos --- */
    .fila-cadena {
        display: flex; align-items: center; gap: 14px;
        background: var(--card); border: 1px solid var(--borde);
        border-radius: 14px; padding: 10px 16px; margin-bottom: 9px;
    }
    .fila-cadena img, .fila-cadena .thumb-vacia {
        width: 46px; height: 46px; border-radius: 10px; flex: none;
        object-fit: contain; background: #fff;
    }
    .fila-cadena .thumb-vacia { background: var(--card-2); }
    .fila-cadena .cadena {
        padding-left: 10px; color: var(--txt); font-weight: 600; font-size: .95rem;
        min-width: 116px;
    }
    .fila-cadena .precio {
        margin-left: auto; color: var(--txt); font-weight: 700;
        font-size: 1.32rem; letter-spacing: -.02em; font-variant-numeric: tabular-nums;
    }
    .pill-barata, .pill-dif {
        border-radius: 999px; padding: 4px 11px; font-size: .76rem; font-weight: 600;
        white-space: nowrap; min-width: 82px; text-align: center;
    }
    .pill-barata { background: rgba(52,211,153,.16); color: var(--pos); }
    .pill-igual  { background: rgba(139,150,173,.16); color: var(--txt-2); }
    .pill-dif    { background: rgba(248,113,113,.14); color: var(--neg); }
    .brecha { color: var(--txt-2); font-size: .88rem; margin-top: 12px; }

    /* --- Grilla catálogo --- */
    .card-foto {
        width: 100%; aspect-ratio: 1; object-fit: contain;
        background: #fff; border-radius: 12px;
        border: 1px solid var(--borde); padding: 6px;
    }
    .card-precio {
        margin: 8px 0 2px; color: var(--txt); font-weight: 700; font-size: 1.02rem;
        font-variant-numeric: tabular-nums; line-height: 1.2;
    }
    .card-precio span { color: var(--txt-2); font-weight: 500; font-size: .78rem; }
    /* El nombre del producto es el botón: tipografía de texto, no de control. */
    .stButton button {
        font-size: .78rem; font-weight: 500; text-align: left;
        padding: 7px 10px; line-height: 1.25; min-height: 46px;
    }
    .sin-foto {
        display: grid; place-items: center; aspect-ratio: 1; width: 100%;
        background: var(--card-2); border: 1px dashed var(--borde);
        border-radius: 14px; color: var(--txt-2); font-size: .82rem;
    }
    /* Las fotos vienen sobre fondo blanco del retailer: se les da su propia
       superficie clara para que no floten sobre el oscuro con halo. */
    [data-testid="stImage"] img { border-radius: 14px; background: #fff; }

    /* --- Limpieza del chrome default de Streamlit --- */
    #MainMenu, header [data-testid="stToolbar"] { visibility: hidden; }
    footer { visibility: hidden; }
    .block-container { padding-top: 2.2rem; max-width: 1500px; }
    .footer { text-align: center; color: var(--txt-2); font-size: 12px; margin-top: 32px; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def cargar_datos() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retorna (df_precios, df_productos) desde la base de datos."""
    if not DB_PATH.exists():
        return pd.DataFrame(), pd.DataFrame()

    con = sqlite3.connect(DB_PATH)

    df_precios = pd.read_sql("""
        SELECT
            pr.fecha,
            pr.fuente,
            pr.precio_lista,
            pr.precio_promo,
            p.nombre_original,
            p.nombre_normalizado,
            p.ean,
            p.categoria,
            p.contenido_valor,
            p.contenido_unidad,
            COALESCE(p.peso_variable, 0) AS peso_variable,
            p.id AS producto_id
        FROM precios pr
        JOIN productos p ON p.id = pr.producto_id
        WHERE p.en_canasta = 1
        ORDER BY pr.fecha, p.categoria
    """, con)

    df_eventos = pd.read_sql("""
        SELECT e.*, p.nombre_original
        FROM eventos e
        JOIN productos p ON p.id = e.producto_id
        ORDER BY e.fecha DESC
    """, con)

    con.close()
    return df_precios, df_eventos


@st.cache_data(ttl=3600)
def cargar_imagenes() -> pd.DataFrame:
    """
    Fotos de producto por cadena. Cols: producto_id, fuente, url.

    La tabla es nueva (v5): una base normalizada antes de la migración no la
    tiene, así que se degrada a vacío en vez de romper el dashboard.
    """
    if not DB_PATH.exists():
        return pd.DataFrame(columns=["producto_id", "fuente", "url"])
    con = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("SELECT producto_id, fuente, url FROM imagenes", con)
    except Exception:
        df = pd.DataFrame(columns=["producto_id", "fuente", "url"])
    finally:
        con.close()
    return df


@st.cache_data(ttl=86400, show_spinner=False, max_entries=400)
def foto(url: str | None, px: int) -> str | None:
    """
    URL lista para poner en un <img>, al tamaño pedido.

    Las CDNs de VTEX se enlazan directo (cero costo para nosotros). La de Coto
    rompe en el navegador —manda Content-Type webp con bytes jpeg y Chrome la
    bloquea por ORB— así que esas se traen por el servidor y se embeben. Se
    cachea un día: son fotos de catálogo, no cambian de un rerun al otro, y así
    no se golpea la CDN ajena en cada interacción del filtro.
    """
    chica = miniatura(url, px)
    if not chica:
        return None
    return como_data_uri(chica) if requiere_proxy(chica) else chica


def url_preferida(urls: dict[str, str]) -> str | None:
    """
    De las fotos que hay para un producto, la mejor para una miniatura de grilla.

    Prioriza las CDNs que el navegador puede pedir directo: en una grilla de 45
    productos, mandarlas todas por el proxy serían 45 descargas del lado del
    servidor. Como el match es por EAN, es el mismo artículo en cualquier
    cadena, así que la foto sirve igual venga de donde venga.
    """
    if not urls:
        return None
    directas = [u for u in urls.values() if not requiere_proxy(u)]
    return directas[0] if directas else next(iter(urls.values()))


@st.cache_data(ttl=3600)
def cargar_regresores() -> pd.DataFrame:
    """Series externas (dólar) desde la base. Vacío si la tabla no existe aún."""
    if not DB_PATH.exists():
        return pd.DataFrame()
    con = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("SELECT fecha, serie, valor FROM regresores ORDER BY fecha", con)
    except Exception:
        df = pd.DataFrame(columns=["fecha", "serie", "valor"])
    finally:
        con.close()
    if not df.empty:
        df["fecha"] = pd.to_datetime(df["fecha"])
    return df


@st.cache_data(ttl=3600)
def cargar_forecast() -> dict:
    """Lee data/public/forecast.json (lo genera pipeline/forecast.py). {} si no existe."""
    ruta = DB_PATH.parent / "public" / "forecast.json"
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def cargar_comparativa_ipc() -> dict:
    """Lee data/public/comparativa_ipc.json (índice vs IPC oficial). {} si no existe."""
    ruta = DB_PATH.parent / "public" / "comparativa_ipc.json"
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def cargar_hallazgos() -> dict:
    """Lee data/public/hallazgos.json (dispersión + eventos). {} si no existe."""
    ruta = DB_PATH.parent / "public" / "hallazgos.json"
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def cargar_qc() -> dict:
    """Lee data/public/qc.json (salud del relevamiento). {} si no existe."""
    ruta = DB_PATH.parent / "public" / "qc.json"
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return {}


# El índice vive en pipeline/indice.py — una sola fuente de verdad compartida
# con el export público, el forecast y la comparativa vs IPC. Acá sólo se
# pivotea por nombre_original (el nombre que ve el usuario en el dashboard).
_COL = "nombre_original"


def _base_indice(df: pd.DataFrame) -> pd.DataFrame:
    """Filas que alimentan el índice: sin frescos de balanza (peso variable)."""
    if "peso_variable" not in df.columns:
        return df
    return df[df["peso_variable"] == 0]


@st.cache_data(ttl=3600)
def calcular_indice(df: pd.DataFrame) -> pd.DataFrame:
    """Índice Canasta Atlas total (encadenado, base 100 en el primer día)."""
    if df.empty:
        return pd.DataFrame()

    base = _base_indice(df)
    indice = indice_encadenado(base, col_producto=_COL)
    if indice.empty:
        return pd.DataFrame()

    idx = pd.DataFrame({
        "fecha": pd.to_datetime(indice.index),
        "costo_canasta": costo_canasta(base, col_producto=_COL).values,
        "indice": indice.values,
    }).sort_values("fecha")
    idx["var_diaria"] = idx["indice"].pct_change().mul(100).round(2)
    return idx


@st.cache_data(ttl=3600)
def calcular_indice_categoria(df: pd.DataFrame) -> pd.DataFrame:
    """Índice base 100 por categoría (encadenado). Columnas: fecha, categoria, indice."""
    if df.empty:
        return pd.DataFrame()

    filas = []
    for cat, g in _base_indice(df).groupby("categoria"):
        indice = indice_encadenado(g, col_producto=_COL)
        for fecha, valor in indice.items():
            filas.append({"fecha": fecha, "categoria": cat, "indice": round(valor, 2)})
    out = pd.DataFrame(filas)
    if not out.empty:
        out["fecha"] = pd.to_datetime(out["fecha"])
    return out.sort_values(["categoria", "fecha"])


# ---------------------------------------------------------------------------
# Helpers de UI
# ---------------------------------------------------------------------------

def _flecha(val: float | None) -> str:
    if val is None:
        return ""
    return "▲" if val > 0 else ("▼" if val < 0 else "→")


def _color_var(val: float | None) -> str:
    """Suba de precios = malo (rojo), baja = bueno (verde), sin cambio = texto neutro."""
    if val is None:
        return COLORES["texto_2"]
    return COLORES["rojo"] if val > 0 else (COLORES["verde"] if val < 0 else COLORES["texto_2"])


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

# Barra de marca compacta: identidad a la izquierda, salud del relevamiento a
# la derecha — el estado es lo primero que hay que poder chequear de un vistazo.
_qc = cargar_qc()
_chip = ""
if _qc.get("cadenas"):
    _ok = sum(1 for c in _qc["cadenas"].values() if c["estado"] == "ok")
    _tot = len(_qc["cadenas"])
    _tono = {"ok": "var(--pos)", "warning": "#fbbf24", "critical": "var(--neg)"}.get(
        _qc["estado_global"], "var(--txt-2)")
    _detalle = "" if _qc["estado_global"] == "ok" else " · " + "; ".join(_qc.get("alertas", []))
    _chip = (
        f"<span class='chip'><span class='punto' style='background:{_tono};'></span>"
        f"Relevamiento {_qc.get('fecha', '—')} · {_ok}/{_tot} cadenas OK{_detalle}</span>"
    )

st.markdown(f"""
<div class="atlas-head">
  <div class="marca">
    <div class="logo">📊</div>
    <div>
      <h1>Atlas Precios</h1>
      <p class="bajada">Índice de inflación diario sobre 4 supermercados argentinos —
      datos abiertos, reproducibles, y por delante del IPC oficial.</p>
    </div>
  </div>
  {_chip}
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

# Cadena de referencia para el índice y las vistas históricas (evita doble conteo multi-cadena).
FUENTE_REFERENCIA = "coto"

df_todas, df_eventos = cargar_datos()

if df_todas.empty:
    st.warning("Base de datos no encontrada o sin datos. Ejecutá el pipeline primero.", icon="⚠️")
    st.stop()

# ---------------------------------------------------------------------------
# Barra de filtros global
# ---------------------------------------------------------------------------
# Un solo lugar de control para todo el tablero. Dos reglas que NO se negocian,
# porque si se rompen el número publicado deja de ser el índice:
#
#   1. El filtro de cadenas NO toca el índice. El Índice Canasta Atlas está
#      definido sobre la cadena de referencia; dejar que el visitante lo
#      recalcule sobre "Día + Jumbo" produciría un número que no es el que
#      publicamos en indice_canasta.csv, con el mismo nombre.
#   2. El rango de fechas es una ventana de VISTA, no un rebase. La base 100
#      sigue anclada al primer día de la serie; acortar el rango hace zoom, no
#      cambia el índice. Rebasar mostraría "+0.0%" cada vez que alguien elige
#      "últimos 7 días", que es exactamente la lectura equivocada.

_TODAS = sorted(df_todas["fuente"].unique())
_CATS = sorted(df_todas["categoria"].dropna().unique())
_RANGOS = {"Todo": None, "Últimos 30 días": 30, "Últimos 14 días": 14, "Últimos 7 días": 7}

# El color sigue a la ENTIDAD, nunca a su posición: se asigna sobre el universo
# completo, así deseleccionar una cadena o una categoría no repinta las que
# quedan. Con índices por enumerate() del set filtrado, cada filtro cambiaba el
# color de todas las series y la lectura se volvía imposible.
COLOR_CADENA = {f: _COLORWAY[i % len(_COLORWAY)] for i, f in enumerate(_TODAS)}
COLOR_CATEGORIA = {c: _COLORWAY[i % len(_COLORWAY)] for i, c in enumerate(_CATS)}

for _k, _v in {"f_cadenas": _TODAS, "f_categoria": "Todas",
               "f_rango": "Todo", "f_producto": None}.items():
    st.session_state.setdefault(_k, _v)

# Cross-filter: un clic en un gráfico no puede escribir la clave de un widget ya
# instanciado (Streamlit lo prohíbe, y el tablero se caía con StreamlitAPIException).
# El handler deja el valor "pendiente" y pide un rerun; acá arriba, ANTES de crear
# los widgets, se aplica. Es el único punto del script donde se puede.
if "_pendiente" in st.session_state:
    for _pk, _pv in st.session_state.pop("_pendiente").items():
        st.session_state[_pk] = _pv


def pedir_filtro(**cambios) -> None:
    """Aplica filtros desde un clic en un gráfico, en el próximo rerun."""
    st.session_state["_pendiente"] = cambios
    st.rerun()


def _reset_filtros() -> None:
    st.session_state.update(f_cadenas=_TODAS, f_categoria="Todas",
                            f_rango="Todo", f_producto=None)


with st.container(border=True):
    fb1, fb2, fb3, fb4 = st.columns([4, 2, 2, 1])
    fb1.multiselect("Supermercados", _TODAS, key="f_cadenas",
                    format_func=str.capitalize,
                    help="Aplica al comparador, a las series por producto y al precio "
                         "por unidad. El Índice Canasta Atlas siempre se calcula sobre "
                         f"{FUENTE_REFERENCIA.capitalize()}, la cadena de referencia.")
    fb2.selectbox("Categoría", ["Todas"] + [c.capitalize() for c in _CATS], key="f_categoria")
    fb3.selectbox("Rango", list(_RANGOS), key="f_rango",
                  help="Hace zoom en las series. No cambia la base 100 del índice.")
    fb4.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    fb4.button("Limpiar", on_click=_reset_filtros, width="stretch")

# Selección efectiva (una cadena vacía se lee como "todas", no como "ninguna").
CADENAS_SEL = st.session_state["f_cadenas"] or _TODAS
CAT_SEL = st.session_state["f_categoria"]
_dias_rango = _RANGOS[st.session_state["f_rango"]]


def filtrar(df: pd.DataFrame, *, cadenas: bool = True, categoria: bool = True,
            rango: bool = True) -> pd.DataFrame:
    """Aplica la barra global a un dataframe de precios."""
    out = df
    if cadenas and "fuente" in out.columns:
        out = out[out["fuente"].isin(CADENAS_SEL)]
    if categoria and CAT_SEL != "Todas" and "categoria" in out.columns:
        out = out[out["categoria"].str.lower() == CAT_SEL.lower()]
    if rango and _dias_rango and "fecha" in out.columns:
        corte = pd.to_datetime(out["fecha"]).max() - pd.Timedelta(days=_dias_rango - 1)
        out = out[pd.to_datetime(out["fecha"]) >= corte]
    return out


def selector_producto(df: pd.DataFrame, key: str) -> str | None:
    """
    Selector de producto respaldado por el estado global `f_producto`.

    Vive en session_state y no en el widget para que la tab de fotos y la de
    serie histórica queden sincronizadas: elegís un producto en una y la otra
    ya está parada en el mismo. La lista respeta la categoría de la barra.
    """
    base = df if CAT_SEL == "Todas" else df[df["categoria"].str.lower() == CAT_SEL.lower()]
    opciones = sorted(base["nombre_original"].dropna().unique())
    if not opciones:
        st.info("Ningún producto entra en la categoría elegida.", icon="ℹ️")
        return None

    actual = st.session_state.get("f_producto")
    # Si el filtro de categoría dejó afuera al producto elegido, se cae al primero
    # en vez de romper el selectbox con un valor que no está en las opciones.
    if actual not in opciones:
        actual = opciones[0]
        st.session_state["f_producto"] = actual

    # Streamlit ignora `index` cuando la clave del widget ya existe en el estado,
    # así que el desplegable se sincroniza a mano contra el estado canónico. Sin
    # esto, elegir un producto en la grilla no movía el selector (el widget
    # pisaba el valor con el suyo viejo). Se escribe ANTES de instanciarlo, que
    # es la única ventana en que Streamlit lo permite.
    if st.session_state.get(key) != actual:
        st.session_state[key] = actual

    def _sincronizar() -> None:
        st.session_state["f_producto"] = st.session_state[key]

    return st.selectbox("Producto", opciones, key=key, on_change=_sincronizar)


def ventana(df: pd.DataFrame, col: str = "fecha") -> pd.DataFrame:
    """Recorta una serie ya calculada al rango elegido (zoom, no recálculo)."""
    if not _dias_rango or df.empty or col not in df.columns:
        return df
    fechas = pd.to_datetime(df[col])
    return df[fechas >= fechas.max() - pd.Timedelta(days=_dias_rango - 1)]


# Las vistas históricas (índice, movimientos, producto) usan solo la cadena de referencia.
df_precios = df_todas[df_todas["fuente"] == FUENTE_REFERENCIA]

# El índice se calcula SIEMPRE sobre la serie completa y la canasta entera: es
# el número publicado. La categoría y el rango se aplican después, al mostrar.
idx = calcular_indice(df_precios)
ultima_fecha = idx["fecha"].max()
primera_fecha = idx["fecha"].min()
dias_de_datos = (ultima_fecha - primera_fecha).days + 1

# ---------------------------------------------------------------------------
# KPIs superiores
# ---------------------------------------------------------------------------

ultimo = idx.iloc[-1]
penultimo = idx.iloc[-2] if len(idx) > 1 else None
hace_7 = idx[idx["fecha"] <= ultima_fecha - pd.Timedelta(days=7)].iloc[-1] if len(idx) >= 7 else None
hace_30 = idx[idx["fecha"] <= ultima_fecha - pd.Timedelta(days=30)].iloc[-1] if len(idx) >= 30 else None

k1, k2, k3, k4 = st.columns(4)

with k1.container(key="kpi_hero"):
    st.metric(
        label="Índice Canasta Atlas",
        value=f"{ultimo['indice']:.1f}",
        delta=f"{ultimo['var_diaria']:+.1f}% hoy" if pd.notna(ultimo["var_diaria"]) else None,
        delta_color="inverse",
    )

with k2:
    costo = ultimo["costo_canasta"]
    delta_7 = (
        f"{((costo - hace_7['costo_canasta']) / hace_7['costo_canasta'] * 100):+.1f}% vs 7d"
        if hace_7 is not None else None
    )
    st.metric(label="Costo canasta hoy", value=f"${costo:,.0f}", delta=delta_7, delta_color="inverse")

with k3:
    delta_30 = (
        f"{((costo - hace_30['costo_canasta']) / hace_30['costo_canasta'] * 100):+.1f}%"
        if hace_30 is not None else "< 30 días de datos"
    )
    st.metric(label="Variación mensual", value=delta_30 if hace_30 is not None else "—", delta=None)

with k4:
    st.metric(label="Días de historia", value=f"{dias_de_datos}", delta=f"desde {primera_fecha.strftime('%d/%m/%Y')}")

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab1, tab2, tab3, tab4, tab6, tab5 = st.tabs(
    ["📊 Resumen", "📈 Categorías y movimientos", "🔍 Por Producto",
     "🏪 Comparador de cadenas", "🛒 Comparar con fotos", "📉 Proyección & Contexto"]
)


# ============================================================
# TAB 1 — Índice Canasta
# ============================================================
with tab1:
    # Insight dinámico — lee los datos actuales para el primer visitante
    if len(idx) >= 2:
        var_total = idx["indice"].iloc[-1] - 100
        dias_serie = (idx["fecha"].iloc[-1] - idx["fecha"].iloc[0]).days + 1
        verbo = "subió" if var_total > 0 else ("bajó" if var_total < 0 else "se mantuvo")
        _idx_cat_ins = calcular_indice_categoria(df_precios)
        _extra = ""
        if not _idx_cat_ins.empty:
            _uc = _idx_cat_ins.sort_values("fecha").groupby("categoria").last()
            _uc["var"] = _uc["indice"] - 100
            _lider = _uc["var"].idxmax()
            if _uc["var"].max() > 0:
                _extra = f" El rubro que más empuja es **{_lider.capitalize()}** ({_uc['var'].max():+.1f}%)."
        st.info(
            f"En los últimos **{dias_serie} días**, la Canasta Atlas {verbo} **{var_total:+.1f}%**.{_extra}",
            icon="📊",
        )

    # Nowcast: nuestro índice vs IPC oficial — el diferencial del proyecto, va primero
    comp_ipc = cargar_comparativa_ipc()
    mec = comp_ipc.get("mes_en_curso")
    if mec:
        st.subheader("🎯 Nowcast — nuestro índice vs IPC oficial")
        st.caption(
            "El IPC de INDEC se publica con ~6 semanas de rezago. La Canasta Atlas "
            "mide el mes en curso **en tiempo real**: adelantamos la inflación oficial."
        )
        ipc_u = comp_ipc.get("ipc_ultimo") or {}
        n1, n2, n3 = st.columns(3)
        n1.metric(
            f"Canasta Atlas — {mec['mes']} (parcial)",
            f"{mec['var_canasta_pct']:+.1f}%",
            delta=f"{mec['dias_observados']} días relevados",
            delta_color="off",
        )
        if ipc_u:
            n2.metric(f"IPC oficial — {ipc_u['mes']}", f"{ipc_u['var_pct']:+.1f}%",
                      delta="último dato publicado", delta_color="off")
        n3.metric("Ventaja temporal", "~6 semanas",
                  delta=f"IPC {mec['mes']} se publica después", delta_color="off")

        # Histórico mensual: nuestra canasta vs IPC (se llena al cerrar meses)
        mensual = comp_ipc.get("mensual") or []
        cerrados = [m for m in mensual if m.get("var_ipc_pct") is not None]
        if cerrados:
            dfm = pd.DataFrame(cerrados)
            figm = go.Figure()
            figm.add_trace(go.Bar(x=dfm["mes"], y=dfm["var_canasta_pct"],
                                  name="Canasta Atlas", marker_color=COLORES["cyan"]))
            figm.add_trace(go.Bar(x=dfm["mes"], y=dfm["var_ipc_pct"],
                                  name="IPC oficial", marker_color="#c98500"))
            figm.update_layout(barmode="group", height=300, margin=dict(t=20, b=20),
                               yaxis_title="Var. mensual %",
                               legend=dict(orientation="h", y=1.15))
            st.plotly_chart(figm, width="stretch")
        else:
            st.info(
                f"El contraste mensual completo (Canasta vs IPC) se activa al cerrar "
                f"el primer mes completo de historia. Por ahora, nowcast de {mec['mes']}.",
                icon="⏳",
            )
        st.divider()

    # Índice Canasta Atlas (base 100)
    st.subheader("Índice Canasta Atlas")
    st.caption("Base 100 = primer día de datos. Índice encadenado sobre la cadena de referencia: "
               "se comparan los productos con precio en ambos días. Los frescos de balanza "
               "(precio por pieza de peso variable) quedan fuera.")
    if len(idx) < 2:
        st.info("Necesitás al menos 2 días de datos para ver la evolución.", icon="ℹ️")
    else:
        idx_v = ventana(idx)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=idx_v["fecha"], y=idx_v["indice"], mode="lines+markers", name="Índice",
            line=dict(color=COLORES["cyan"], width=2.5), marker=dict(size=5),
            hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Índice: %{y:.1f}<extra></extra>",
        ))
        fig.add_hline(y=100, line_dash="dot", line_color=COLORES["texto_2"], line_width=1,
                      annotation_text="Base 100", annotation_position="top left",
                      annotation_font=dict(color=COLORES["texto_2"], size=11))
        fig.update_layout(height=380, xaxis_title=None, yaxis_title="Índice (base 100)")
        st.plotly_chart(fig, width="stretch")


# ============================================================
# TAB 2 — Categorías y movimientos
# ============================================================
with tab2:
    # Índice por categoría
    idx_cat = calcular_indice_categoria(df_precios)
    if CAT_SEL != "Todas":
        idx_cat = idx_cat[idx_cat["categoria"].str.lower() == CAT_SEL.lower()]
    idx_cat = ventana(idx_cat)
    if not idx_cat.empty and idx_cat["fecha"].nunique() > 1:
        st.subheader("Índice por categoría")
        st.caption("Cada categoría en base 100 a su primer día. Muestra qué rubros empujan la canasta.")

        colg, colb = st.columns([3, 2])
        with colg:
            figc = go.Figure()
            for cat, g in idx_cat.groupby("categoria"):
                figc.add_trace(go.Scatter(
                    x=g["fecha"], y=g["indice"], mode="lines+markers", name=cat.capitalize(),
                    line=dict(color=COLOR_CATEGORIA.get(cat, COLORES["cyan"]), width=2),
                    marker=dict(size=4),
                    hovertemplate=f"<b>{cat.capitalize()}</b> %{{x|%d/%m}}<br>%{{y:.1f}}<extra></extra>",
                ))
            figc.add_hline(y=100, line_dash="dot", line_color=COLORES["texto_2"], line_width=1)
            figc.update_layout(height=340, xaxis_title=None, yaxis_title="Índice (base 100)",
                               legend=dict(font=dict(size=11)))
            st.plotly_chart(figc, width="stretch")
        with colb:
            ultimo_cat = idx_cat.sort_values("fecha").groupby("categoria").last().reset_index()
            ultimo_cat["var"] = (ultimo_cat["indice"] - 100).round(2)
            ultimo_cat = ultimo_cat.sort_values("var", ascending=False)
            figb = go.Figure(go.Bar(
                x=ultimo_cat["var"], y=ultimo_cat["categoria"].str.capitalize(), orientation="h",
                marker_color=[COLORES["rojo"] if v > 0 else COLORES["verde"] for v in ultimo_cat["var"]],
                hovertemplate="%{y}: %{x:+.1f}%<extra></extra>",
            ))
            figb.update_layout(height=340, xaxis_title="Var. acumulada %", yaxis_title=None,
                               margin=dict(t=30, b=48, l=10, r=24), clickmode="event+select")
            st.caption("Hacé clic en un rubro para filtrar todo el tablero.")
            _sel_cat = st.plotly_chart(figb, width="stretch", key="cx_categoria",
                                       on_select="rerun", selection_mode="points")
            _pts = (_sel_cat or {}).get("selection", {}).get("points", [])
            if _pts:
                # El eje y del gráfico son los rubros capitalizados; el filtro global
                # los guarda igual, así que se asigna directo.
                _clic = _pts[0].get("y")
                if _clic and _clic != CAT_SEL:
                    pedir_filtro(f_categoria=_clic)

    # Historial del índice
    if len(idx) > 1:
        st.subheader("Historial del índice")
        hist = idx.sort_values("fecha", ascending=False).head(30).copy()
        hist["fecha_str"] = hist["fecha"].dt.strftime("%d/%m/%Y")
        hist["costo_str"] = hist["costo_canasta"].apply(lambda x: f"${x:,.0f}")
        hist["indice_str"] = hist["indice"].apply(lambda x: f"{x:.1f}")
        hist["var_str"] = hist["var_diaria"].apply(
            lambda x: f"{_flecha(x)} {x:+.2f}%" if pd.notna(x) else "—"
        )
        st.dataframe(
            hist[["fecha_str", "indice_str", "costo_str", "var_str"]].rename(columns={
                "fecha_str": "Fecha", "indice_str": "Índice",
                "costo_str": "Costo canasta", "var_str": "Var. diaria",
            }),
            width="stretch", hide_index=True,
        )

    st.divider()
    st.subheader("Mayores movimientos")

    n_dias = st.select_slider("Ventana", options=[1, 7, 14, 30], value=7, key="ventana_mov")
    fecha_desde = ultima_fecha - pd.Timedelta(days=n_dias)

    precios_hoy = df_precios[df_precios["fecha"] == ultima_fecha.strftime("%Y-%m-%d")].copy()
    precios_ant = df_precios[
        (df_precios["fecha"] <= fecha_desde.strftime("%Y-%m-%d"))
    ].sort_values("fecha").groupby("producto_id").last().reset_index()

    if precios_ant.empty or precios_hoy.empty:
        st.info(f"No hay suficientes datos para comparar {n_dias} días atrás.", icon="ℹ️")
    else:
        merged = precios_hoy.merge(
            precios_ant[["producto_id", "precio_lista", "fecha"]],
            on="producto_id", suffixes=("_hoy", "_ant"),
        )
        merged["variacion_pct"] = (
            (merged["precio_lista_hoy"] - merged["precio_lista_ant"])
            / merged["precio_lista_ant"] * 100
        ).round(1)
        merged["variacion_abs"] = (merged["precio_lista_hoy"] - merged["precio_lista_ant"]).round(0)

        col_sub, col_baj = st.columns(2)

        with col_sub:
            st.markdown("#### ▲ Mayores subas")
            subas = merged.nlargest(8, "variacion_pct")[
                ["nombre_original", "categoria", "precio_lista_ant", "precio_lista_hoy", "variacion_pct"]
            ]
            for _, r in subas.iterrows():
                color_rojo = COLORES["rojo"]
                html = (
                    f"**{r['nombre_original'][:40]}**  \n"
                    f"<span style='color:{color_rojo};font-size:18px'>▲ {r['variacion_pct']:+.1f}%</span>"
                    f"&nbsp;&nbsp; ${r['precio_lista_ant']:,.0f} → ${r['precio_lista_hoy']:,.0f}"
                )
                st.markdown(html, unsafe_allow_html=True)
                st.divider()

        with col_baj:
            st.markdown("#### ▼ Mayores bajas")
            bajas = merged.nsmallest(8, "variacion_pct")[
                ["nombre_original", "categoria", "precio_lista_ant", "precio_lista_hoy", "variacion_pct"]
            ]
            for _, r in bajas.iterrows():
                color = _color_var(r["variacion_pct"])
                flecha = _flecha(r["variacion_pct"])
                html = (
                    f"**{r['nombre_original'][:40]}**  \n"
                    f"<span style='color:{color};font-size:18px'>{flecha} {r['variacion_pct']:+.1f}%</span>"
                    f"&nbsp;&nbsp; ${r['precio_lista_ant']:,.0f} → ${r['precio_lista_hoy']:,.0f}"
                )
                st.markdown(html, unsafe_allow_html=True)
                st.divider()

    # Eventos detectados
    if not df_eventos.empty:
        st.subheader("Eventos detectados")
        st.dataframe(
            df_eventos[["fecha", "tipo", "nombre_original", "detalle"]].rename(columns={
                "fecha": "Fecha", "tipo": "Tipo",
                "nombre_original": "Producto", "detalle": "Detalle",
            }),
            width="stretch", hide_index=True,
        )


# ============================================================
# TAB 3 — Detalle por Producto
# ============================================================
with tab3:
    st.subheader("Serie histórica por producto")
    st.caption("Precio del producto en cada cadena (match por EAN). "
               "Los supermercados, la categoría y el rango salen de la barra de arriba.")

    # La categoría y las cadenas ya vienen de la barra global; acá sólo queda
    # elegir el producto, que se guarda en el mismo estado compartido para que
    # el comparador con fotos abra en el mismo que se está mirando.
    producto_sel = selector_producto(df_todas, "prod_tab3")

    df_prod = filtrar(df_todas[df_todas["nombre_original"] == producto_sel].copy(),
                      categoria=False)
    df_prod["fecha"] = pd.to_datetime(df_prod["fecha"])
    df_prod = df_prod.sort_values("fecha")

    if df_prod.empty:
        st.info("Elegí al menos una cadena.")
    else:
        # Métricas: precio del último día por cadena + cuál conviene
        ult_fecha = df_prod["fecha"].max()
        hoy = df_prod[df_prod["fecha"] == ult_fecha]
        cols = st.columns(max(len(hoy), 1) + 1)
        barata = hoy.loc[hoy["precio_lista"].idxmin()] if not hoy.empty else None
        for col, (_, r) in zip(cols, hoy.sort_values("precio_lista").iterrows()):
            es_barata = barata is not None and r["fuente"] == barata["fuente"]
            col.metric(r["fuente"].capitalize(), f"${r['precio_lista']:,.0f}",
                       delta="más barata" if es_barata else None, delta_color="off")
        if barata is not None:
            cols[-1].metric("Conviene", barata["fuente"].capitalize(),
                            delta=f"al {ult_fecha.strftime('%d/%m')}", delta_color="off")

        # Serie por cadena (una línea por cadena)
        if df_prod["fecha"].nunique() >= 2:
            fig2 = go.Figure()
            for f, g in df_prod.groupby("fuente"):
                fig2.add_trace(go.Scatter(
                    x=g["fecha"], y=g["precio_lista"], mode="lines+markers", name=f.capitalize(),
                    line=dict(color=COLOR_CADENA.get(f)),
                    hovertemplate=f"<b>{f.capitalize()}</b> %{{x|%d/%m}}<br>$%{{y:,.0f}}<extra></extra>",
                ))
            fig2.update_layout(height=360, xaxis_title=None, yaxis_title="Precio de lista ($)")
            st.plotly_chart(fig2, width="stretch")
        else:
            st.info("Con un solo día de datos todavía no hay serie que graficar. 📅", icon="ℹ️")

        info = df_prod.iloc[0]
        _pu_txt = ""
        if barata is not None:
            _pu = precio_por_unidad(barata["precio_lista"], info["ean"])
            if _pu:
                _pu_txt = f" · Precio por unidad: **${_pu[0]:,.0f}/{_pu[1]}** (en {barata['fuente'].capitalize()})"
        st.caption(f"EAN: `{info['ean']}` · Categoría: {info['categoria']}{_pu_txt}")


# ============================================================
# TAB 4 — Comparador de cadenas
# ============================================================
with tab4:
    st.subheader("¿Dónde conviene comprar la canasta?")
    st.caption(
        "Compara el último precio de cada cadena para el mismo producto exacto (match por EAN). "
        "Los frescos de balanza y las presentaciones que una cadena no stockea no entran en la comparación."
    )

    # Cadenas y categoría salen de la barra global. El rango NO se aplica acá:
    # el comparador mira el último precio de cada cadena, no una serie.
    sel_fuentes = CADENAS_SEL
    dft = filtrar(df_todas, cadenas=False, rango=False)

    if len(sel_fuentes) < 2:
        st.info("Elegí al menos 2 supermercados en la barra de arriba para comparar.", icon="ℹ️")
    else:
        # Último precio por (producto, cadena), sin las cadenas que dejaron de
        # listarlo: un precio viejo no puede ganar una comparación de hoy.
        ult = ultimo_por_cadena(dft, extra=("categoria",))
        piv = ult.pivot_table(
            index=["nombre_original", "categoria"], columns="fuente", values="precio_lista"
        )
        fuentes = [f for f in sorted(sel_fuentes) if f in piv.columns]
        comparables = piv.dropna(subset=fuentes) if len(fuentes) >= 2 else piv.iloc[0:0]

        if comparables.empty:
            st.warning("Aún no hay productos con precio en todas las cadenas el mismo período.", icon="⚠️")
        else:
            # KPIs: costo de la canasta comparable por cadena
            totales = comparables[fuentes].sum()
            mas_barata = totales.idxmin()
            cols = st.columns(len(fuentes) + 1)
            for col, f in zip(cols, fuentes):
                dif = (totales[f] / totales.min() - 1) * 100
                col.metric(
                    label=f"Canasta en {f.capitalize()}",
                    value=f"${totales[f]:,.0f}",
                    delta=("más barata" if f == mas_barata else f"+{dif:.1f}%"),
                    delta_color="off" if f == mas_barata else "inverse",
                )
            cols[-1].metric(
                label="Productos comparados",
                value=f"{len(comparables)}",
                delta=f"la más barata: {mas_barata.capitalize()}",
            )

            st.divider()

            # Gráfico de barras por producto
            comp = comparables.reset_index()
            fig4 = go.Figure()
            # Color por entidad: la cadena conserva el suyo aunque el filtro
            # cambie el set visible (COLOR_CADENA se arma sobre el universo completo).
            paleta = COLOR_CADENA
            for f in fuentes:
                fig4.add_trace(go.Bar(
                    y=comp["nombre_original"].str.slice(0, 38),
                    x=comp[f],
                    name=f.capitalize(),
                    orientation="h",
                    marker_color=paleta.get(f),
                    hovertemplate="<b>%{y}</b><br>" + f.capitalize() + ": $%{x:,.0f}<extra></extra>",
                ))
            fig4.update_layout(
                barmode="group",
                height=max(360, 26 * len(comp)),
                margin=dict(t=20, b=20, l=10),
                xaxis_title="Precio ($)", yaxis_title=None,
                xaxis=dict(gridcolor=COLORES["grilla"]),
                legend=dict(orientation="h", y=1.05),
            )
            st.plotly_chart(fig4, width="stretch")

            # Tabla: dónde conviene cada producto
            tabla = comparables.copy()
            tabla["Más barata"] = tabla[fuentes].idxmin(axis=1).str.capitalize()
            tabla["Dif. %"] = (
                (tabla[fuentes].max(axis=1) - tabla[fuentes].min(axis=1))
                / tabla[fuentes].min(axis=1) * 100
            ).round(1)
            tabla = tabla.reset_index().sort_values("Dif. %", ascending=False)
            cols_fmt = {f: st.column_config.NumberColumn(f.capitalize(), format="$%d") for f in fuentes}
            st.dataframe(
                tabla[["nombre_original", "categoria", *fuentes, "Más barata", "Dif. %"]].rename(
                    columns={"nombre_original": "Producto", "categoria": "Categoría"}
                ),
                width="stretch", hide_index=True,
                column_config=cols_fmt,
            )

    # --- Hallazgos: dispersión de precios ---
    hall = cargar_hallazgos()
    disp = hall.get("dispersion") or {}
    if disp.get("top"):
        st.divider()
        st.subheader("💡 Hallazgo — dispersión de precios")
        st.caption(
            "El mismo producto (match por EAN) puede costar muy distinto según la cadena. "
            "Sobre el precio de lista de la fecha con mayor cobertura."
        )
        h1, h2, h3 = st.columns(3)
        h1.metric("Dispersión media", f"{disp['dispersion_media_pct']:.0f}%")
        peor = disp["top"][0]
        h2.metric("Diferencia máxima", f"{disp['dispersion_maxima_pct']:.0f}%",
                  delta=peor["producto"][:28], delta_color="off")
        h3.metric("Productos analizados", f"{disp['n_productos']}")

        tabla_h = pd.DataFrame(disp["top"]).rename(columns={
            "producto": "Producto", "categoria": "Categoría",
            "precio_min": "Mín", "precio_max": "Máx", "dispersion_pct": "Dif. %",
            "mas_barata": "Más barata", "mas_cara": "Más cara"})
        st.dataframe(
            tabla_h[["Producto", "Categoría", "Mín", "Máx", "Dif. %", "Más barata", "Más cara"]],
            width="stretch", hide_index=True,
            column_config={
                "Mín": st.column_config.NumberColumn("Mín", format="$%d"),
                "Máx": st.column_config.NumberColumn("Máx", format="$%d"),
                "Dif. %": st.column_config.NumberColumn("Dif. %", format="%.1f%%"),
            },
        )

        eventos_h = hall.get("eventos") or []
        if eventos_h:
            st.markdown("**Eventos detectados** (reduflación / cambios de presentación):")
            ev_df = pd.DataFrame(eventos_h).rename(columns={
                "fecha": "Fecha", "tipo": "Tipo", "producto": "Producto", "detalle": "Detalle"})
            st.dataframe(ev_df, width="stretch", hide_index=True)

    # --- Precio por unidad ($/kg-litro) ---
    st.divider()
    st.subheader("📏 Precio por unidad — dónde está el kg / litro más barato")
    st.caption("Normaliza el precio por contenido, para comparar más allá del tamaño del envase. "
               "El contenido se toma de la canasta de referencia.")
    base_lbl = {"kg": "$/kg", "L": "$/litro", "un": "$/unidad"}
    base_sel = st.radio("Base", list(base_lbl), format_func=lambda b: base_lbl[b],
                        horizontal=True, key="base_unidad")

    ult_u = ultimo_por_cadena(df_todas, extra=("ean",))
    filas_u = []
    for _, r in ult_u.iterrows():
        pu = precio_por_unidad(r["precio_lista"], r["ean"])
        if pu and pu[1] == base_sel:
            filas_u.append({"Producto": r["nombre_original"], "pu": pu[0], "Cadena": r["fuente"].capitalize()})
    if filas_u:
        dfu = pd.DataFrame(filas_u)
        # cadena más barata por producto
        barato = dfu.loc[dfu.groupby("Producto")["pu"].idxmin()].sort_values("pu").reset_index(drop=True)
        c1, c2 = st.columns([2, 3])
        with c1:
            mas = barato.iloc[0]
            st.metric(f"Más barato por {base_sel}", f"${mas['pu']:,.0f}",
                      delta=f"{mas['Producto'][:26]} · {mas['Cadena']}", delta_color="off")
            st.caption(f"{len(barato)} productos medidos en {base_lbl[base_sel]}.")
        with c2:
            fig_u = go.Figure(go.Bar(
                x=barato["pu"].head(10)[::-1], y=barato["Producto"].str.slice(0, 30).head(10)[::-1],
                orientation="h", marker_color=COLORES["cyan"],
                hovertemplate="%{y}<br>" + base_lbl[base_sel] + " $%{x:,.0f}<extra></extra>",
            ))
            fig_u.update_layout(height=320, xaxis_title=base_lbl[base_sel], yaxis_title=None)
            st.plotly_chart(fig_u, width="stretch")
        tabla_u = barato.rename(columns={"pu": base_lbl[base_sel], "Cadena": "Más barata"})
        st.dataframe(
            tabla_u[["Producto", base_lbl[base_sel], "Más barata"]],
            width="stretch", hide_index=True,
            column_config={base_lbl[base_sel]: st.column_config.NumberColumn(base_lbl[base_sel], format="$%d")},
        )
    else:
        st.info(f"No hay productos medibles en {base_lbl[base_sel]} todavía.", icon="ℹ️")


# ============================================================
# TAB 5 — Proyección & Contexto (v3)
# ============================================================
with tab5:
    # --- Proyección del índice ---
    st.subheader("Proyección del índice")
    fc = cargar_forecast()
    estado = fc.get("estado")

    if estado == "ok" and fc.get("forecast"):
        hist = pd.DataFrame(fc["historia"])
        hist["fecha"] = pd.to_datetime(hist["fecha"])
        fore = pd.DataFrame(fc["forecast"])
        fore["fecha"] = pd.to_datetime(fore["fecha"])
        st.caption(f"Modelo Prophet · proyección a {fc.get('horizonte_dias')} días · banda = intervalo de confianza.")
        figf = go.Figure()
        figf.add_trace(go.Scatter(x=fore["fecha"], y=fore["yhat_upper"], mode="lines",
                                  line=dict(width=0), showlegend=False, hoverinfo="skip"))
        figf.add_trace(go.Scatter(x=fore["fecha"], y=fore["yhat_lower"], mode="lines", fill="tonexty",
                                  fillcolor="rgba(34,211,238,0.14)", line=dict(width=0),
                                  name="Intervalo", hoverinfo="skip"))
        figf.add_trace(go.Scatter(x=hist["fecha"], y=hist["indice"], mode="lines+markers", name="Histórico",
                                  line=dict(color=COLORES["cyan"], width=2.5)))
        figf.add_trace(go.Scatter(x=fore["fecha"], y=fore["yhat"], mode="lines", name="Proyección",
                                  line=dict(color="#c98500", width=2.5, dash="dash")))
        figf.update_layout(height=380, margin=dict(t=20, b=20),
                           yaxis_title="Índice (base 100)")
        st.plotly_chart(figf, width="stretch")
    else:
        n, need = fc.get("dias_historia", 0), fc.get("dias_necesarios", 30)
        st.info(
            f"**Acumulando historia para pronosticar: {n}/{need} días.** "
            "El forecast se activa automáticamente al superar el umbral — no publicamos "
            "proyecciones sobre series demasiado cortas (serían ruido con un intervalo de confianza falso).",
            icon="⏳",
        )
        st.progress(min(n / need, 1.0))
        if estado == "prophet_no_instalado":
            st.warning("Hay datos suficientes pero falta instalar Prophet (`requirements-ml.txt`).", icon="⚙️")

    st.divider()

    # --- Contexto macro: dólar + IPC ---
    st.subheader("Contexto macro")
    reg = cargar_regresores()
    if reg.empty:
        st.caption("Todavía sin datos de regresores. Se ingieren a diario desde el próximo run.")
    else:
        st.caption("Regresores externos para el modelo (dólar diario, IPC mensual). "
                   "La correlación con el índice se activa al acumular historia.")

        # Dólar (diario)
        dolar = reg[reg["serie"].str.startswith("dolar")]
        if not dolar.empty:
            figd = go.Figure()
            etiquetas = {"dolar_oficial": "Dólar oficial", "dolar_blue": "Dólar blue"}
            for serie, g in dolar.groupby("serie"):
                figd.add_trace(go.Scatter(x=g["fecha"], y=g["valor"], mode="lines+markers",
                                         name=etiquetas.get(serie, serie)))
            figd.update_layout(height=280, margin=dict(t=20, b=20),
                              yaxis_title="$ / USD (venta)", legend=dict(orientation="h", y=1.15))
            st.plotly_chart(figd, width="stretch")
            piv_d = dolar.pivot_table(index="fecha", columns="serie", values="valor")
            if {"dolar_oficial", "dolar_blue"}.issubset(piv_d.columns):
                ult = piv_d.dropna().iloc[-1]
                brecha = (ult["dolar_blue"] / ult["dolar_oficial"] - 1) * 100
                c1, c2, c3 = st.columns(3)
                c1.metric("Dólar oficial", f"${ult['dolar_oficial']:,.0f}")
                c2.metric("Dólar blue", f"${ult['dolar_blue']:,.0f}")
                c3.metric("Brecha", f"{brecha:.1f}%")

        # IPC INDEC (mensual) — inflación oficial, para contrastar con nuestro índice
        ipc = reg[reg["serie"] == "ipc"].sort_values("fecha")
        if len(ipc) >= 2:
            st.markdown("**Inflación oficial — IPC INDEC (Nivel General)**")
            ipc = ipc.assign(var=ipc["valor"].pct_change() * 100)
            ult, prev = ipc.iloc[-1], ipc.iloc[-2]
            interanual = None
            if len(ipc) >= 13:
                interanual = (ult["valor"] / ipc.iloc[-13]["valor"] - 1) * 100
            k1, k2 = st.columns(2)
            k1.metric(f"IPC mensual ({ult['fecha'].strftime('%b %Y')})", f"{ult['var']:.1f}%")
            k2.metric("IPC interanual", f"{interanual:.1f}%" if interanual is not None else "—")
            figi = go.Figure(go.Bar(
                x=ipc["fecha"].tail(12), y=ipc["var"].tail(12),
                marker_color="#c98500",
                hovertemplate="%{x|%b %Y}: %{y:.1f}%<extra></extra>",
            ))
            figi.update_layout(height=240, margin=dict(t=10, b=20),
                              yaxis_title="Var. mensual %", )
            st.plotly_chart(figi, width="stretch")

    st.divider()

    # --- Anomalías y eventos ---
    st.subheader("Anomalías y eventos detectados")
    anomalias = fc.get("anomalias", [])
    if anomalias:
        st.markdown("**Movimientos anómalos del índice** (retorno diario fuera de ±2,5σ):")
        st.dataframe(pd.DataFrame(anomalias), width="stretch", hide_index=True)
    if not df_eventos.empty:
        st.markdown("**Eventos a nivel producto** (outliers, reduflación, cambios de presentación):")
        ev = df_eventos[["fecha", "tipo", "nombre_original", "detalle"]].rename(columns={
            "fecha": "Fecha", "tipo": "Tipo", "nombre_original": "Producto", "detalle": "Detalle"})
        st.dataframe(ev.head(50), width="stretch", hide_index=True)
    elif not anomalias:
        st.caption("Sin anomalías ni eventos registrados por ahora.")


# ============================================================
# TAB 6 — Comparar con fotos
# ============================================================
with tab6:
    st.subheader("El mismo producto, en cada supermercado")
    st.caption(
        "Elegí un producto y compará su precio de hoy en cada cadena. El match es por EAN: "
        "es exactamente el mismo artículo, no uno parecido. Las fotos vienen de cada "
        "supermercado."
    )

    # --- Grilla catálogo: portada de la sección ---
    # Una tarjeta por producto de la canasta con su foto, el precio más barato de
    # hoy y qué cadena lo tiene. Es el índice visual: se hace clic y abajo se abre
    # el comparador de ese producto.
    _grid_base = filtrar(df_todas, rango=False)
    if not _grid_base.empty:
        _ult = ultimo_por_cadena(_grid_base)
        # Más barata por producto entre las cadenas elegidas.
        _min = (_ult.sort_values("precio_lista")
                .groupby(["producto_id", "nombre_original"], as_index=False).first()
                .sort_values("nombre_original"))

        # Un producto que ninguna cadena releva hace días sigue en la grilla, pero
        # su precio no es el de hoy: se le pone la fecha para no venderlo como tal.
        _hoy = _grid_base["fecha"].max()

        _imgs = cargar_imagenes()
        _por_prod: dict[int, dict[str, str]] = {}
        for _pid, _g in _imgs.groupby("producto_id"):
            _por_prod[int(_pid)] = dict(zip(_g["fuente"], _g["url"]))

        with st.expander(f"🧺 Ver la canasta completa ({len(_min)} productos)", expanded=False):
            st.caption("Hacé clic en un producto para compararlo abajo.")
            _COLS = 5
            for _i in range(0, len(_min), _COLS):
                _fila = _min.iloc[_i:_i + _COLS]
                for _col, (_, _p) in zip(st.columns(_COLS), _fila.iterrows()):
                    with _col:
                        _u = foto(url_preferida(_por_prod.get(int(_p["producto_id"]), {})), 160)
                        _nombre = str(_p["nombre_original"])
                        if _u:
                            st.markdown(
                                f"<img class='card-foto' src='{_u}' loading='lazy' alt=''>",
                                unsafe_allow_html=True)
                        else:
                            st.markdown("<div class='card-foto sin-foto'>sin foto</div>",
                                        unsafe_allow_html=True)
                        _sello = str(_p["fuente"]).capitalize()
                        if _p["fecha"] != _hoy:
                            _sello += f" · {pd.to_datetime(_p['fecha']):%d-%m}"
                        st.markdown(
                            f"<p class='card-precio'>${_p['precio_lista']:,.0f}"
                            f"<span> · {_sello}</span></p>",
                            unsafe_allow_html=True)
                        st.button(
                            _nombre if len(_nombre) <= 34 else _nombre[:32] + "…",
                            key=f"grid_{int(_p['producto_id'])}",
                            width="stretch",
                            help=_nombre,
                            # El callback corre antes del rerun, así que escribir el
                            # estado acá es seguro: todavía no se instanció el
                            # selectbox que lo lee.
                            on_click=lambda n=_nombre: st.session_state.update(f_producto=n),
                        )

    producto_foto = selector_producto(df_todas, "prod_tab6")

    if producto_foto:
        _pf = filtrar(df_todas[df_todas["nombre_original"] == producto_foto].copy(),
                      categoria=False, rango=False)
        if _pf.empty:
            st.info("Ese producto no está en los supermercados elegidos.", icon="ℹ️")
        else:
            # Último precio de cada cadena para ese producto.
            _pf["fecha"] = pd.to_datetime(_pf["fecha"])
            hoy_pf = (_pf.sort_values("fecha")
                      .groupby("fuente", as_index=False).last()
                      .sort_values("precio_lista"))

            imgs = cargar_imagenes()
            _pid = int(_pf["producto_id"].iloc[0])
            urls = dict(zip(*(lambda d: (d["fuente"], d["url"]))(
                imgs[imgs["producto_id"] == _pid]))) if not imgs.empty else {}

            barato = hoy_pf.iloc[0]
            caro = hoy_pf.iloc[-1]
            brecha = (caro["precio_lista"] / barato["precio_lista"] - 1) * 100

            col_foto, col_precios = st.columns([1, 2])

            with col_foto:
                # Foto de referencia: la de la cadena más barata, o cualquiera que
                # haya. Se pide la miniatura de la CDN, no el original.
                _u = foto(urls.get(barato["fuente"]) or next(iter(urls.values()), None), 320)
                if _u:
                    st.image(_u, width="stretch")
                else:
                    st.markdown(
                        "<div class='sin-foto'>sin foto disponible</div>",
                        unsafe_allow_html=True)
                st.caption(f"**{producto_foto}**")
                _info = _pf.iloc[0]
                if pd.notna(_info.get("ean")):
                    st.caption(f"EAN {_info['ean']} · {str(_info['categoria']).capitalize()}")

            with col_precios:
                for _, r in hoy_pf.iterrows():
                    dif = (r["precio_lista"] / barato["precio_lista"] - 1) * 100
                    # Los empates son frecuentes (varias cadenas al mismo precio de
                    # lista): marcarlos todos evita un "más barata" arbitrario en una
                    # y un "+0.0%" en rojo en las otras, que se leía como que eran
                    # más caras.
                    if len(hoy_pf) == 1:
                        # Una sola cadena con este EAN: no hay nada que comparar.
                        etiqueta = "<span class='pill-igual'>único precio</span>"
                    elif abs(dif) >= 0.05:
                        etiqueta = f"<span class='pill-dif'>+{dif:.1f}%</span>"
                    elif hoy_pf["precio_lista"].nunique() == 1:
                        etiqueta = "<span class='pill-igual'>igual</span>"
                    else:
                        etiqueta = "<span class='pill-barata'>más barata</span>"
                    _thumb = foto(urls.get(r["fuente"]), 80)
                    _img = (f"<img src='{_thumb}' loading='lazy' alt=''>" if _thumb
                            else "<div class='thumb-vacia'></div>")
                    st.markdown(
                        f"""<div class='fila-cadena'>
                              {_img}
                              <span class='cadena' style='border-left:3px solid {COLOR_CADENA.get(r["fuente"], "#888")}'>
                                {r["fuente"].capitalize()}</span>
                              <span class='precio'>${r["precio_lista"]:,.0f}</span>
                              {etiqueta}
                            </div>""",
                        unsafe_allow_html=True,
                    )

                if len(hoy_pf) >= 2:
                    st.markdown(
                        f"<p class='brecha'>Entre {barato['fuente'].capitalize()} y "
                        f"{caro['fuente'].capitalize()} hay <b>{brecha:.1f}%</b> de diferencia "
                        f"por el mismo producto — ${caro['precio_lista'] - barato['precio_lista']:,.0f}"
                        f" de bolsillo.</p>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption(
                        "Sólo una cadena tiene este EAN hoy: no hay comparación posible. "
                        "Las demás no lo stockean o devuelven un sustituto con otro código."
                    )

            _faltan = [f for f in CADENAS_SEL if f not in set(hoy_pf["fuente"])]
            if _faltan:
                st.caption("Sin precio hoy en: " + ", ".join(f.capitalize() for f in _faltan))


# ---------------------------------------------------------------------------
# Acerca de y metodología
# ---------------------------------------------------------------------------

st.divider()
with st.expander("ℹ️ Acerca de Atlas Precios y metodología"):
    st.markdown(
        """
**Qué es.** Todos los días a las 06:00 (hora Argentina) un robot releva los precios de una
**canasta fija de 45 productos básicos** en **Coto, Día, Carrefour y Jumbo**, y los guarda en
una base histórica. Con esos datos construyo un índice de inflación propio con resolución
**diaria** — algo que no existe públicamente.

**Nowcast de la inflación.** El IPC oficial de INDEC se publica con ~6 semanas de rezago. Como
la Canasta Atlas mide el mes en curso en tiempo real, funciona como un *nowcast*: adelanta la
cifra oficial.

**Cómo se construye el índice.**
- **Base 100** en el primer día; la variación refleja el costo de comprar la misma canasta.
- **Canasta fija**: solo productos con precio *todos los días* de la cadena de referencia (Coto),
  así ningún producto que aparece o desaparece mueve el índice por composición.
- Se usa el **precio de lista** (no el promocional).
- **Total + 6 categorías**, cada una con su propio índice.

**Comparador entre cadenas.** El mismo producto se identifica por **EAN** (código de barras), que
es el mismo en todas las cadenas. Los frescos de balanza (queso x kg, pollo) no cross-matchean y
quedan fuera de la comparación, a propósito.

**Fuentes.** Precios: APIs públicas de Coto (Constructor.io) y VTEX (Día/Carrefour/Jumbo).
Contexto: dólar oficial/blue (dolarapi.com) e IPC INDEC (API de datos.gob.ar).

**Límites.** Es un relevamiento de baja frecuencia (1 vez por día) sobre precios públicos, sin
datos personales. La serie recién arranca: el pronóstico y el contraste mensual con el IPC se
activan solos al acumular historia.

Proyecto de portfolio · datos bajo licencia **CC BY 4.0** · no afiliado a ninguna cadena.
        """
    )

# ---------------------------------------------------------------------------
# Datos abiertos
# ---------------------------------------------------------------------------

st.divider()
PUBLIC_DIR = DB_PATH.parent / "public"
with st.expander("📂 Datos abiertos — descargá la serie completa (CSV / JSON)"):
    st.caption(
        "Datos propios bajo licencia CC BY 4.0. También accesibles como API estática "
        "vía las URLs *raw* de GitHub (`data/public/`)."
    )
    archivos = [
        ("indice_canasta.csv", "Índice base 100 diario: total + 6 categorías"),
        ("precios.csv", "Serie completa de precios (todas las cadenas)"),
        ("comparador.csv", "Último precio por cadena de cada producto"),
    ]
    cols = st.columns(len(archivos))
    for col, (nombre, desc) in zip(cols, archivos):
        ruta = PUBLIC_DIR / nombre
        if ruta.exists():
            col.download_button(
                f"⬇️ {nombre}", data=ruta.read_bytes(), file_name=nombre,
                mime="text/csv", width="stretch",
            )
            col.caption(desc)
        else:
            col.caption(f"{nombre} — se genera con el pipeline")


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown(
    "<div class='footer'>Atlas Analytics · datos propios relevados diariamente · "
    "no afiliado a ninguna cadena de supermercados</div>",
    unsafe_allow_html=True,
)
