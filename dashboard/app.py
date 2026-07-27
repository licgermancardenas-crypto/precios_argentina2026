"""
Dashboard Atlas Precios — Streamlit
5 vistas: Resumen (índice + nowcast), Categorías y movimientos, Por Producto,
Comparador de cadenas, Proyección & Contexto.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from pipeline.unidades import precio_por_unidad

# ---------------------------------------------------------------------------
# Identidad visual — paleta de marca (una sola fuente de verdad)
# ---------------------------------------------------------------------------
COLORES = {
    "navy":   "#1a2744",
    "gold":   "#c9a227",
    "rojo":   "#d64550",
    "gris":   "#f2f2f2",
    "verde":  "#2e9e6b",
    "azul":   "#4a7fb5",
    "texto":  "#212529",
    "grilla": "#eef0f3",
}
_FUENTE = "IBM Plex Sans, sans-serif"
# Colorway de marca para series múltiples (categorías, comparador, etc.)
_COLORWAY = [COLORES["navy"], COLORES["gold"], COLORES["verde"], COLORES["azul"],
             COLORES["rojo"], "#8a6d3b", "#5a6472", "#9aa4b2"]

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

# Template de Plotly de marca — se aplica a TODOS los gráficos automáticamente
# (fuente, paleta de series, grillas, hover, márgenes).
pio.templates["atlas"] = go.layout.Template(
    layout=dict(
        font=dict(family=_FUENTE, color=COLORES["texto"], size=13),
        colorway=_COLORWAY,
        paper_bgcolor="white",
        plot_bgcolor="white",
        xaxis=dict(gridcolor=COLORES["grilla"], zerolinecolor=COLORES["grilla"], zeroline=False),
        yaxis=dict(gridcolor=COLORES["grilla"], zerolinecolor=COLORES["grilla"], zeroline=False),
        hoverlabel=dict(bgcolor="white", bordercolor=COLORES["grilla"], font=dict(family=_FUENTE, size=12)),
        margin=dict(t=30, b=20, l=10, r=10),
        legend=dict(orientation="h", y=1.12, x=0),
        colorscale=dict(sequential=[[0, "#eaf0f6"], [1, COLORES["navy"]]]),
    )
)
pio.templates.default = "atlas"

# Estilos de la app (fuente + tarjetas de métrica + tabs + limpieza de chrome)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
    html, body, [class*="css"], .stApp, [data-testid="stMarkdownContainer"] {
        font-family: 'IBM Plex Sans', sans-serif;
    }
    h1, h2, h3 { color: #1a2744; font-weight: 600; letter-spacing: -0.01em; }
    h1 { font-weight: 700; }

    /* Tarjetas de métrica */
    [data-testid="stMetric"] {
        background: #f8f9fb;
        border: 1px solid #eceef2;
        border-left: 4px solid #1a2744;
        border-radius: 10px;
        padding: 14px 16px 12px;
    }
    [data-testid="stMetricLabel"] p { color: #5a6472; font-weight: 500; font-size: 0.8rem; }
    [data-testid="stMetricValue"] { color: #1a2744; font-weight: 600; }

    /* Tabs */
    [data-baseweb="tab-list"] { gap: 2px; border-bottom: 1px solid #eceef2; }
    button[data-baseweb="tab"] { font-weight: 500; }
    button[data-baseweb="tab"][aria-selected="true"] { color: #1a2744; }

    /* Limpieza del chrome default de Streamlit */
    #MainMenu, header [data-testid="stToolbar"] { visibility: hidden; }
    footer { visibility: hidden; }
    .block-container { padding-top: 2.2rem; }
    .footer { text-align: center; color: #9aa4b2; font-size: 12px; margin-top: 32px; }
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


def _costo_canasta_fija(df: pd.DataFrame) -> pd.Series:
    """
    Costo diario de una canasta FIJA: solo productos con precio todos los días.
    Evita artefactos de composición (un producto que aparece/desaparece no mueve
    el índice). Misma metodología que el export público (pipeline/export.py).
    """
    piv = df.pivot_table(index="fecha", columns="nombre_original", values="precio_lista").sort_index()
    completos = piv.dropna(axis=1)
    return completos.sum(axis=1)


@st.cache_data(ttl=3600)
def calcular_indice(df: pd.DataFrame) -> pd.DataFrame:
    """Índice Canasta Atlas total (base 100 en primer día), canasta fija."""
    if df.empty:
        return pd.DataFrame()

    costos = _costo_canasta_fija(df)
    idx = costos.reset_index()
    idx.columns = ["fecha", "costo_canasta"]
    idx["fecha"] = pd.to_datetime(idx["fecha"])
    idx = idx.sort_values("fecha")

    base = idx["costo_canasta"].iloc[0]
    idx["indice"] = (idx["costo_canasta"] / base * 100).round(2)
    idx["var_diaria"] = idx["costo_canasta"].pct_change().mul(100).round(2)
    return idx


@st.cache_data(ttl=3600)
def calcular_indice_categoria(df: pd.DataFrame) -> pd.DataFrame:
    """Índice base 100 por categoría (canasta fija). Columnas: fecha, categoria, indice."""
    if df.empty:
        return pd.DataFrame()

    filas = []
    for cat, g in df.groupby("categoria"):
        costos = _costo_canasta_fija(g)
        if costos.empty:
            continue
        base = costos.iloc[0]
        for fecha, costo in costos.items():
            filas.append({"fecha": fecha, "categoria": cat, "indice": round(costo / base * 100, 2)})
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
    if val is None:
        return "black"
    return COLORES["rojo"] if val > 0 else (COLORES["verde"] if val < 0 else "black")


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

col_logo, col_titulo = st.columns([1, 9])
with col_logo:
    st.markdown("<div style='font-size:52px; line-height:1.2'>📊</div>", unsafe_allow_html=True)
with col_titulo:
    st.title("Atlas Precios")
    st.markdown(
        "Relevo **4 supermercados** argentinos todos los días y construyo un índice de "
        "inflación propio con resolución diaria — que **adelanta al IPC oficial**. "
        "Todo automatizado, reproducible y con datos abiertos."
    )

# Estado del relevamiento (control de calidad)
_qc = cargar_qc()
if _qc.get("cadenas"):
    _ok = sum(1 for c in _qc["cadenas"].values() if c["estado"] == "ok")
    _tot = len(_qc["cadenas"])
    _icono = {"ok": "🟢", "warning": "🟡", "critical": "🔴"}.get(_qc["estado_global"], "⚪")
    _detalle = "" if _qc["estado_global"] == "ok" else " · " + "; ".join(_qc.get("alertas", []))
    st.caption(f"{_icono} Relevamiento {_qc.get('fecha', '—')}: {_ok}/{_tot} cadenas OK{_detalle}")

st.divider()

# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

# Cadena de referencia para el índice y las vistas históricas (evita doble conteo multi-cadena).
FUENTE_REFERENCIA = "coto"

df_todas, df_eventos = cargar_datos()

if df_todas.empty:
    st.warning("Base de datos no encontrada o sin datos. Ejecutá el pipeline primero.", icon="⚠️")
    st.stop()

# Las vistas históricas (índice, movimientos, producto) usan solo la cadena de referencia.
df_precios = df_todas[df_todas["fuente"] == FUENTE_REFERENCIA]

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

with k1:
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
    st.metric(label="Variación mensual", value=delta_30 if hace_30 else "—", delta=None)

with k4:
    st.metric(label="Días de historia", value=f"{dias_de_datos}", delta=f"desde {primera_fecha.strftime('%d/%m/%Y')}")

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📊 Resumen", "📈 Categorías y movimientos", "🔍 Por Producto",
     "🏪 Comparador de cadenas", "📉 Proyección & Contexto"]
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
                                  name="Canasta Atlas", marker_color=COLORES["navy"]))
            figm.add_trace(go.Bar(x=dfm["mes"], y=dfm["var_ipc_pct"],
                                  name="IPC oficial", marker_color=COLORES["gold"]))
            figm.update_layout(barmode="group", height=300, margin=dict(t=20, b=20),
                               yaxis_title="Var. mensual %", plot_bgcolor="white",
                               xaxis=dict(gridcolor="#eee"), yaxis=dict(gridcolor="#eee"),
                               legend=dict(orientation="h", y=1.15))
            st.plotly_chart(figm, use_container_width=True)
        else:
            st.info(
                f"El contraste mensual completo (Canasta vs IPC) se activa al cerrar "
                f"el primer mes completo de historia. Por ahora, nowcast de {mec['mes']}.",
                icon="⏳",
            )
        st.divider()

    # Índice Canasta Atlas (base 100)
    st.subheader("Índice Canasta Atlas")
    st.caption("Base 100 = primer día de datos. Canasta fija (productos con serie completa) sobre la cadena de referencia.")
    if len(idx) < 2:
        st.info("Necesitás al menos 2 días de datos para ver la evolución.", icon="ℹ️")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=idx["fecha"], y=idx["indice"], mode="lines+markers", name="Índice",
            line=dict(color=COLORES["navy"], width=2.5), marker=dict(size=5),
            hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Índice: %{y:.1f}<extra></extra>",
        ))
        fig.add_hline(y=100, line_dash="dot", line_color=COLORES["gold"], line_width=1.5,
                      annotation_text="Base 100", annotation_position="left")
        fig.update_layout(height=380, xaxis_title=None, yaxis_title="Índice (base 100)")
        st.plotly_chart(fig, use_container_width=True)


# ============================================================
# TAB 2 — Categorías y movimientos
# ============================================================
with tab2:
    # Índice por categoría
    idx_cat = calcular_indice_categoria(df_precios)
    if not idx_cat.empty and idx_cat["fecha"].nunique() > 1:
        st.subheader("Índice por categoría")
        st.caption("Cada categoría en base 100 a su primer día. Muestra qué rubros empujan la canasta.")

        colg, colb = st.columns([3, 2])
        with colg:
            figc = go.Figure()
            for i, (cat, g) in enumerate(idx_cat.groupby("categoria")):
                figc.add_trace(go.Scatter(
                    x=g["fecha"], y=g["indice"], mode="lines+markers", name=cat.capitalize(),
                    line=dict(color=_COLORWAY[i % len(_COLORWAY)], width=2), marker=dict(size=4),
                    hovertemplate=f"<b>{cat.capitalize()}</b> %{{x|%d/%m}}<br>%{{y:.1f}}<extra></extra>",
                ))
            figc.add_hline(y=100, line_dash="dot", line_color="#bbb", line_width=1)
            figc.update_layout(height=340, xaxis_title=None, yaxis_title="Índice (base 100)",
                               legend=dict(font=dict(size=11)))
            st.plotly_chart(figc, use_container_width=True)
        with colb:
            ultimo_cat = idx_cat.sort_values("fecha").groupby("categoria").last().reset_index()
            ultimo_cat["var"] = (ultimo_cat["indice"] - 100).round(2)
            ultimo_cat = ultimo_cat.sort_values("var", ascending=False)
            figb = go.Figure(go.Bar(
                x=ultimo_cat["var"], y=ultimo_cat["categoria"].str.capitalize(), orientation="h",
                marker_color=[COLORES["rojo"] if v > 0 else COLORES["verde"] for v in ultimo_cat["var"]],
                hovertemplate="%{y}: %{x:+.1f}%<extra></extra>",
            ))
            figb.update_layout(height=340, xaxis_title="Var. acumulada %", yaxis_title=None)
            st.plotly_chart(figb, use_container_width=True)

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
            use_container_width=True, hide_index=True,
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
                color = COLORES["verde"] if r["variacion_pct"] < 0 else "black"
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
            use_container_width=True, hide_index=True,
        )


# ============================================================
# TAB 3 — Detalle por Producto
# ============================================================
with tab3:
    st.subheader("Serie histórica por producto")
    st.caption("Precio del producto en cada cadena (match por EAN). Filtrá por categoría y cadenas.")

    # --- Filtros ---
    cats_p = ["Todas"] + [c.capitalize() for c in sorted(df_todas["categoria"].unique())]
    fp1, fp2 = st.columns([1, 2])
    cat_p = fp1.selectbox("Categoría", cats_p, key="cat_producto")
    base_p = df_todas if cat_p == "Todas" else df_todas[df_todas["categoria"] == cat_p.lower()]
    productos_lista = sorted(base_p["nombre_original"].dropna().unique())
    producto_sel = fp2.selectbox("Producto", productos_lista, key="prod_sel")

    df_prod = df_todas[df_todas["nombre_original"] == producto_sel].copy()
    df_prod["fecha"] = pd.to_datetime(df_prod["fecha"])
    cadenas_prod = sorted(df_prod["fuente"].unique())
    sel_cad = st.multiselect("Cadenas", cadenas_prod, default=cadenas_prod,
                             format_func=str.capitalize, key="cad_producto")
    df_prod = df_prod[df_prod["fuente"].isin(sel_cad)].sort_values("fecha")

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
                    hovertemplate=f"<b>{f.capitalize()}</b> %{{x|%d/%m}}<br>$%{{y:,.0f}}<extra></extra>",
                ))
            fig2.update_layout(height=360, xaxis_title=None, yaxis_title="Precio de lista ($)")
            st.plotly_chart(fig2, use_container_width=True)
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

    # --- Filtros ---
    fuentes_disp = sorted(df_todas["fuente"].unique())
    cats_c = ["Todas"] + [c.capitalize() for c in sorted(df_todas["categoria"].unique())]
    fcol1, fcol2 = st.columns([2, 1])
    sel_fuentes = fcol1.multiselect("Cadenas a comparar", fuentes_disp, default=fuentes_disp,
                                    format_func=str.capitalize, key="cad_comparador")
    cat_c = fcol2.selectbox("Categoría", cats_c, key="cat_comparador")
    dft = df_todas if cat_c == "Todas" else df_todas[df_todas["categoria"] == cat_c.lower()]

    if len(sel_fuentes) < 2:
        st.info("Elegí al menos 2 cadenas para comparar.", icon="ℹ️")
    else:
        # Último precio por (producto, cadena)
        ult = (
            dft.sort_values("fecha")
            .groupby(["producto_id", "nombre_original", "categoria", "fuente"], as_index=False)
            .last()
        )
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
            _ciclo = [COLORES["navy"], COLORES["gold"], COLORES["verde"], COLORES["rojo"]]
            paleta = {f: _ciclo[i % len(_ciclo)] for i, f in enumerate(fuentes)}
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
                plot_bgcolor="white", xaxis=dict(gridcolor="#eee"),
                legend=dict(orientation="h", y=1.05),
            )
            st.plotly_chart(fig4, use_container_width=True)

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
                use_container_width=True, hide_index=True,
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
            use_container_width=True, hide_index=True,
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
            st.dataframe(ev_df, use_container_width=True, hide_index=True)

    # --- Precio por unidad ($/kg-litro) ---
    st.divider()
    st.subheader("📏 Precio por unidad — dónde está el kg / litro más barato")
    st.caption("Normaliza el precio por contenido, para comparar más allá del tamaño del envase. "
               "El contenido se toma de la canasta de referencia.")
    base_lbl = {"kg": "$/kg", "L": "$/litro", "un": "$/unidad"}
    base_sel = st.radio("Base", list(base_lbl), format_func=lambda b: base_lbl[b],
                        horizontal=True, key="base_unidad")

    ult_u = (df_todas.sort_values("fecha")
             .groupby(["producto_id", "nombre_original", "ean", "fuente"], as_index=False).last())
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
                orientation="h", marker_color=COLORES["navy"],
                hovertemplate="%{y}<br>" + base_lbl[base_sel] + " $%{x:,.0f}<extra></extra>",
            ))
            fig_u.update_layout(height=320, xaxis_title=base_lbl[base_sel], yaxis_title=None)
            st.plotly_chart(fig_u, use_container_width=True)
        tabla_u = barato.rename(columns={"pu": base_lbl[base_sel], "Cadena": "Más barata"})
        st.dataframe(
            tabla_u[["Producto", base_lbl[base_sel], "Más barata"]],
            use_container_width=True, hide_index=True,
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
                                  fillcolor="rgba(201,162,39,0.18)", line=dict(width=0),
                                  name="Intervalo", hoverinfo="skip"))
        figf.add_trace(go.Scatter(x=hist["fecha"], y=hist["indice"], mode="lines+markers", name="Histórico",
                                  line=dict(color=COLORES["navy"], width=2.5)))
        figf.add_trace(go.Scatter(x=fore["fecha"], y=fore["yhat"], mode="lines", name="Proyección",
                                  line=dict(color=COLORES["gold"], width=2.5, dash="dash")))
        figf.update_layout(height=380, margin=dict(t=20, b=20), plot_bgcolor="white",
                           yaxis_title="Índice (base 100)", xaxis=dict(gridcolor="#eee"), yaxis=dict(gridcolor="#eee"))
        st.plotly_chart(figf, use_container_width=True)
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
            figd.update_layout(height=280, margin=dict(t=20, b=20), plot_bgcolor="white",
                              yaxis_title="$ / USD (venta)", xaxis=dict(gridcolor="#eee"),
                              yaxis=dict(gridcolor="#eee"), legend=dict(orientation="h", y=1.15))
            st.plotly_chart(figd, use_container_width=True)
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
                marker_color=COLORES["navy"],
                hovertemplate="%{x|%b %Y}: %{y:.1f}%<extra></extra>",
            ))
            figi.update_layout(height=240, margin=dict(t=10, b=20), plot_bgcolor="white",
                              yaxis_title="Var. mensual %", xaxis=dict(gridcolor="#eee"),
                              yaxis=dict(gridcolor="#eee"))
            st.plotly_chart(figi, use_container_width=True)

    st.divider()

    # --- Anomalías y eventos ---
    st.subheader("Anomalías y eventos detectados")
    anomalias = fc.get("anomalias", [])
    if anomalias:
        st.markdown("**Movimientos anómalos del índice** (retorno diario fuera de ±2,5σ):")
        st.dataframe(pd.DataFrame(anomalias), use_container_width=True, hide_index=True)
    if not df_eventos.empty:
        st.markdown("**Eventos a nivel producto** (outliers, reduflación, cambios de presentación):")
        ev = df_eventos[["fecha", "tipo", "nombre_original", "detalle"]].rename(columns={
            "fecha": "Fecha", "tipo": "Tipo", "nombre_original": "Producto", "detalle": "Detalle"})
        st.dataframe(ev.head(50), use_container_width=True, hide_index=True)
    elif not anomalias:
        st.caption("Sin anomalías ni eventos registrados por ahora.")


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
                mime="text/csv", use_container_width=True,
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
