"""Catalogo real de Snowflake: FULL_MASTER_CATALOG y VW_PRICING_DASHBOARD."""

import pandas as pd


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
