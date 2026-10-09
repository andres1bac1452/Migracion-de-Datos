import streamlit as st
import pandas as pd
import jpype
import jaydebeapi
from io import BytesIO

# =====================================================
# CONFIGURACION
# =====================================================

HOST = "10.0.12.93"

LIBRERIA = "DPJDAT01"

USUARIO = "anaforer"
PASSWORD = "banco2026"

JVM = r"C:\Program Files\Java\jdk-11\bin\server\jvm.dll"

JAR = r"C:\Users\davidroa\AppData\Roaming\DBeaverData\drivers\maven\maven-central\net.sf.jt400\jt400-21.0.7.jar"

# =====================================================
# STREAMLIT
# =====================================================

st.set_page_config(
    page_title="Catálogo AS400",
    page_icon="📚",
    layout="wide"
)

# =====================================================
# CONEXION
# =====================================================

@st.cache_resource
def iniciar_jvm():

    if not jpype.isJVMStarted():

        jpype.startJVM(
            JVM,
            classpath=[JAR]
        )

@st.cache_resource
def conectar():

    iniciar_jvm()

    conn = jaydebeapi.connect(
        "com.ibm.as400.access.AS400JDBCDriver",
        (
            f"jdbc:as400://{HOST};"
            f"libraries={LIBRERIA};"
            f"user={USUARIO};"
            f"password={PASSWORD};"
            f"prompt=false;"
        )
    )

    return conn

# =====================================================
# EJECUTAR QUERY
# =====================================================

def ejecutar_query(query):

    try:

        conn = conectar()

        cursor = conn.cursor()

        cursor.execute(query)

        filas = cursor.fetchall()

        columnas = [
            str(col[0])
            for col in cursor.description
        ]

        df = pd.DataFrame(
            filas,
            columns=columnas
        )

        return df.astype(str)

    except Exception as e:

        st.error(
            f"Error ejecutando consulta:\n{e}"
        )

        return pd.DataFrame()

# =====================================================
# TABLAS
# =====================================================

@st.cache_data(ttl=3600)
def obtener_tablas():

    query = f"""
    SELECT
        TABLE_NAME
    FROM QSYS2.SYSTABLES
    WHERE TABLE_SCHEMA = '{LIBRERIA}'
    ORDER BY TABLE_NAME
    """

    return ejecutar_query(query)

# =====================================================
# COLUMNAS
# =====================================================

@st.cache_data(ttl=3600)
def obtener_columnas(tabla):

    query = f"""
    SELECT
        ORDINAL_POSITION,
        COLUMN_NAME,
        DATA_TYPE,
        LENGTH,
        NUMERIC_SCALE,
        IS_NULLABLE
    FROM QSYS2.SYSCOLUMNS
    WHERE TABLE_SCHEMA = '{LIBRERIA}'
    AND TABLE_NAME = '{tabla}'
    ORDER BY ORDINAL_POSITION
    """

    return ejecutar_query(query)

# =====================================================
# PRIMARY KEYS
# =====================================================

@st.cache_data(ttl=3600)
def obtener_pk(tabla):

    query = f"""
    SELECT
        K.CONSTRAINT_NAME,
        K.COLUMN_NAME,
        K.ORDINAL_POSITION

    FROM QSYS2.SYSKEYCST K

    INNER JOIN QSYS2.SYSCST C

        ON K.CONSTRAINT_SCHEMA =
           C.CONSTRAINT_SCHEMA

       AND K.CONSTRAINT_NAME =
           C.CONSTRAINT_NAME

    WHERE C.TABLE_SCHEMA = '{LIBRERIA}'
      AND C.TABLE_NAME = '{tabla}'
      AND C.CONSTRAINT_TYPE = 'PRIMARY KEY'

    ORDER BY K.ORDINAL_POSITION
    """

    return ejecutar_query(query)

# =====================================================
# FOREIGN KEYS
# =====================================================

@st.cache_data(ttl=3600)
def obtener_fk(tabla):

    query = f"""
    SELECT
        K.CONSTRAINT_NAME,
        K.COLUMN_NAME,
        K.ORDINAL_POSITION

    FROM QSYS2.SYSKEYCST K

    INNER JOIN QSYS2.SYSCST C

        ON K.CONSTRAINT_SCHEMA =
           C.CONSTRAINT_SCHEMA

       AND K.CONSTRAINT_NAME =
           C.CONSTRAINT_NAME

    WHERE C.TABLE_SCHEMA = '{LIBRERIA}'
      AND C.TABLE_NAME = '{tabla}'
      AND C.CONSTRAINT_TYPE = 'FOREIGN KEY'

    ORDER BY K.ORDINAL_POSITION
    """

    return ejecutar_query(query)

# =====================================================
# RELACIONES
# =====================================================

@st.cache_data(ttl=3600)
def obtener_relaciones(tabla):

    query = f"""
    SELECT DISTINCT

        C.TABLE_NAME AS TABLA_HIJA,

        P.TABLE_NAME AS TABLA_PADRE,

        R.CONSTRAINT_NAME

    FROM QSYS2.SYSREFCST R

    INNER JOIN QSYS2.SYSCST C

        ON R.CONSTRAINT_SCHEMA =
        C.CONSTRAINT_SCHEMA

    AND R.CONSTRAINT_NAME =
        C.CONSTRAINT_NAME

    INNER JOIN QSYS2.SYSCST P

        ON R.UNIQUE_CONSTRAINT_SCHEMA =
        P.CONSTRAINT_SCHEMA

    AND R.UNIQUE_CONSTRAINT_NAME =
        P.CONSTRAINT_NAME

    WHERE C.TABLE_SCHEMA = '{LIBRERIA}'
    AND C.TABLE_NAME = '{tabla}'
    """

    return ejecutar_query(query)
# =====================================================
# BUSCAR TABLAS
# =====================================================

@st.cache_data(ttl=3600)
def buscar_tabla(texto):

    query = f"""
    SELECT
        TABLE_NAME
    FROM QSYS2.SYSTABLES
    WHERE TABLE_SCHEMA = '{LIBRERIA}'
    AND UPPER(TABLE_NAME)
    LIKE UPPER('%{texto}%')
    ORDER BY TABLE_NAME
    """

    return ejecutar_query(query)

# =====================================================
# BUSCAR COLUMNAS
# =====================================================

@st.cache_data(ttl=3600)
def buscar_columna(texto):

    query = f"""
    SELECT
        TABLE_NAME,
        COLUMN_NAME,
        DATA_TYPE,
        LENGTH
    FROM QSYS2.SYSCOLUMNS
    WHERE TABLE_SCHEMA = '{LIBRERIA}'
    AND UPPER(COLUMN_NAME)
    LIKE UPPER('%{texto}%')
    ORDER BY TABLE_NAME
    """

    return ejecutar_query(query)

# =====================================================
# TABLAS CON PK
# =====================================================

@st.cache_data(ttl=3600)
def obtener_tablas_con_pk():

    query = f"""
    SELECT DISTINCT
        TABLE_NAME
    FROM QSYS2.SYSCST
    WHERE TABLE_SCHEMA = '{LIBRERIA}'
      AND CONSTRAINT_TYPE = 'PRIMARY KEY'
    ORDER BY TABLE_NAME
    """

    return ejecutar_query(query)

# =====================================================
# EXCEL
# =====================================================

def generar_excel(df):

    output = BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            sheet_name="Datos",
            index=False
        )

    output.seek(0)

    return output

# =====================================================
# TITULO
# =====================================================

st.title(
    "📚 Catálogo AS400 - DPJDAT01"
)

st.caption(
    "Migración AS400 → Azure SQL"
)

# =====================================================
# CARGAR TABLAS
# =====================================================

with st.spinner(
    "Consultando catálogo AS400..."
):

    tablas = obtener_tablas()

# =====================================================
# SIDEBAR
# =====================================================

st.sidebar.success(
    f"📚 Librería: {LIBRERIA}"
)


st.sidebar.metric(
    "Total Tablas",
    len(tablas)
)


tabla = st.sidebar.selectbox(
    "📂 Seleccione Tabla",
    [""] + tablas["TABLE_NAME"].tolist()
)

if tabla == "":
    st.info(
        "Seleccione una tabla para visualizar su estructura."
    )

st.sidebar.markdown("---")

texto_tabla = st.sidebar.text_input(
    "🔍 Buscar Tabla"
)

texto_columna = st.sidebar.text_input(
    "🔎 Buscar Columna"
)



# =====================================================
# KPIS
# =====================================================

tablas_pk = obtener_tablas_con_pk()

tablas_sin_pk = len(tablas) - len(tablas_pk)

k1, k2, k3, k4 = st.columns(4)

k1.metric(
    "📚 Librería",
    LIBRERIA
)

k2.metric(
    "📋 Total Tablas",
    len(tablas)
)

k3.metric(
    "🔑 Con PK",
    len(tablas_pk)
)

k4.metric(
    "⚠️ Sin PK",
    tablas_sin_pk
)

# =====================================================
# DETALLE TABLA
# =====================================================
st.divider()
st.markdown(
"""
## 📂 Análisis de Tabla
Información detallada de la entidad seleccionada
"""
)
if tabla != "":

    with st.spinner(
        "Consultando estructura..."
    ):

        columnas = obtener_columnas(
            tabla
        )

        pk = obtener_pk(
            tabla
        )

        fk = obtener_fk(
            tabla
        )

        relaciones = obtener_relaciones(
            tabla
        )

    st.header(
        f"📂 {tabla}"
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "📋 Columnas",
        len(columnas)
    )

    c2.metric(
        "🔑 PK",
        len(pk)
    )

    c3.metric(
        "🔗 FK",
        len(fk)
    )

    c4.metric(
        "🌐 Relaciones",
        len(relaciones)
    )

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📋 Columnas",
            "🔑 PK",
            "🔗 FK",
            "🌐 Entidad Relación"
        ]
    )

    with tab1:

        st.dataframe(
            columnas,
            use_container_width=True,
            height=600
        )

    with tab2:

        if pk.empty:

            st.info(
                "La tabla no tiene Primary Key."
            )

        else:

            st.dataframe(
                pk,
                use_container_width=True
            )

    with tab3:

        if fk.empty:

            st.info(
                "La tabla no tiene Foreign Keys."
            )

        else:

            st.dataframe(
                fk,
                use_container_width=True
            )

    with tab4:

        if relaciones.empty:

            st.info(
                "No existen relaciones registradas."
            )

        else:

            st.dataframe(
                relaciones,
                use_container_width=True
            )

    archivo_excel = generar_excel(
        columnas
    )

    st.download_button(
        label="📥 Descargar Diccionario",
        data=archivo_excel,
        file_name=f"{tabla}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# =====================================================
# BUSQUEDA TABLAS
# =====================================================

if texto_tabla:

    st.subheader(
        f"🔍 Resultado Tabla: {texto_tabla}"
    )

    resultado = buscar_tabla(
        texto_tabla
    )

    st.dataframe(
        resultado,
        use_container_width=True
    )

# =====================================================
# BUSQUEDA COLUMNAS
# =====================================================

if texto_columna:

    st.subheader(
        f"🔎 Resultado Columna: {texto_columna}"
    )

    resultado = buscar_columna(
        texto_columna
    )

    st.dataframe(
        resultado,
        use_container_width=True
    )


