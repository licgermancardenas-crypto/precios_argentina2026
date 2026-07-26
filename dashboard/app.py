"""
Dashboard Atlas Precios — Streamlit
3 vistas: Índice Canasta, Top Movimientos, Detalle por producto.
"""

from __future__ import annotations

import json
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
    ["📈 Índice Canasta", "🔥 Top Movimientos", "🔍 Por Producto",
     "🏪 Comparador de cadenas", "📉 Proyección & Contexto"]
)


# ============================================================
# TAB 1 — Índice Canasta
# ============================================================
with tab1:
    st.subheader("Índice Canasta Atlas")
    st.caption("Base 100 = primer día de datos. Canasta fija (productos con serie completa) sobre la cadena de referencia.")

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

    # Índices por categoría
    idx_cat = calcular_indice_categoria(df_precios)
    if not idx_cat.empty and idx_cat["fecha"].nunique() > 1:
        st.subheader("Índice por categoría")
        st.caption("Cada categoría en base 100 a su primer día. Muestra qué rubros empujan la canasta.")

        colg, colb = st.columns([3, 2])
        with colg:
            figc = go.Figure()
            paleta_cat = px.colors.qualitative.Set2
            for i, (cat, g) in enumerate(idx_cat.groupby("categoria")):
                figc.add_trace(go.Scatter(
                    x=g["fecha"], y=g["indice"], mode="lines+markers", name=cat.capitalize(),
                    line=dict(color=paleta_cat[i % len(paleta_cat)], width=2), marker=dict(size=4),
                    hovertemplate=f"<b>{cat.capitalize()}</b> %{{x|%d/%m}}<br>%{{y:.1f}}<extra></extra>",
                ))
            figc.add_hline(y=100, line_dash="dot", line_color="#bbb", line_width=1)
            figc.update_layout(
                height=340, margin=dict(t=20, b=20), xaxis_title=None, yaxis_title="Índice (base 100)",
                plot_bgcolor="white", xaxis=dict(gridcolor="#eee"), yaxis=dict(gridcolor="#eee"),
                legend=dict(orientation="h", y=1.12, font=dict(size=11)),
            )
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
            figb.update_layout(
                height=340, margin=dict(t=20, b=20), xaxis_title="Var. acumulada %", yaxis_title=None,
                plot_bgcolor="white", xaxis=dict(gridcolor="#eee"),
            )
            st.plotly_chart(figb, use_container_width=True)

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


# ============================================================
# TAB 4 — Comparador de cadenas
# ============================================================
with tab4:
    st.subheader("¿Dónde conviene comprar la canasta?")
    st.caption(
        "Compara el último precio de cada cadena para el mismo producto exacto (match por EAN). "
        "Los frescos de balanza y las presentaciones que una cadena no stockea no entran en la comparación."
    )

    fuentes = sorted(df_todas["fuente"].unique())
    if len(fuentes) < 2:
        st.info(
            "Todavía hay una sola cadena en la base. El comparador se activa cuando entra la segunda.",
            icon="ℹ️",
        )
    else:
        # Último precio por (producto, cadena)
        ult = (
            df_todas.sort_values("fecha")
            .groupby(["producto_id", "nombre_original", "categoria", "fuente"], as_index=False)
            .last()
        )
        piv = ult.pivot_table(
            index=["nombre_original", "categoria"], columns="fuente", values="precio_lista"
        )
        comparables = piv.dropna(subset=fuentes)  # producto presente en TODAS las cadenas

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


# ============================================================
# TAB 5 — Proyección & Contexto (v3)
# ============================================================
with tab5:
    # --- Proyección del índice ---
    st.subheader("Proyección del índice")
    fc = cargar_forecast()
    estado = fc.get("estado")

    if estado == "ok" and fc.get("forecast"):
        hist = pd.DataFrame(fc["historia"]); hist["fecha"] = pd.to_datetime(hist["fecha"])
        fore = pd.DataFrame(fc["forecast"]); fore["fecha"] = pd.to_datetime(fore["fecha"])
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

    # --- Contexto: dólar ---
    st.subheader("Contexto macro — dólar")
    reg = cargar_regresores()
    if reg.empty:
        st.caption("Todavía sin datos de regresores. Se ingieren a diario desde el próximo run.")
    else:
        st.caption("Regresor externo para el modelo. La correlación con el índice se activa al acumular historia.")
        figd = go.Figure()
        etiquetas = {"dolar_oficial": "Dólar oficial", "dolar_blue": "Dólar blue"}
        for serie, g in reg.groupby("serie"):
            figd.add_trace(go.Scatter(x=g["fecha"], y=g["valor"], mode="lines+markers",
                                     name=etiquetas.get(serie, serie)))
        figd.update_layout(height=300, margin=dict(t=20, b=20), plot_bgcolor="white",
                          yaxis_title="$ / USD (venta)", xaxis=dict(gridcolor="#eee"), yaxis=dict(gridcolor="#eee"),
                          legend=dict(orientation="h", y=1.12))
        st.plotly_chart(figd, use_container_width=True)
        piv_d = reg.pivot_table(index="fecha", columns="serie", values="valor")
        if {"dolar_oficial", "dolar_blue"}.issubset(piv_d.columns):
            ult = piv_d.dropna().iloc[-1]
            brecha = (ult["dolar_blue"] / ult["dolar_oficial"] - 1) * 100
            c1, c2, c3 = st.columns(3)
            c1.metric("Dólar oficial", f"${ult['dolar_oficial']:,.0f}")
            c2.metric("Dólar blue", f"${ult['dolar_blue']:,.0f}")
            c3.metric("Brecha", f"{brecha:.1f}%")

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
