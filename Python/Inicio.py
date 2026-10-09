import streamlit as st

st.set_page_config(
    page_title="Catálogo Arquitectura de Datos DPJ",
    page_icon="🔍",
    layout="wide"
)

# =====================================
# CABECERA
# =====================================

st.markdown("<br><br>", unsafe_allow_html=True)

st.markdown(
    """
    <h1 style='text-align:center;color:#1a73e8;'>
        Catálogo Arquitectura de Datos DPJ
    </h1>
    """,
    unsafe_allow_html=True
)

st.markdown(
    """
    <p style='text-align:center;font-size:20px;color:gray;'>
        Explorador de Metadatos • Migración AS400 → Azure SQL
    </p>
    """,
    unsafe_allow_html=True
)

st.markdown("<br>", unsafe_allow_html=True)


# =====================================
# ACCESOS RAPIDOS
# =====================================

st.subheader("🚀 Accesos rápidos")

c1, c2, c3 = st.columns(3)

with c1:
    st.page_link(
        "pages/01_Dashboard.py",
        label="📊 Dashboard"
    )

with c2:
    st.page_link(
        "pages/02_Diccionario.py",
        label="📖 Diccionario"
    )

with c3:
    st.page_link(
        "pages/06_Busqueda_Global.py",
        label="🔍 Búsqueda Global"
    )

st.markdown("---")

