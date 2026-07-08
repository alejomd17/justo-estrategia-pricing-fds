"""Elasticidad y unidades/dia reales (ATHENEA), con fallback en cascada
cuando no hay dato real: SKU real -> promedio real de categoria -> supuesto
declarado como ultimo recurso."""

import pandas as pd

ELASTICIDAD_POR_TAG_FALLBACK = {"ALTAMENTE ELASTICO": -2.2, "ELASTICO": -1.5, "POCO ELASTICO": -0.8}
Q0_POR_ROTACION_FALLBACK = {
    "Alta rotacion": 20.0,
    "Rotacion normal": 6.0,
    "Baja rotacion": 1.5,
    "Sin rotacion": 0.3,
}


def get_athenea(cur) -> pd.DataFrame:
    """Elasticidad real por SKU+Tienda desde ATHENEA.

    AVG_UNITS_PER_DAY ya NO se trae de aqui para Q0_DIA - ver
    get_unidades_dia_fulfillment. ELASTICITY_BY_SKU se sigue usando de
    ATHENEA (no mostro el mismo problema de unidad)."""
    cur.execute("""
        SELECT
            PRODUCT_ID::VARCHAR  AS SKU,
            WAREHOUSE_ID         AS STORE_ID,
            ELASTICITY_BY_SKU
        FROM MX_JUSTO_PROD.DR_GENERAL.ATHENEA
        WHERE WAREHOUSE_ID IN (9, 14)
          AND STATUS_SAP = 'Prendido'
          AND ELASTICITY_BY_SKU IS NOT NULL
    """)
    columnas = [c[0] for c in cur.description]
    athenea = pd.DataFrame(cur.fetchall(), columns=columnas)
    athenea["SKU"] = pd.to_numeric(athenea["SKU"], errors="coerce")
    athenea = athenea.dropna(subset=["SKU"])
    athenea["SKU"] = athenea["SKU"].astype(int)
    athenea["STORE_ID"] = athenea["STORE_ID"].astype(int)
    athenea = athenea.drop_duplicates(subset=["SKU", "STORE_ID"], keep="first")
    return athenea


def get_unidades_dia_fulfillment(cur, ventana_inicio="2026-01-01", ventana_fin=None) -> pd.DataFrame:
    """Unidades/dia real por SKU+tienda desde FACT_FULFILLMENT_LINE
    (QUANTITY_PZ) - reemplaza a ATHENEA.AVG_UNITS_PER_DAY como fuente de
    Q0_DIA, por decision explicita pese al riesgo conocido:

    RIESGO ACEPTADO: QUANTITY_PZ cuenta PIEZAS. Para SKUs de peso variable
    (ej. fruver, precio de catalogo en $/kg) esto NO es la misma unidad que
    PRECIO JUSTO/COSTO (de oportunidad.xlsx, en $/kg para esos SKUs) -
    confirmado con el SKU 23827: ATHENEA reportaba 18.9-41.8 unidades/dia
    (probable kg) vs. 294-646 piezas/dia reales, un ratio ~15.5x CONSISTENTE
    entre las dos tiendas (no un dato corrupto, una unidad distinta). Usar
    piezas aqui infla GMV_BASE_DIA/GMV_PROY_DIA (= Q0_DIA x PRECIO JUSTO)
    ~15x para ese tipo de SKU. Se opto por usar FACT_FULFILLMENT_LINE de
    todas formas, decision explicita del usuario aceptando ese riesgo
    conocido para SKUs de peso variable. Ver memoria
    project_athenea_unidades_sospechosas.

    Usa DELIVERED_DATE IS NOT NULL como filtro de "efectivamente
    entregado", mismo criterio que postmortem.validar_redencion_real (no se
    confirmaron los valores validos de ORDER_STATUS)."""
    ventana_inicio = pd.Timestamp(ventana_inicio)
    ventana_fin = pd.Timestamp(ventana_fin) if ventana_fin is not None else pd.Timestamp.now().normalize()
    dias_periodo = (ventana_fin - ventana_inicio).days

    cur.execute(
        """
        SELECT
            PRODUCT_ID::VARCHAR AS SKU,
            WAREHOUSE_ID        AS STORE_ID,
            SUM(QUANTITY_PZ)    AS UNIDADES
        FROM MX_JUSTO_PROD.DM_CORE.FACT_FULFILLMENT_LINE
        WHERE WAREHOUSE_ID IN (9, 14)
          AND DELIVERED_DATE IS NOT NULL
          AND DELIVERED_DATE BETWEEN %s AND %s
          AND QUANTITY_PZ > 0
        GROUP BY 1, 2
        """,
        (ventana_inicio.date(), ventana_fin.date()),
    )
    columnas = [c[0] for c in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=columnas)
    df["SKU"] = pd.to_numeric(df["SKU"], errors="coerce")
    df = df.dropna(subset=["SKU"])
    df["SKU"] = df["SKU"].astype(int)
    df["STORE_ID"] = df["STORE_ID"].astype(int)
    df["AVG_UNITS_PER_DAY"] = df["UNIDADES"] / dias_periodo
    return df[["SKU", "STORE_ID", "AVG_UNITS_PER_DAY"]]


def _fuente_y_valor(row, col_real, prom_por_cat, fallback_dict, tag_col):
    if pd.notna(row[col_real]):
        return "SKU real", row[col_real]
    prom_cat = prom_por_cat.get(row["Categoria"], float("nan"))
    if pd.notna(prom_cat):
        return "Categoria real", prom_cat
    return "Supuesto declarado", fallback_dict.get(row[tag_col], float("nan"))


def aplicar_fallback_cascada(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega ELASTICIDAD_FINAL/FUENTE_ELASTICIDAD y Q0_DIA/FUENTE_Q0 a `df`,
    que ya debe traer ELASTICITY_BY_SKU (merge previo con get_athenea),
    AVG_UNITS_PER_DAY (merge previo con get_unidades_dia_fulfillment - real,
    de FACT_FULFILLMENT_LINE, ya NO de ATHENEA - ver el riesgo conocido de
    unidad para peso variable documentado ahi) y Categoria (merge previo
    con el catalogo)."""
    elasticidad_por_categoria = (
        df.dropna(subset=["ELASTICITY_BY_SKU"]).groupby("Categoria")["ELASTICITY_BY_SKU"].mean()
    )
    unidades_por_categoria = (
        df.dropna(subset=["AVG_UNITS_PER_DAY"]).groupby("Categoria")["AVG_UNITS_PER_DAY"].mean()
    )

    res_elas = df.apply(
        lambda r: _fuente_y_valor(
            r, "ELASTICITY_BY_SKU", elasticidad_por_categoria, ELASTICIDAD_POR_TAG_FALLBACK, "TAG ELAS"
        ),
        axis=1,
    )
    df["FUENTE_ELASTICIDAD"] = res_elas.str[0]
    df["ELASTICIDAD_FINAL"] = res_elas.str[1].astype(float)

    res_q0 = df.apply(
        lambda r: _fuente_y_valor(
            r, "AVG_UNITS_PER_DAY", unidades_por_categoria, Q0_POR_ROTACION_FALLBACK, "TAG_ROTACION"
        ),
        axis=1,
    )
    df["FUENTE_Q0"] = res_q0.str[0]
    df["Q0_DIA"] = res_q0.str[1].astype(float)
    return df
