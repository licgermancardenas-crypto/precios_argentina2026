"""
Dashboard Atlas Precios — Streamlit
3 vistas: Índice Canasta, Top Movimientos, Detalle por producto.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

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

# Estilos
st.markdown("""
<style>
    .metric-card {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 16px;
        border-left: 4px solid #1a2744;
    }
    .footer {text-align:center; color:#aaa; font-size:12px; margin-top:40px;}
    h1 {color: #1a2744;}
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
def calcular_indice(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula el Índice Canasta Atlas (base 100 en primer día)."""
    if df.empty:
        return pd.DataFrame()

    idx = (
        df.groupby("fecha")["precio_lista"]
        .sum()
        .reset_index()
        .rename(columns={"precio_lista": "costo_canasta"})
    )
    idx["fecha"] = pd.to_datetime(idx["fecha"])
    idx = idx.sort_values("fecha")

    base = idx["costo_canasta"].iloc[0]
    idx["indice"] = (idx["costo_canasta"] / base * 100).round(2)
    idx["var_diaria"] = idx["costo_canasta"].pct_change().mul(100).round(2)

    return idx


# ---------------------------------------------------------------------------
# Helpers de UI
# ---------------------------------------------------------------------------

COLORES = {
    "navy":   "#1a2744",
    "gold":   "#c9a227",
    "rojo":   "#E20025",
    "gris":   "#f2f2f2",
    "verde":  "#00a524",
}


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

col_logo, col_titulo = st.columns([1, 8])
with col_titulo:
    st.title("Atlas Precios")
    st.caption("Monitor de inflación de supermercados argentinos · datos propios · actualización diaria")

st.divider()

# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

df_precios, df_eventos = cargar_datos()

if df_precios.empty:
    st.warning("Base de datos no encontrada o sin datos. Ejecutá el pipeline primero.", icon="⚠️")
    st.stop()

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

tab1, tab2, tab3 = st.tabs(["📈 Índice Canasta", "🔥 Top Movimientos", "🔍 Por Producto"])


# ============================================================
# TAB 1 — Índice Canasta
# ============================================================
with tab1:
    st.subheader("Índice Canasta Atlas")
    st.caption("Base 100 = primer día de datos. Refleja el costo de comprar los 26 productos de la canasta.")

    if len(idx) < 2:
        st.info("Necesitás al menos 2 días de datos para ver la evolución.", icon="ℹ️")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=idx["fecha"],
            y=idx["indice"],
            mode="lines+markers",
            name="Índice",
            line=dict(color=COLORES["navy"], width=2.5),
            marker=dict(size=5),
            hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Índice: %{y:.1f}<extra></extra>",
        ))
        fig.add_hline(y=100, line_dash="dot", line_color=COLORES["gold"], line_width=1.5,
                      annotation_text="Base 100", annotation_position="left")
        fig.update_layout(
            height=380, margin=dict(t=20, b=20),
            xaxis_title=None, yaxis_title="Índice (base 100)",
            plot_bgcolor="white",
            xaxis=dict(gridcolor="#eee"), yaxis=dict(gridcolor="#eee"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Tabla de variaciones diarias
    if len(idx) > 1:
        st.subheader("Historial")
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


# ============================================================
# TAB 2 — Top Movimientos
# ============================================================
with tab2:
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

    productos_lista = sorted(df_precios["nombre_original"].unique())
    producto_sel = st.selectbox("Seleccioná un producto", productos_lista)

    df_prod = df_precios[df_precios["nombre_original"] == producto_sel].copy()
    df_prod["fecha"] = pd.to_datetime(df_prod["fecha"])
    df_prod = df_prod.sort_values("fecha")

    if len(df_prod) < 1:
        st.info("Sin datos para este producto.")
    else:
        # Métricas del producto
        precio_actual = df_prod["precio_lista"].iloc[-1]
        precio_min = df_prod["precio_lista"].min()
        precio_max = df_prod["precio_lista"].max()

        m1, m2, m3 = st.columns(3)
        m1.metric("Precio actual", f"${precio_actual:,.0f}")
        m2.metric("Mínimo histórico", f"${precio_min:,.0f}")
        m3.metric("Máximo histórico", f"${precio_max:,.0f}")

        if len(df_prod) >= 2:
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=df_prod["fecha"],
                y=df_prod["precio_lista"],
                mode="lines+markers",
                name="Precio lista",
                line=dict(color=COLORES["navy"], width=2),
                hovertemplate="<b>%{x|%d/%m/%Y}</b><br>$%{y:,.0f}<extra></extra>",
            ))
            if df_prod["precio_promo"].notna().any():
                fig2.add_trace(go.Scatter(
                    x=df_prod["fecha"],
                    y=df_prod["precio_promo"],
                    mode="markers",
                    name="Precio promo",
                    marker=dict(color=COLORES["gold"], size=10, symbol="star"),
                    hovertemplate="<b>Promo %{x|%d/%m/%Y}</b><br>$%{y:,.0f}<extra></extra>",
                ))
            fig2.update_layout(
                height=340, margin=dict(t=20, b=20),
                xaxis_title=None, yaxis_title="Precio ($)",
                plot_bgcolor="white",
                xaxis=dict(gridcolor="#eee"), yaxis=dict(gridcolor="#eee"),
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Con un solo día de datos no hay serie que graficar. Volvé mañana. 📅", icon="ℹ️")

        # Info del producto
        info = df_precios[df_precios["nombre_original"] == producto_sel].iloc[0]
        st.caption(
            f"EAN: `{info['ean']}` · "
            f"Categoría: {info['categoria']} · "
            f"Contenido: {info['contenido_valor']} {info['contenido_unidad']}"
        )


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown(
    "<div class='footer'>Atlas Analytics · datos propios relevados diariamente · "
    "no afiliado a ninguna cadena de supermercados</div>",
    unsafe_allow_html=True,
)
