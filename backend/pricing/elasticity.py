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
    """Elasticidad y unidades/dia promedio por SKU+Tienda desde ATHENEA."""
    cur.execute("""
        SELECT
            PRODUCT_ID::VARCHAR  AS SKU,
            WAREHOUSE_ID         AS STORE_ID,
            ELASTICITY_BY_SKU,
            AVG_UNITS_PER_DAY
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


def _fuente_y_valor(row, col_real, prom_por_cat, fallback_dict, tag_col):
    if pd.notna(row[col_real]):
        return "SKU real", row[col_real]
    prom_cat = prom_por_cat.get(row["Categoria"], float("nan"))
    if pd.notna(prom_cat):
        return "Categoria real", prom_cat
    return "Supuesto declarado", fallback_dict.get(row[tag_col], float("nan"))


def aplicar_fallback_cascada(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega ELASTICIDAD_FINAL/FUENTE_ELASTICIDAD y Q0_DIA/FUENTE_Q0 a `df`,
    que ya debe traer ELASTICITY_BY_SKU/AVG_UNITS_PER_DAY (merge previo con
    get_athenea) y Categoria (merge previo con el catalogo)."""
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
