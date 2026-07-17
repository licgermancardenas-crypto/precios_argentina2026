"""
Dashboard Atlas Precios — Streamlit
Fase 4: placeholder. Las 3 vistas se implementan cuando haya datos.
"""

import streamlit as st

st.set_page_config(
    page_title="Atlas Precios",
    page_icon="📊",
    layout="wide",
)

st.title("Atlas Precios")
st.caption("Monitor de precios de supermercados argentinos · Atlas Analytics")

st.info(
    "Dashboard en construcción. "
    "Volvé cuando el pipeline tenga al menos 7 días de datos.",
    icon="🔧",
)

st.markdown(
    """
    **Próximas vistas:**
    1. Índice Canasta Atlas — evolución del costo total (base 100)
    2. Top movimientos — mayores subas y bajas de la semana
    3. Detalle por producto — serie histórica individual
    """
)
