import streamlit as st
import pandas as pd
import pyodbc
from io import BytesIO
from st_aggrid import AgGrid
from st_aggrid import GridOptionsBuilder
from difflib import SequenceMatcher

# =====================================================
# CONFIGURACION
# =====================================================

SERVER = "vm-prb-dpj-eastus-001.database.windows.net"
USERNAME = "bquirozb"
PASSWORD = "Banco2026*+"

st.set_page_config(
    page_title="Catalogo Modelo DPJ",
    layout="wide"
)

# =====================================================
# CONEXION
# =====================================================

def conectar(database):

    return pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={SERVER};"
        f"DATABASE={database};"
        f"UID={USERNAME};"
        f"PWD={PASSWORD};"
    )

# =====================================================
# BASES
# =====================================================

@st.cache_data
def obtener_bases():

    conn = conectar("master")
    query = """
    SELECT name
    FROM sys.databases
    ORDER BY name
    """

    df = pd.read_sql(query, conn)

    conn.close()

    return df

# =====================================================
# TABLAS
# =====================================================

@st.cache_data
def obtener_tablas(base):

    conn = conectar(base)

    query = """
    SELECT
        TABLE_SCHEMA,
        TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_TYPE = 'BASE TABLE'
    ORDER BY TABLE_NAME
    """

    df = pd.read_sql(query, conn)

    conn.close()

    return df

# =====================================================
# BUSCAR TABLA GLOBAL
# =====================================================

@st.cache_data
def buscar_tabla_global(texto):

    bases = obtener_bases()

    resultado = []

    for db in bases["name"]:

        try:

            tablas_db = obtener_tablas(db)

            tablas_db["BASE_DATOS"] = db

            encontrados = tablas_db[
                tablas_db["TABLE_NAME"]
                .str.contains(
                    texto,
                    case=False,
                    na=False
                )
            ]

            resultado.append(encontrados)

        except:
            pass

    if len(resultado) > 0:

        return pd.concat(
            resultado,
            ignore_index=True
        )

    return pd.DataFrame()

# =====================================================
# COLUMNAS
# =====================================================

@st.cache_data
def obtener_columnas(base, tabla):

    conn = conectar(base)

    query = f"""
    SELECT
        ORDINAL_POSITION,
        COLUMN_NAME,
        DATA_TYPE,
        CHARACTER_MAXIMUM_LENGTH,
        NUMERIC_PRECISION,
        NUMERIC_SCALE,
        IS_NULLABLE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = '{tabla}'
    ORDER BY ORDINAL_POSITION
    """

    df = pd.read_sql(query, conn)

    conn.close()

    return df

# =====================================================
# PK / FK
# =====================================================

@st.cache_data
def obtener_llaves(base, tabla):

    conn = conectar(base)

    query = f"""
    SELECT
        tc.TABLE_NAME,
        tc.CONSTRAINT_NAME,
        tc.CONSTRAINT_TYPE,
        kcu.COLUMN_NAME
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
    LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
         ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
    WHERE tc.CONSTRAINT_TYPE IN
        ('PRIMARY KEY','FOREIGN KEY')
    AND tc.TABLE_NAME = '{tabla}'
    """

    df = pd.read_sql(query, conn)

    conn.close()

    return df

# =====================================================
# RELACIONES
# =====================================================

@st.cache_data
def obtener_relaciones(base, tabla):

    conn = conectar(base)

    query = f"""
    SELECT
        fk.name AS FK_NOMBRE,
        tp.name AS TABLA_HIJA,
        cp.name AS CAMPO_HIJA,
        tr.name AS TABLA_PADRE,
        cr.name AS CAMPO_PADRE
    FROM sys.foreign_keys fk
    INNER JOIN sys.foreign_key_columns fkc
       ON fk.object_id = fkc.constraint_object_id
    INNER JOIN sys.tables tp
       ON fkc.parent_object_id = tp.object_id
    INNER JOIN sys.columns cp
       ON fkc.parent_object_id = cp.object_id
      AND fkc.parent_column_id = cp.column_id
    INNER JOIN sys.tables tr
       ON fkc.referenced_object_id = tr.object_id
    INNER JOIN sys.columns cr
       ON fkc.referenced_object_id = cr.object_id
      AND fkc.referenced_column_id = cr.column_id
    WHERE tp.name = '{tabla}'
    """

    df = pd.read_sql(query, conn)

    conn.close()

    return df

# =====================================================
# BUSCAR COLUMNAS
# =====================================================

@st.cache_data
def buscar_columnas(base, texto):

    conn = conectar(base)

    query = f"""
    SELECT
        TABLE_NAME,
        COLUMN_NAME,
        DATA_TYPE,
        CHARACTER_MAXIMUM_LENGTH,
        NUMERIC_PRECISION,
        NUMERIC_SCALE,
        IS_NULLABLE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE COLUMN_NAME LIKE '%{texto}%'
    ORDER BY TABLE_NAME
    """

    df = pd.read_sql(query, conn)

    conn.close()

    return df

# =====================================================
# CONTEO REGISTROS
# =====================================================

@st.cache_data
def obtener_conteo(base, tabla):

    try:

        conn = conectar(base)

        query = f"""
        SELECT COUNT(*) TOTAL
        FROM [{tabla}]
        """

        total = pd.read_sql(query, conn)

        conn.close()

        return int(total.iloc[0]["TOTAL"])

    except:

        return 0

def validar_pk_reutilizada(
    muestra_origen,
    muestra_destino,
    pk_origen,
    pk_destino
):

    origen = set(
        muestra_origen[pk_origen]
        .astype(str)
    )

    destino = set(
        muestra_destino[pk_destino]
        .astype(str)
    )

    comunes = len(
        origen.intersection(destino)
    )

    if len(origen) == 0:
        return 0

    return round(
        (comunes / len(origen)) * 100,
        2
    )
# =====================================================
# MOTOR: OBTENER INFORMACION ESTRUCTURAL
# =====================================================

def obtener_perfil_estructural(base, tabla):
    
    columnas = obtener_columnas(base, tabla)
    llaves = obtener_llaves(base, tabla)
    
    pk = llaves[
        llaves["CONSTRAINT_TYPE"] == "PRIMARY KEY"]["COLUMN_NAME"].tolist()
    
    return{
        "base": base,
        "tabla": tabla,
        "pk": pk,
        "columnas": columnas.to_dict(orient="records")
    }

# =====================================================
# CALIDAD DE COLUMNA
# =====================================================

def calcular_calidad_columna(df, columna):

    try:
        total = len(df)

        if total == 0:
            return 0

        no_nulos = ( df[columna].notna().sum())

        return no_nulos / total

    except:
        return 0
    
def obtener_perfil_columna(df, columna):

    try:

        serie = df[columna].dropna()

        if len(serie) == 0:

            return {
                "nulos": 1,
                "unicos": 0,
                "longitud_promedio": 0
            }

        longitud_promedio = (
            serie.astype(str)
            .str.len()
            .mean()
        )

        return {

            "nulos":
                1 - (len(serie) / len(df)),

            "unicos":
                serie.nunique(),

            "longitud_promedio":
                round(longitud_promedio, 2)
        }

    except:

        return {
            "nulos": 1,
            "unicos": 0,
            "longitud_promedio": 0
        }
        
        
def clasificar_columna(df, columna):

    try:

        valores = (
            df[columna]
            .dropna()
            .astype(str)
            .head(100)
            .tolist()
        )

        if len(valores) == 0:
            return "VACIA"

        promedio = (
            sum(len(v) for v in valores)
            / len(valores)
        )

        # UUID

        if sum(
            "-" in v and len(v) >= 30
            for v in valores
        ) > len(valores) * 0.7:

            return "UUID"

        # FECHA

        if "date" in columna.lower():

            return "DATE"

        # BOOLEANO

        conjunto = set(valores)

        if conjunto.issubset(
            {"0", "1", "True", "False"}
        ):

            return "BOOLEAN"

        # CATALOGO

        if len(conjunto) <= 10:

            return "CATALOGO"

        # TEXTO CORTO

        if promedio <= 50:

            return "TEXT_SHORT"

        return "TEXT_LONG"

    except:

        return "UNKNOWN"
    
def score_estadistico(
    perfil_origen,
    perfil_destino
):

    score = 0

    diferencia_unicos = abs(
        perfil_origen["unicos"]
        -
        perfil_destino["unicos"]
    )

    if diferencia_unicos <= 2:

        score += 40

    elif diferencia_unicos <= 5:

        score += 20

    diferencia_longitud = abs(
        perfil_origen["longitud_promedio"]
        -
        perfil_destino["longitud_promedio"]
    )

    if diferencia_longitud <= 5:

        score += 30

    return score

def score_por_pk(
    origen,
    destino,
    pk_origen,
    pk_destino,
    col_origen,
    col_destino
):

    try:

        o = origen[
            [pk_origen, col_origen]
        ].copy()

        d = destino[
            [pk_destino, col_destino]
        ].copy()

        o.columns = ["PK", "VALOR_O"]
        d.columns = ["PK", "VALOR_D"]

        merge = o.merge(
            d,
            on="PK",
            how="inner"
        )

        if len(merge) == 0:
            return 0

        iguales = (
            merge["VALOR_O"]
            .astype(str)
            .str.strip()
            ==
            merge["VALOR_D"]
            .astype(str)
            .str.strip()
        ).sum()

        return round(
            (iguales / len(merge))
            * 100,
            2
        )

    except:

        return 0
    
def detectar_transformacion(
    origen,
    destino,
    col_origen,
    col_destino
):

    try:

        o = (
            origen[col_origen]
            .astype(str)
            .value_counts(normalize=True)
        )

        d = (
            destino[col_destino]
            .astype(str)
            .value_counts(normalize=True)
        )

        diferencia = abs(
            len(o)
            -
            len(d)
        )

        if diferencia <= 1:

            return True

        return False

    except:

        return False

def descubrir_equivalencias(
    perfil_origen,
    perfil_destino,
    muestra_origen,
    muestra_destino
):

    equivalencias = []
    destinos_usados = set()

    pk_origen = (
        perfil_origen["pk"][0]
        if len(perfil_origen["pk"]) == 1
        else None
    )

    pk_destino = (
        perfil_destino["pk"][0]
        if len(perfil_destino["pk"]) == 1
        else None
    )

    # ==========================================
    # MATCH EXACTO
    # ==========================================

    columnas_destino = {
        c["COLUMN_NAME"].lower(): c
        for c in perfil_destino["columnas"]
    }

    for col_origen in perfil_origen["columnas"]:

        nombre_origen = (
            col_origen["COLUMN_NAME"]
            .lower()
        )

        if nombre_origen in columnas_destino:

            equivalencias.append({
                "origen":
                    col_origen["COLUMN_NAME"],

                "destino":
                    columnas_destino[
                        nombre_origen
                    ]["COLUMN_NAME"],

                "score":
                    1000,

                "score_pk":
                    100,

                "tipo":
                    "EXACTA"
            })

            destinos_usados.add(
                nombre_origen
            )

    # ==========================================
    # MOTOR SEMANTICO
    # ==========================================

    for col_origen in perfil_origen["columnas"]:

        nombre_origen = (
            col_origen["COLUMN_NAME"]
        )

        if any(
            eq["origen"].lower()
            ==
            nombre_origen.lower()
            for eq in equivalencias
        ):
            continue

        mejor_score = 0
        mejor_destino = None
        mejor_tipo = None

        mejor_score_pk = 0
        mejor_score_nombre = 0

        perfil_est_origen = (
            obtener_perfil_columna(
                muestra_origen,
                nombre_origen
            )
        )

        categoria_origen = (
            clasificar_columna(
                muestra_origen,
                nombre_origen
            )
        )

        for col_destino in perfil_destino["columnas"]:

            nombre_destino = (
                col_destino["COLUMN_NAME"]
            )

            if (
                nombre_destino.lower()
                in destinos_usados
            ):
                continue

            perfil_est_destino = (
                obtener_perfil_columna(
                    muestra_destino,
                    nombre_destino
                )
            )

            categoria_destino = (
                clasificar_columna(
                    muestra_destino,
                    nombre_destino
                )
            )

            # ===================================
            # REGRA NUEVA
            # UNICIDAD COMPATIBLE
            # ===================================

            filas_origen = max(
                len(muestra_origen),
                1
            )

            filas_destino = max(
                len(muestra_destino),
                1
            )

            ratio_origen = (
                perfil_est_origen["unicos"]
                / filas_origen
            )

            ratio_destino = (
                perfil_est_destino["unicos"]
                / filas_destino
            )

            if (
                ratio_origen > 0.80
                and ratio_destino < 0.30
            ):
                continue

            if (
                ratio_destino > 0.80
                and ratio_origen < 0.30
            ):
                continue

            score = 0

            # ===================================
            # CATEGORIA
            # ===================================

            if (
                categoria_origen
                ==
                categoria_destino
            ):
                score += 100

            # ===================================
            # ESTADISTICO
            # ===================================

            score += score_estadistico(
                perfil_est_origen,
                perfil_est_destino
            )

            # ===================================
            # NOMBRE
            # ===================================

            similitud_nombre = (
                SequenceMatcher(
                    None,
                    nombre_origen.lower(),
                    nombre_destino.lower()
                ).ratio()
            )

            score_nombre = (
                similitud_nombre * 100
            )

            score += int(
                similitud_nombre * 30
            )

            # ===================================
            # DATA TYPE
            # ===================================

            if (
                col_origen["DATA_TYPE"]
                ==
                col_destino["DATA_TYPE"]
            ):
                score += 20

            # ===================================
            # PK MATCH
            # ===================================

            score_pk = 0

            if (
                pk_origen
                and
                pk_destino
            ):

                score_pk = score_por_pk(
                    muestra_origen,
                    muestra_destino,
                    pk_origen,
                    pk_destino,
                    nombre_origen,
                    nombre_destino
                )

                score += (
                    score_pk * 4
                )

            # ===================================
            # TRANSFORMACION
            # ===================================

            es_transformacion = (
                detectar_transformacion(
                    muestra_origen,
                    muestra_destino,
                    nombre_origen,
                    nombre_destino
                )
            )

            if es_transformacion:
                score += 50

            # ===================================
            # TIPO
            # ===================================

            tipo_equivalencia = (
                "COMPATIBLE"
            )

            if score_pk >= 90:

                tipo_equivalencia = (
                    "SEMANTICA"
                )

            elif es_transformacion:

                tipo_equivalencia = (
                    "TRANSFORMADA"
                )

            # ===================================
            # MEJOR
            # ===================================

            if score > mejor_score:

                mejor_score = score

                mejor_destino = (
                    nombre_destino
                )

                mejor_tipo = (
                    tipo_equivalencia
                )

                mejor_score_pk = (
                    score_pk
                )

                mejor_score_nombre = (
                    score_nombre
                )

        # =======================================
        # NUEVA REGLA
        # NO FORZAR MATCH
        # =======================================

        if not mejor_destino:
            continue

        # Sin evidencia real

        if (
            mejor_score_pk == 0
            and
            mejor_score_nombre < 80
        ):
            continue

        # Score muy bajo

        if mejor_score < 150:
            continue

        equivalencias.append({

            "origen":
                nombre_origen,

            "destino":
                mejor_destino,

            "score":
                round(
                    mejor_score,
                    2
                ),

            "score_pk":
                round(
                    mejor_score_pk,
                    2
                ),

            "tipo":
                mejor_tipo

        })

        destinos_usados.add(
            mejor_destino.lower()
        )

    cobertura = round(
        (
            len(equivalencias)
            /
            max(
                len(
                    perfil_origen[
                        "columnas"
                    ]
                ),
                1
            )
        ) * 100,
        2
    )

    return {

        "equivalencias":
            equivalencias,

        "cobertura":
            cobertura

    }
# =====================================================
# COMPARACION: CANTIDAD DE REGISTROS
# =====================================================
def comparar_conteos(origen_base, origen_tabla, destino_base, destino_tabla):
    conteo_origen = obtener_conteo(origen_base, origen_tabla)
    conteo_destino = obtener_conteo(destino_base,destino_tabla)
    
    return{
        "conteo_origen": conteo_origen,
        "conteo_destino": conteo_destino,
        "diferencia": conteo_origen - conteo_destino,
        "coincide": conteo_origen == conteo_destino
    }

# =====================================================
# COMPARACION: COMPARAR REGISTROS FALTANTES
# =====================================================
def comparar_faltantes(muestra_origen, muestra_destino, pk_origen, pk_destino):
    valores_origen = set(
        muestra_origen[pk_origen].dropna().astype(str)
    )
    valores_destino = set(muestra_destino[pk_destino].dropna().astype(str))
    faltantes = list(valores_origen - valores_destino)
    sobrantes = list(valores_destino - valores_origen)
    
    return{
        "faltantes": faltantes,
        "sobrantes": sobrantes,
        "total_faltantes": len(faltantes),
        "total_sobrantes": len(sobrantes)
    }
    
# =====================================================
# COMPARACION: COMPARAR VALORES
# =====================================================
def comparar_valores(muestra_origen, muestra_destino, equivalencias, pk_origen, pk_destino, SCORE_MINIMO=80):
    diferencias = []
    
    origen = muestra_origen.copy()
    destino = muestra_destino.copy()
    
    origen[pk_origen] = origen[pk_origen].astype(str)
    destino[pk_destino] = destino[pk_destino].astype(str)

    registros_comunes = set(origen[pk_origen]).intersection(set(destino[pk_destino]))
    
    for llave in registros_comunes:
        fila_origen = origen[origen[pk_origen] == llave].iloc[0]
        fila_destino = destino[destino[pk_destino] == llave].iloc[0]
        
        for eq in equivalencias:
            if eq["score"]<SCORE_MINIMO: continue
            
            campo_origen = eq["origen"]
            campo_destino = eq["destino"]
            
            try:
                valor_origen = str(fila_origen[campo_origen]).strip()
                valor_destino = str(fila_destino[campo_destino]).strip()
                
                if valor_origen != valor_destino:
                    diferencias.append({"pk": llave,"campo_origen": campo_origen, "valor_origen": valor_origen, "valor_destino": valor_destino})
            except: pass
            
    return diferencias
# =====================================================
# COMPARACION: OBTENER DATOS TABLA
# =====================================================
def obtener_datos_tabla(base, tabla):

    conn = conectar(base)

    metadata = obtener_columnas(
        base,
        tabla
    )

    columnas_select = []

    for _, row in metadata.iterrows():

        columna = row["COLUMN_NAME"]
        tipo = str(row["DATA_TYPE"]).lower()

        if tipo == "datetimeoffset":

            columnas_select.append(
                f"CAST([{columna}] AS datetime2) AS [{columna}]"
            )

        else:

            columnas_select.append(
                f"[{columna}]"
            )

    query = f"""
        SELECT
            {",".join(columnas_select)}
        FROM [{tabla}]
    """

    df = pd.read_sql(
        query,
        conn
    )

    conn.close()

    return df
# =====================================================
# COMPARACION: COMPARAR PROYECCION
# =====================================================

# =====================================================
# COMPARACION: COMPARAR PROYECCION
# =====================================================

def comparar_proyeccion(
    origen_base,
    origen_tabla,
    destino_base,
    destino_tabla
):

    # ======================================
    # PERFILES
    # ======================================

    perfil_origen = obtener_perfil_estructural(
        origen_base,
        origen_tabla
    )

    perfil_destino = obtener_perfil_estructural(
        destino_base,
        destino_tabla
    )

    # ======================================
    # DATOS
    # ======================================

    datos_origen = obtener_datos_tabla(
        origen_base,
        origen_tabla
    )

    datos_destino = obtener_datos_tabla(
        destino_base,
        destino_tabla
    )

    # ======================================
    # EQUIVALENCIAS
    # ======================================

    resultado_heuristico = descubrir_equivalencias(
        perfil_origen,
        perfil_destino,
        datos_origen,
        datos_destino
    )

    equivalencias = (
        resultado_heuristico["equivalencias"]
    )

    cobertura = (
        resultado_heuristico["cobertura"]
    )

    # ======================================
    # VALIDAR PK
    # ======================================

    if len(perfil_origen["pk"]) != 1:

        raise Exception(
            f"La tabla origen {origen_tabla} "
            f"tiene PK compuesta o no tiene PK"
        )

    if len(perfil_destino["pk"]) != 1:

        raise Exception(
            f"La tabla destino {destino_tabla} "
            f"tiene PK compuesta o no tiene PK"
        )

    pk_origen = perfil_origen["pk"][0]
    pk_destino = perfil_destino["pk"][0]

    # ======================================
    # CONTEOS
    # ======================================

    resultado_conteo = comparar_conteos(
        origen_base,
        origen_tabla,
        destino_base,
        destino_tabla
    )

    # ======================================
    # COINCIDENCIA PK
    # ======================================

    coincidencia_pk = validar_pk_reutilizada(
        datos_origen,
        datos_destino,
        pk_origen,
        pk_destino
    )

    origen_vacio = (
        len(datos_origen) == 0
    )

    destino_vacio = (
        len(datos_destino) == 0
    )

    conteo_origen = len(datos_origen)
    conteo_destino = len(datos_destino)

    # ======================================
    # DIFERENCIA DE CONTEO
    # ======================================

    if max(conteo_origen, conteo_destino) > 0:

        diferencia_conteo = (
            abs(
                conteo_origen
                -
                conteo_destino
            )
            /
            max(
                conteo_origen,
                conteo_destino
            )
        )

    else:

        diferencia_conteo = 1

    # ======================================
    # PK REGENERADA
    # SOLO SI LOS CONTEOS SON CASI IGUALES
    # ======================================

    pk_regenerada = (

        coincidencia_pk < 20

        and

        not origen_vacio

        and

        not destino_vacio

        and

        diferencia_conteo <= 0.05

    )

    observacion = ""

    # ======================================
    # CASO 1
    # DESTINO VACIO
    # ======================================

    if destino_vacio:

        resultado_faltantes = {

            "faltantes":
                datos_origen[
                    pk_origen
                ]
                .astype(str)
                .tolist(),

            "sobrantes": [],

            "total_faltantes":
                len(datos_origen),

            "total_sobrantes":
                0

        }

        diferencias = []

        observacion = (
            "PROYECCION VACIA"
        )

    # ======================================
    # CASO 2
    # ORIGEN VACIO
    # ======================================

    elif origen_vacio:

        resultado_faltantes = {

            "faltantes": [],

            "sobrantes":
                datos_destino[
                    pk_destino
                ]
                .astype(str)
                .tolist(),

            "total_faltantes":
                0,

            "total_sobrantes":
                len(datos_destino)

        }

        diferencias = []

        observacion = (
            "ORIGEN VACIO"
        )

    # ======================================
    # CASO 3
    # PK REGENERADA
    # ======================================

    elif pk_regenerada:

        resultado_faltantes = {

            "faltantes": [],

            "sobrantes": [],

            "total_faltantes": 0,

            "total_sobrantes": 0

        }

        diferencias = []

        observacion = (
            "PK TECNICA REGENERADA"
        )

    # ======================================
    # CASO 4
    # COMPARACION NORMAL
    # ======================================

    else:

        resultado_faltantes = comparar_faltantes(
            datos_origen,
            datos_destino,
            pk_origen,
            pk_destino
        )

        diferencias = comparar_valores(
            datos_origen,
            datos_destino,
            equivalencias,
            pk_origen,
            pk_destino
        )

    # ======================================
    # RETORNO
    # ======================================

    # ======================================
    # RETORNO
    # ======================================

    return {

        "base_destino":
            destino_base,

        "tabla_destino":
            destino_tabla,

        "cobertura":
            cobertura,

        "equivalencias":
            equivalencias,

        "conteos":
            resultado_conteo,

        "pk_origen":
            pk_origen,

        "pk_destino":
            pk_destino,

        "coincidencia_pk":
            coincidencia_pk,

        "pk_regenerada":
            pk_regenerada,

        "origen_vacio":
            origen_vacio,

        "destino_vacio":
            destino_vacio,

        "observacion":
            observacion,

        "conteo_origen":
            conteo_origen,

        "conteo_destino":
            conteo_destino,

        "faltantes":
            resultado_faltantes[
                "total_faltantes"
            ],

        "sobrantes":
            resultado_faltantes[
                "total_sobrantes"
            ],

        "detalle_faltantes":
            resultado_faltantes[
                "faltantes"
            ],

        "detalle_sobrantes":
            resultado_faltantes[
                "sobrantes"
            ],

        "diferencias":
            len(diferencias),

        "detalle_diferencias":
            diferencias

    }
# =====================================================
# ORQUESTADOR VALIDADOR DE PROYECCIONES
# =====================================================
def ejecutar_validacion_matriz(matriz_validacion):
    resultados = []
    origenes = [x for x in matriz_validacion if x["tipo"]== "ORIGEN"]
    
    if len(origenes) != 1:
        raise Exception("Debe existir un unico origen")
    
    origen = origenes[0]
    proyecciones = [x for x in matriz_validacion if x["tipo"]== "PROYECCION"]
    
    if len(proyecciones) == 0:
        raise Exception("No existe PROYECCIONES para validar")
    
    for proyeccion in proyecciones:
        try:
            resultado = comparar_proyeccion(origen["base"], origen["tabla"], proyeccion["base"], proyeccion["tabla"])
            resultados.append(resultado)
        except Exception as e: resultados.append({"base_destino":proyeccion["base"], "tabla_destino":proyeccion["tabla"], "error": str(e)})
    return resultados

# =====================================================
# GENERAR REPORTE VALIDACION DE PROYECCION
# =====================================================

# =====================================================
# INVENTARIO COMPLETO
# =====================================================

def generar_inventario_completo():

    output = BytesIO()

    bases = obtener_bases()

    tablas_total = []
    columnas_total = []
    llaves_total = []
    relaciones_total = []
    conteos_total = []

    for db in bases["name"]:

        try:

            conn = conectar(db)

            # ======================================
            # TABLAS
            # ======================================

            tablas = pd.read_sql("""
                SELECT
                    TABLE_SCHEMA,
                    TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE='BASE TABLE'
            """, conn)

            tablas["BASE_DATOS"] = db

            tablas_total.append(tablas)

            # ======================================
            # COLUMNAS
            # ======================================

            columnas = pd.read_sql("""
                SELECT
                    TABLE_SCHEMA,
                    TABLE_NAME,
                    COLUMN_NAME,
                    DATA_TYPE,
                    CHARACTER_MAXIMUM_LENGTH,
                    NUMERIC_PRECISION,
                    NUMERIC_SCALE,
                    IS_NULLABLE,
                    COLUMN_DEFAULT
                FROM INFORMATION_SCHEMA.COLUMNS
            """, conn)

            columnas["BASE_DATOS"] = db

            columnas_total.append(columnas)

            # ======================================
            # PK FK
            # ======================================

            llaves = pd.read_sql("""
                SELECT
                    tc.TABLE_NAME,
                    tc.CONSTRAINT_NAME,
                    tc.CONSTRAINT_TYPE,
                    kcu.COLUMN_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                    ON tc.CONSTRAINT_NAME =
                       kcu.CONSTRAINT_NAME
                WHERE tc.CONSTRAINT_TYPE IN
                    ('PRIMARY KEY','FOREIGN KEY')
            """, conn)

            llaves["BASE_DATOS"] = db

            llaves_total.append(llaves)

            # ======================================
            # CONTEOS
            # ======================================

            try:

                conteo = pd.read_sql("""
                    SELECT
                        t.name AS TABLA,
                        SUM(p.rows) AS REGISTROS
                    FROM sys.tables t
                    INNER JOIN sys.partitions p
                        ON t.object_id = p.object_id
                    WHERE p.index_id IN (0,1)
                    GROUP BY t.name
                """, conn)

                conteo["BASE_DATOS"] = db

                conteos_total.append(conteo)

            except:
                pass

            # ======================================
            # RELACIONES
            # ======================================

            try:

                relaciones = pd.read_sql("""
                    SELECT
                        fk.name AS FK_NOMBRE,
                        tp.name AS TABLA_HIJA,
                        cp.name AS CAMPO_HIJA,
                        tr.name AS TABLA_PADRE,
                        cr.name AS CAMPO_PADRE
                    FROM sys.foreign_keys fk

                    INNER JOIN sys.foreign_key_columns fkc
                        ON fk.object_id =
                           fkc.constraint_object_id

                    INNER JOIN sys.tables tp
                        ON fkc.parent_object_id =
                           tp.object_id

                    INNER JOIN sys.columns cp
                        ON fkc.parent_object_id =
                           cp.object_id
                       AND
                           fkc.parent_column_id =
                           cp.column_id

                    INNER JOIN sys.tables tr
                        ON fkc.referenced_object_id =
                           tr.object_id

                    INNER JOIN sys.columns cr
                        ON fkc.referenced_object_id =
                           cr.object_id
                       AND
                           fkc.referenced_column_id =
                           cr.column_id
                """, conn)

                relaciones["BASE_DATOS"] = db

                relaciones_total.append(relaciones)

            except:
                pass

            conn.close()

        except Exception as e:

            print(f"Error {db}: {e}")

    # ==========================================
    # CONSOLIDAR
    # ==========================================

    tablas_total = pd.concat(tablas_total)

    columnas_total = pd.concat(columnas_total)

    llaves_total = pd.concat(llaves_total)

    relaciones_total = pd.concat(relaciones_total)

    conteos_total = pd.concat(conteos_total)

    # ==========================================
    # PK
    # ==========================================

    pk = llaves_total[
        llaves_total["CONSTRAINT_TYPE"]
        == "PRIMARY KEY"
    ]

    # ==========================================
    # FK
    # ==========================================

    fk = llaves_total[
        llaves_total["CONSTRAINT_TYPE"]
        == "FOREIGN KEY"
    ]

    # ==========================================
    # AS400
    # ==========================================

    as400 = tablas_total[
        tablas_total["TABLE_NAME"]
        .str.contains(
            "AS400",
            case=False,
            na=False
        )
    ]

    # ==========================================
    # TABLAS SIN PK
    # ==========================================

    tablas_con_pk = set(
        pk["TABLE_NAME"]
    )

    todas_tablas = set(
        tablas_total["TABLE_NAME"]
    )

    tablas_sin_pk = pd.DataFrame(
        {
            "TABLE_NAME":
                list(
                    todas_tablas -
                    tablas_con_pk
                )
        }
    )

    # ==========================================
    # COLUMNAS POR TABLA
    # ==========================================

    columnas_por_tabla = (
        columnas_total
        .groupby(
            [
                "BASE_DATOS",
                "TABLE_NAME"
            ]
        )
        .size()
        .reset_index(
            name="TOTAL_COLUMNAS"
        )
        .sort_values(
            "TOTAL_COLUMNAS",
            ascending=False
        )
    )

    # ==========================================
    # TABLAS MAESTRAS
    # ==========================================

    tablas_maestras = (
        relaciones_total
        .groupby(
            "TABLA_PADRE"
        )
        .size()
        .reset_index(
            name="DEPENDENCIAS"
        )
        .sort_values(
            "DEPENDENCIAS",
            ascending=False
        )
    )

    # ==========================================
    # CAMPOS OBLIGATORIOS
    # ==========================================

    obligatorios = columnas_total[
        columnas_total["IS_NULLABLE"]
        == "NO"
    ]

    # ==========================================
    # CAMPOS DECIMALES
    # ==========================================

    decimales = columnas_total[
        columnas_total["DATA_TYPE"]
        .str.contains(
            "decimal|numeric",
            case=False,
            na=False
        )
    ]

    # ==========================================
    # RESUMEN
    # ==========================================

    resumen = pd.DataFrame({

        "Indicador": [

            "Bases",
            "Tablas",
            "Columnas",
            "PK",
            "FK",
            "Relaciones",
            "AS400",
            "Tablas sin PK"

        ],

        "Valor": [

            len(bases),
            len(tablas_total),
            len(columnas_total),
            len(pk),
            len(fk),
            len(relaciones_total),
            len(as400),
            len(tablas_sin_pk)

        ]
    })

    # ==========================================
    # EXCEL
    # ==========================================

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        resumen.to_excel(
            writer,
            sheet_name="Resumen",
            index=False
        )

        bases.to_excel(
            writer,
            sheet_name="Bases",
            index=False
        )

        tablas_total.to_excel(
            writer,
            sheet_name="Tablas",
            index=False
        )

        columnas_total.to_excel(
            writer,
            sheet_name="Columnas",
            index=False
        )
        pk.to_excel(
            writer,
            sheet_name="PrimaryKeys",
            index=False
        )

        fk.to_excel(
            writer,
            sheet_name="ForeignKeys",
            index=False
        )

        llaves_total.to_excel(
            writer,
            sheet_name="Llaves",
            index=False
        )

        relaciones_total.to_excel(
            writer,
            sheet_name="Entidad_Relacion",
            index=False
        )

        conteos_total.to_excel(
            writer,
            sheet_name="Conteos",
            index=False
        )

        as400.to_excel(
            writer,
            sheet_name="Tablas_AS400",
            index=False
        )

        tablas_sin_pk.to_excel(
            writer,
            sheet_name="Tablas_Sin_PK",
            index=False
        )

        columnas_por_tabla.to_excel(
            writer,
            sheet_name="Columnas_Por_Tabla",
            index=False
        )

        tablas_maestras.to_excel(
            writer,
            sheet_name="Tablas_Maestras",
            index=False
        )

        obligatorios.to_excel(
            writer,
            sheet_name="Campos_Obligatorios",
            index=False
        )

        decimales.to_excel(
            writer,
            sheet_name="Campos_Decimales",
            index=False
        )

    output.seek(0)

    return output

# =====================================================
# GENERAR EXCEL TABLA
# =====================================================

def generar_excel_tabla(
    columnas,
    pk,
    fk,
    relaciones
):

    output = BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        columnas.to_excel(
            writer,
            sheet_name="Columnas",
            index=False
        )

        pk.to_excel(
            writer,
            sheet_name="PrimaryKeys",
            index=False
        )

        fk.to_excel(
            writer,
            sheet_name="ForeignKeys",
            index=False
        )

        relaciones.to_excel(
            writer,
            sheet_name="Relaciones",
            index=False
        )

    output.seek(0)

    return output

# =====================================================
# INTERFAZ
# =====================================================

st.title("📚 Catalogo Arquitectura de Datos DPJ")
if "matriz_validacion" not in st.session_state:
    st.session_state["matriz_validacion"] = []

if "tabla_abierta" not in st.session_state:
    st.session_state["tabla_abierta"] = None

if "base_abierta" not in st.session_state:
    st.session_state["base_abierta"] = None

if "nombre_tabla_abierta" not in st.session_state:
    st.session_state["nombre_tabla_abierta"] = None
    
bases = obtener_bases()

lista_bases = [""] + bases["name"].tolist()

base = st.sidebar.selectbox(
    "Base de Datos",
    lista_bases
)

if base != "":

    tablas = obtener_tablas(base)

else:

    tablas = pd.DataFrame(
        columns=[
            "TABLE_SCHEMA",
            "TABLE_NAME"
        ]   
    )

# =====================================================
# TABLAS DE LA BASE SELECCIONADA
# =====================================================

if base != "":

    mostrar_tablas = st.sidebar.checkbox(
        "📋 Ver tablas de la base"
    )

    st.sidebar.metric(
        "Total tablas",
        len(tablas)
    )

else:

    mostrar_tablas = False

# Si se desmarca, limpiar selección
if not mostrar_tablas:

    st.session_state["tabla_activa"] = ""
    
if mostrar_tablas:

    st.subheader(
        f"Tablas de la base: {base}"
    )

    tablas_grid = tablas[
        [
            "TABLE_SCHEMA",
            "TABLE_NAME"
        ]
    ]

    gb = GridOptionsBuilder.from_dataframe(
        tablas_grid
    )

    gb.configure_selection(
        selection_mode="single",
        use_checkbox=True
    )

    gb.configure_default_column(
        sortable=True,
        filter=True,
        resizable=True
    )

    respuesta = AgGrid(
        tablas_grid,
        gridOptions=gb.build(),
        height=350,
        fit_columns_on_grid_load=True
    )

    try:

        seleccionados = respuesta.selected_rows

        # SIN SELECCION
        if (
            seleccionados is None
            or seleccionados.empty
        ):

            if (
                st.session_state.get(
                    "tabla_activa",
                    ""
                ) != ""
            ):

                st.session_state["tabla_activa"] = ""

                st.rerun()

        # CON SELECCION
        else:

            tabla_seleccionada = (
                seleccionados.iloc[0]["TABLE_NAME"]
            )

            if (
                tabla_seleccionada
                != st.session_state.get(
                    "tabla_activa",
                    ""
                )
            ):

                st.session_state["tabla_activa"] = (
                    tabla_seleccionada
                )

                st.rerun()

    except Exception as e:

        st.warning(
            f"Error leyendo selección: {e}"
        )

# =====================================================
# CAMBIO DE BASE
# =====================================================

if "base_activa" not in st.session_state:

    st.session_state["base_activa"] = base

if st.session_state["base_activa"] != base:

    st.session_state["base_activa"] = base

    # limpiar tabla al cambiar de base
    st.session_state["tabla_activa"] = ""

if "tabla_activa" not in st.session_state:

    st.session_state["tabla_activa"] = ""

#=====================================================
# TABLA ACTIVA
# =====================================================

tabla = st.session_state["tabla_activa"]

if base == "":

    st.info(
        "Seleccione una Base de Datos o utilice la búsqueda global de tablas."
    )


if (

    base != ""
    and mostrar_tablas
    and st.session_state.get(
        "tabla_activa",
        ""
    ) != ""

):

    # =====================================================
    # INDICADORES
    # =====================================================

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Bases",
        len(bases)
    )

    col2.metric(
        "Tablas",
        len(tablas)
    )

    col3.metric(
        "Registros",
        obtener_conteo(base, tabla)
    )

    # =====================================================
    # TABLA
    # =====================================================

    st.header(f"📂 {tabla}")

    if "AS400" in tabla.upper():

        st.error(
            "🏦 Tabla proveniente de AS400"
        )

    # =====================================================
    # COLUMNAS
    # =====================================================

    columnas = obtener_columnas(
        base,
        tabla
    )

    def tipo_completo(row):

        if pd.notnull(row["NUMERIC_PRECISION"]):

            return (
                f"{row['DATA_TYPE']}"
                f"({int(row['NUMERIC_PRECISION'])},"
                f"{int(row['NUMERIC_SCALE'])})"
            )

        if pd.notnull(
            row["CHARACTER_MAXIMUM_LENGTH"]
        ):

            return (
                f"{row['DATA_TYPE']}"
                f"({int(row['CHARACTER_MAXIMUM_LENGTH'])})"
            )

        return row["DATA_TYPE"]

    columnas["TIPO_COMPLETO"] = columnas.apply(
        tipo_completo,
        axis=1
    )

    st.markdown("##### 📋 Columnas")

    st.dataframe(
        columnas[
            [
                "ORDINAL_POSITION",
                "COLUMN_NAME",
                "TIPO_COMPLETO",
                "IS_NULLABLE"
            ]
        ],
        use_container_width=True
    )

    # =====================================================
    # PK
    # =====================================================

    llaves = obtener_llaves(
        base,
        tabla
    )

    pk = llaves[
        llaves["CONSTRAINT_TYPE"]
        == "PRIMARY KEY"
    ]

    st.markdown("##### 🔑 Primary Keys")

    st.dataframe(
        pk,
        use_container_width=True
    )

    # =====================================================
    # FK
    # =====================================================

    fk = llaves[
        llaves["CONSTRAINT_TYPE"]
        == "FOREIGN KEY"
    ]

    st.markdown("##### 🔗 Foreign Keys")

    st.dataframe(
        fk,
        use_container_width=True
    )

    # =====================================================
    # RELACIONES
    # =====================================================

    relaciones = obtener_relaciones(
        base,
        tabla
    )

    st.markdown("##### 🌐 Relaciones")

    st.dataframe(
        relaciones,
        use_container_width=True
    )

# =====================================================
# GENERAR REPORTE VALIDACION
# =====================================================

def generar_reporte_validacion(resultados):

    output = BytesIO()

    resumen = []
    equivalencias = []
    faltantes = []
    sobrantes = []
    diferencias = []
    errores = []

    for resultado in resultados:

        # -----------------------------
        # ERRORES
        # -----------------------------
        if "error" in resultado:

            errores.append({
                "BASE_DESTINO":
                    resultado["base_destino"],

                "TABLA_DESTINO":
                    resultado["tabla_destino"],

                "ERROR":
                    resultado["error"]
            })

            continue

        # -----------------------------
        # RESUMEN
        # -----------------------------
        resumen.append({

        "BASE_DESTINO":
            resultado["base_destino"],

        "TABLA_DESTINO":
            resultado["tabla_destino"],

        "COBERTURA":
            resultado["cobertura"],

        "REG_ORIGEN":
            resultado["conteos"]["conteo_origen"],

        "REG_DESTINO":
            resultado["conteos"]["conteo_destino"],

        "DIF_CONTEO":
            resultado["conteos"]["diferencia"],

        "PK_ORIGEN":
            resultado["pk_origen"],

        "PK_DESTINO":
            resultado["pk_destino"],

        "COINCIDENCIA_PK":
            resultado["coincidencia_pk"],

        "PK_REGENERADA":
            resultado["pk_regenerada"],

        "ORIGEN_VACIO":
            resultado["origen_vacio"],

        "DESTINO_VACIO":
            resultado["destino_vacio"],

        "CONTEO_ORIGEN":
            resultado["conteo_origen"],

        "CONTEO_DESTINO":
        resultado["conteo_destino"],

        "OBSERVACION":
            resultado["observacion"],

        "FALTANTES":
            resultado["faltantes"],

        "SOBRANTES":
            resultado["sobrantes"],

        "DIFERENCIAS":
            resultado["diferencias"]

    })


        # -----------------------------
        # EQUIVALENCIAS
        # -----------------------------
        for eq in resultado["equivalencias"]:

            equivalencias.append({

                "BASE_DESTINO":
                    resultado["base_destino"],

                "TABLA_DESTINO":
                    resultado["tabla_destino"],

                "CAMPO_ORIGEN":
                    eq["origen"],

                "CAMPO_DESTINO":
                    eq["destino"],

                "SCORE":
                    eq["score"]
            })

        # -----------------------------
        # FALTANTES
        # -----------------------------
        for pk in resultado["detalle_faltantes"]:

            faltantes.append({

                "BASE_DESTINO":
                    resultado["base_destino"],

                "TABLA_DESTINO":
                    resultado["tabla_destino"],

                "PK":
                    pk

            })

        # -----------------------------
        # SOBRANTES
        # -----------------------------
        for pk in resultado["detalle_sobrantes"]:

            sobrantes.append({

                "BASE_DESTINO":
                    resultado["base_destino"],

                "TABLA_DESTINO":
                    resultado["tabla_destino"],

                "PK":
                    pk

            })

        # -----------------------------
        # DIFERENCIAS
        # -----------------------------
        for diff in resultado[
            "detalle_diferencias"
        ]:

            diferencias.append({

                "BASE_DESTINO":
                    resultado["base_destino"],

                "TABLA_DESTINO":
                    resultado["tabla_destino"],

                "PK":
                    diff["pk"],

                "CAMPO_ORIGEN":
                    diff["campo_origen"],

                "VALOR_ORIGEN":
                    diff["valor_origen"],

                "VALOR_DESTINO":
                    diff["valor_destino"]

            })

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        pd.DataFrame(resumen).to_excel(
            writer,
            sheet_name="Resumen",
            index=False
        )

        pd.DataFrame(equivalencias).to_excel(
            writer,
            sheet_name="Equivalencias",
            index=False
        )

        pd.DataFrame(faltantes).to_excel(
            writer,
            sheet_name="Faltantes",
            index=False
        )

        pd.DataFrame(sobrantes).to_excel(
            writer,
            sheet_name="Sobrantes",
            index=False
        )

        pd.DataFrame(diferencias).to_excel(
            writer,
            sheet_name="Diferencias",
            index=False
        )

        pd.DataFrame(errores).to_excel(
            writer,
            sheet_name="Errores",
            index=False
        )

    output.seek(0)

    return output
# =====================================================
# BUSQUEDA TABLAS
# =====================================================

resultado_tabla = pd.DataFrame()
st.sidebar.markdown("---")


buscar_tabla = st.sidebar.text_input(
    "🔍 Buscar tabla"
)

if buscar_tabla:

    resultado_tabla = buscar_tabla_global(
        buscar_tabla
    )

    if not resultado_tabla.empty:

        st.subheader(
            f"Resultado búsqueda: {buscar_tabla}"
        )

        # -------------------------------------
        # VARIABLES DE SESION
        # -------------------------------------

        if "tabla_abierta" not in st.session_state:
            st.session_state["tabla_abierta"] = None

        if "base_abierta" not in st.session_state:
            st.session_state["base_abierta"] = None

        if "nombre_tabla_abierta" not in st.session_state:
            st.session_state["nombre_tabla_abierta"] = None
# -------------------------------------
# SESION VALIDACION
# -------------------------------------

        if "matriz_validacion" not in st.session_state:
         st.session_state["matriz_validacion"] = []
    else:
         st.warning(
         "No se encontraron tablas"
         )         

# -------------------------------------
# CABECERA
# -------------------------------------

cab1, cab2, cab3, cab4 = st.columns(
    [2, 5, 1, 2]
)

cab1.markdown("### 🛢️ Base")
cab2.markdown("### 🗄️ Tabla")
cab3.markdown("### 🎯 Acción")
cab4.markdown("### ✅ Validación")

st.divider()

# -------------------------------------
# RESULTADOS
# -------------------------------------

for i, fila in resultado_tabla.iterrows():

    col1, col2, col3, col4 = st.columns(
        [2, 5, 1, 2]
    )

    col1.markdown(
        f"🛢️ **{fila['BASE_DATOS']}**"
    )

    col2.markdown(
        f"🗄️ **{fila['TABLE_NAME']}**"
    )

    id_tabla = (
        f"{fila['BASE_DATOS']}|"
        f"{fila['TABLE_NAME']}"
    )

    if (
        st.session_state["tabla_abierta"]
        == id_tabla
    ):

        if col3.button(
            "❌",
            key=f"cerrar_{i}"
        ):
            st.session_state["tabla_abierta"] = None
            st.session_state["base_abierta"] = None
            st.session_state["nombre_tabla_abierta"] = None
            st.rerun()

        base_abierta = fila["BASE_DATOS"]

        tabla_abierta = fila["TABLE_NAME"]

        columnas_busqueda = obtener_columnas(
            base_abierta,
            tabla_abierta
        )

        llaves_busqueda = obtener_llaves(
            base_abierta,
            tabla_abierta
        )

        relaciones_busqueda = obtener_relaciones(
            base_abierta,
            tabla_abierta
        )

        st.markdown(
            f"#### 📂 {base_abierta}.{tabla_abierta}"
        )

        tab1, tab2, tab3, tab4 = st.tabs(
            [
                "📋 Columnas",
                "🔑 PK",
                "🔗 FK",
                "🌐 Relaciones"
            ]
        )

        with tab1:
            st.dataframe(
                columnas_busqueda,
                use_container_width=True
            )

        with tab2:
            st.dataframe(
                llaves_busqueda[
                    llaves_busqueda["CONSTRAINT_TYPE"]
                    == "PRIMARY KEY"
                ],
                use_container_width=True
            )

        with tab3:
            st.dataframe(
                llaves_busqueda[
                    llaves_busqueda["CONSTRAINT_TYPE"]
                    == "FOREIGN KEY"
                ],
                use_container_width=True
            )

        with tab4:
            st.dataframe(
                relaciones_busqueda,
                use_container_width=True
            )

    else:

        if col3.button(
            "📂",
            key=f"abrir_{i}"
        ):

            st.session_state["tabla_abierta"] = id_tabla
            st.session_state["base_abierta"] = fila["BASE_DATOS"]
            st.session_state["nombre_tabla_abierta"] = fila["TABLE_NAME"]

            st.rerun()

    # ----------------------
    # BOTON ORIGEN
    # ----------------------
    val1, val2 = col4.columns(2)
    if val1.button(
        "Origen",
        key=f"origen_{i}"
    ):

        nuevo_origen = {
            "tipo": "ORIGEN",
            "base": fila["BASE_DATOS"],
            "tabla": fila["TABLE_NAME"]
            }
        
        proyecciones = [
            registro
            for registro in st.session_state["matriz_validacion"]
            if registro["tipo"] != "ORIGEN"
        ]
        
        st.session_state["matriz_validacion"] = [
            nuevo_origen,
            *proyecciones
        ]
        
        st.rerun()
        
# ----------------------
# BOTON PROYECCION
# ----------------------

    if val2.button(
    "Proyección",
    key=f"proyeccion_{i}"
    ):

        existe = any(
        x["base"] == fila["BASE_DATOS"]
        and x["tabla"] == fila["TABLE_NAME"]
        for x in st.session_state["matriz_validacion"]
        )

        if not existe:

            st.session_state["matriz_validacion"].append({
            "tipo": "PROYECCION",
            "base": fila["BASE_DATOS"],
            "tabla": fila["TABLE_NAME"]
            })
st.divider()

st.subheader(
    "🎯 Configuración de Validación"
)

cab1, cab2, cab3, cab4 = st.columns(
    [2, 4, 5, 1]
)

cab1.markdown("**Tipo**")
cab2.markdown("**Base**")
cab3.markdown("**Tabla**")
cab4.markdown("**Acción**")

st.divider()

# FILAS

for idx, registro in enumerate(
    st.session_state["matriz_validacion"]
):

    col1, col2, col3, col4 = st.columns(
        [2, 4, 5, 1]
    )

    col1.write(registro["tipo"])
    col2.write(registro["base"])
    col3.write(registro["tabla"])
    
    if col4.button(
        "🗑️",
        key=f"eliminar_{idx}"
    ):

        st.session_state["matriz_validacion"].pop(
            idx
        )

        st.rerun()
if st.button("🚀 Ejecutar Validación"):

    with st.spinner(
        "🔍 Analizando proyecciones y generando reporte..."
    ):

        resultados = ejecutar_validacion_matriz(
            st.session_state["matriz_validacion"]
        )

        archivo_excel = generar_reporte_validacion(
            resultados
        )

        st.session_state[
            "resultado_validacion"
        ] = resultados

        st.session_state[
            "archivo_validacion"
        ] = archivo_excel

    st.success(
        "✅ Validación finalizada correctamente"
    )
if "resultado_validacion" in st.session_state:

    resumen = []

    for resultado in st.session_state[
        "resultado_validacion"
    ]:

        if "error" in resultado:

            resumen.append({
                "BASE":
                    resultado["base_destino"],

                "TABLA":
                    resultado["tabla_destino"],

                "ESTADO":
                    "ERROR",

                "DETALLE":
                    resultado["error"]
            })

        else:

            resumen.append({
                "BASE":
                    resultado["base_destino"],

                "TABLA":
                    resultado["tabla_destino"],

                "COBERTURA":
                    resultado["cobertura"],

                "FALTANTES":
                    resultado["faltantes"],

                "SOBRANTES":
                    resultado["sobrantes"],

                "DIFERENCIAS":
                    resultado["diferencias"]
            })

    st.dataframe(
        pd.DataFrame(resumen),
        use_container_width=True
    )
    
    st.markdown("---")
    st.subheader("🔎 Detalles de Validación")

    for resultado in st.session_state["resultado_validacion"]:

        if "error" in resultado:
            continue

        with st.expander(
            f"{resultado['base_destino']} - {resultado['tabla_destino']}"
        ):

            tab1, tab2, tab3 = st.tabs(
                [
                    "Faltantes",
                    "Sobrantes",
                    "Diferencias"
                ]
            )

            with tab1:

                st.metric(
                    "Total Faltantes",
                    resultado["faltantes"]
                )

                if len(resultado["detalle_faltantes"]) > 0:

                    st.dataframe(
                        pd.DataFrame({
                            "PK_FALTANTE":
                                resultado["detalle_faltantes"]
                        }),
                        use_container_width=True
                    )

                else:

                    st.success(
                        "No existen faltantes"
                    )

            with tab2:

                st.metric(
                    "Total Sobrantes",
                    resultado["sobrantes"]
                )

                if len(resultado["detalle_sobrantes"]) > 0:

                    st.dataframe(
                        pd.DataFrame({
                            "PK_SOBRANTE":
                                resultado["detalle_sobrantes"]
                        }),
                        use_container_width=True
                    )

                else:

                    st.success(
                        "No existen sobrantes"
                    )

            with tab3:

                st.metric(
                    "Total Diferencias",
                    resultado["diferencias"]
                )

                if len(resultado["detalle_diferencias"]) > 0:

                    st.dataframe(
                        pd.DataFrame(
                            resultado["detalle_diferencias"]
                        ),
                        use_container_width=True
                    )

                else:

                    st.success(
                        "No existen diferencias"
                    )
if "archivo_validacion" in st.session_state:

    st.download_button(
        label="📊 Descargar Reporte de Validación",
        data=st.session_state[
            "archivo_validacion"
        ],
        file_name="Reporte_Validacion_Proyecciones.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
# =====================================================
# BUSQUEDA COLUMNAS
# =====================================================

st.sidebar.markdown("---")

buscar_columna = st.sidebar.text_input(
    "🔎 Buscar columna"
)


# =====================================================
# RESULTADO BUSQUEDA COLUMNAS
# =====================================================

if buscar_columna:

    resultado_columnas = buscar_columnas(
        base,
        buscar_columna
    )

    st.subheader(
        f"Resultado de búsqueda: {buscar_columna}"
    )

    st.dataframe(
        resultado_columnas,
        use_container_width=True
    )

    # =====================================================
    # DESCARGAR EXCEL
    # =====================================================

    archivo_excel = generar_excel_tabla(
        columnas,
        pk,
        fk,
        relaciones
    )

    st.download_button(
        label="📄 Descargar Diccionario",
        data=archivo_excel,
        file_name=f"{tabla}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# =====================================================
# INFORMACION FINAL
# =====================================================

if base != "":

    st.sidebar.info(
        f"""
Base seleccionada:
{base}

Tabla seleccionada:
{tabla}
"""
    )

# =====================================================
# RESULTADO BUSQUEDA COLUMNAS
# =====================================================

if buscar_columna:

    if base == "":
        st.warning(
            "Seleccione una base de datos para buscar columnas."
        )

    else:

        resultado_columnas = buscar_columnas(
            base,
            buscar_columna
        )

        st.subheader(
            f"Resultado de búsqueda: {buscar_columna}"
        )

        st.dataframe(
            resultado_columnas,
            use_container_width=True
        )

        # ==========================================
        # DESCARGAR DICCIONARIO
        # ==========================================

        if (
            "columnas" in locals()
            and "pk" in locals()
            and "fk" in locals()
            and "relaciones" in locals()
        ):

            archivo_excel = generar_excel_tabla(
                columnas,
                pk,
                fk,
                relaciones
            )

            st.download_button(
                label="📄 Descargar Diccionario",
                data=archivo_excel,
                file_name=f"{tabla}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
# =====================================================
# DESCARGAR INVENTARIO COMPLETO
# =====================================================

st.sidebar.markdown("---")

if st.sidebar.button(
    "📄 Generar Inventario Completo"
):

    with st.spinner(
        "Generando inventario..."
    ):

        st.session_state.archivo_inventario = (
            generar_inventario_completo()
        )

if "archivo_inventario" in st.session_state:

    st.sidebar.download_button(
        label="⬇ Descargar Inventario_DPJ.xlsx",
        data=st.session_state.archivo_inventario,
        file_name="Inventario_DPJ.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

