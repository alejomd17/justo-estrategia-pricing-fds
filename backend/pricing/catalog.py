"""Catalogo real de Snowflake: FULL_MASTER_CATALOG y VW_PRICING_DASHBOARD."""

import time

import pandas as pd

# Cache en memoria para get_medida_variable: escanea TODO el historico de
# FACT_FULFILLMENT_LINE y su resultado es un atributo fijo del producto (un
# SKU de peso variable no deja de serlo entre dos clics de filtro del
# dashboard). Sin esto, performance_por_mecanica re-corria el escaneo
# completo en CADA request - la causa principal de la lentitud al filtrar.
_MEDIDA_VARIABLE_CACHE = {"ts": 0.0, "df": None}
_CACHE_TTL_SEGUNDOS = 900  # 15 min - suficiente para una sesion de exploracion


def get_full_master_catalog(cur) -> pd.DataFrame:
    """SKU, Departamento, Categoria real - reemplaza el cruce contra el
    Excel de estrategia anterior (que solo cubria 3.5% de los SKUs)."""
    cur.execute("""
        SELECT DISTINCT SKU, DEPARTMENT, CATEGORY
        FROM MX_JUSTO_PROD.SANDBOX.FULL_MASTER_CATALOG
    """)
    columnas = [c[0] for c in cur.description]
    catalogo = pd.DataFrame(cur.fetchall(), columns=columnas)
    catalogo = catalogo.rename(columns={"DEPARTMENT": "Departamento", "CATEGORY": "Categoria"})

    # SKU puede venir sucio; forzar a entero y descartar lo no numerico
    catalogo["SKU"] = pd.to_numeric(catalogo["SKU"], errors="coerce")
    catalogo = catalogo.dropna(subset=["SKU"])
    catalogo["SKU"] = catalogo["SKU"].astype(int)

    # Un SKU podria tener mas de una fila (data quality) - nos quedamos con la primera
    catalogo = catalogo.drop_duplicates(subset="SKU", keep="first")
    return catalogo


def get_departamentos_categorias(cur) -> pd.DataFrame:
    """Departamento/Categoria distintos, para poblar los filtros del
    dashboard (Fase 5)."""
    cur.execute("""
        SELECT DISTINCT DEPARTMENT, CATEGORY
        FROM MX_JUSTO_PROD.SANDBOX.FULL_MASTER_CATALOG
        WHERE DEPARTMENT IS NOT NULL AND CATEGORY IS NOT NULL
        ORDER BY 1, 2
    """)
    columnas = [c[0] for c in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=columnas)
    return df.rename(columns={"DEPARTMENT": "Departamento", "CATEGORY": "Categoria"})


def get_medida_variable(cur) -> pd.DataFrame:
    """SKU+tienda con ES_PESO_VARIABLE real desde FACT_FULFILLMENT_LINE
    (QUANTITY_KG) - tabla ya confirmada accesible (se usa tambien en
    postmortem.validar_redencion_real). PRICE_PRODUCT_FULFILLED_PER_ITEM
    (la fuente que sugeria el diccionario de metricas) esta bloqueada por
    permisos - se resolvio con esta tabla en su lugar, columnas reales
    confirmadas en vivo el 2026-07-09: MEASUREMENT_UNIT_ID,
    UNIT_AVERAGE_WEIGHT, QUANTITY, QUANTITY_PZ, QUANTITY_KG.

    Un SKU de peso variable (fruver, ej. Tomate Verde SKU 23827) tiene su
    precio de catalogo en $/kg, pero la mecanica de precios de strategy.py
    (BNSP "3 x $X", BNSDP "ahorra $X c/u") lo trata como precio por pieza -
    genero una oferta ~14x mas cara que el precio real que nadie uso (ver
    memoria project_athenea_unidades_sospechosas). Este flag es solo para
    marcar/revisar a mano (decision del usuario) - construir_estrategia NO
    cambia la mecanica sola.

    Si un SKU+tienda ALGUNA VEZ se vendio con QUANTITY_KG > 0, se vende por
    peso (para SKUs por pieza QUANTITY_KG viene en 0, confirmado en la fila
    de muestra revisada). No hace falta "la fila mas reciente" - es un
    atributo fijo del producto, no cambia por orden.

    Cacheado en memoria por _CACHE_TTL_SEGUNDOS (el resultado no depende de
    ningun filtro y la query escanea todo el historico de la tabla)."""
    ahora = time.monotonic()
    if (
        _MEDIDA_VARIABLE_CACHE["df"] is not None
        and ahora - _MEDIDA_VARIABLE_CACHE["ts"] < _CACHE_TTL_SEGUNDOS
    ):
        return _MEDIDA_VARIABLE_CACHE["df"].copy()

    cur.execute("""
        SELECT
            PRODUCT_ID::VARCHAR AS SKU,
            WAREHOUSE_ID        AS STORE_ID,
            MAX(QUANTITY_KG)    AS MAX_QUANTITY_KG
        FROM MX_JUSTO_PROD.DM_CORE.FACT_FULFILLMENT_LINE
        WHERE WAREHOUSE_ID IN (9, 14)
          AND DELIVERED_DATE IS NOT NULL
        GROUP BY 1, 2
    """)
    columnas = [c[0] for c in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=columnas)
    df["SKU"] = pd.to_numeric(df["SKU"], errors="coerce")
    df = df.dropna(subset=["SKU"])
    df["SKU"] = df["SKU"].astype(int)
    df["STORE_ID"] = df["STORE_ID"].astype(int)
    df["ES_PESO_VARIABLE"] = df["MAX_QUANTITY_KG"] > 0
    resultado = df[["SKU", "STORE_ID", "ES_PESO_VARIABLE"]]
    _MEDIDA_VARIABLE_CACHE.update(ts=ahora, df=resultado)
    # .copy() para que ningun caller mute el DataFrame cacheado
    return resultado.copy()


def get_pricing_dashboard(cur, skus=None) -> pd.DataFrame:
    """COST/MARGIN/FINAL_PRICE/IEPS/IVA reales por SKU+tienda, para el
    post-mortem (Fase 3 del plan). Se usa SOLO para margen/costo - se
    ignoran a proposito PROMO_ACTIVA y los campos de 30 dias de esta vista,
    porque estan calculados relativos a CURRENT_DATE y no reflejan el
    estado historico de una promo ya pasada.

    `skus`: lista opcional de SKUs (int) para acotar la query. Sin esto,
    trae todo el catalogo (puede ser lento).
    """
    query = """
        SELECT
            SKU,
            STORE_ID,
            COST,
            MARGIN,
            FINAL_PRICE,
            IEPS,
            IVA
        FROM MX_JUSTO_PROD.SANDBOX.VW_PRICING_DASHBOARD
    """
    params = None
    if skus:
        skus_param = tuple(int(s) for s in skus)
        placeholders = ",".join(["%s"] * len(skus_param))
        query += f" WHERE SKU IN ({placeholders})"
        params = skus_param

    cur.execute(query, params)
    columnas = [c[0] for c in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=columnas)
    df["SKU"] = pd.to_numeric(df["SKU"], errors="coerce")
    df = df.dropna(subset=["SKU"])
    df["SKU"] = df["SKU"].astype(int)
    df["STORE_ID"] = df["STORE_ID"].astype(int)
    return df
