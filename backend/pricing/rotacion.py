"""Baseline real de rotacion por categoria (MASTER_ORDERLINE x
FULL_MASTER_CATALOG), para medir traccion de forma justa entre categorias
con ritmos de compra muy distintos (ej. un cepillo de dientes vendiendo 1
unidad/dia no es "mala rotacion" si se compra cada 20-30 dias, mientras que
un platano - consumible diario - vendiendo 20 es apenas normal). Ver Fase 5
del plan en /home/alejomd17/.claude/plans/vamos-a-cambiar-de-glowing-plum.md.

A diferencia de `strategy.get_ventas_historicas` (que acota la query a los
SKUs elegibles del universo de oportunidad.xlsx), esta consulta trae el
catalogo completo - es justo lo opuesto a quedarse en ese universo limitado.
"""

import pandas as pd

from . import catalog

MIN_SKU_TIENDAS_POR_CATEGORIA = 5


def _baseline_y_fuente(row, baseline_tienda, conteo_tienda, baseline_cat):
    key_tienda = (row["Categoria"], row["STORE_ID"])
    n = conteo_tienda.get(key_tienda, 0)
    if key_tienda in baseline_tienda.index and n >= MIN_SKU_TIENDAS_POR_CATEGORIA:
        return baseline_tienda[key_tienda], "Categoria x tienda"
    val_cat = baseline_cat.get(row["Categoria"], float("nan"))
    if pd.notna(val_cat):
        return val_cat, "Categoria (ambas tiendas)"
    return float("nan"), "Sin baseline"


def _agregado_con_cascada(ventas, agg):
    """Cascada categoria x tienda -> categoria (ambas tiendas) -> NaN, para
    un agregado dado ('mean' o 'sum') sobre UNIDADES_DIA_SKU_TIENDA."""
    grp_tienda = ventas.groupby(["Categoria", "STORE_ID"])["UNIDADES_DIA_SKU_TIENDA"]
    valor_tienda = getattr(grp_tienda, agg)()
    conteo_tienda = grp_tienda.size()
    valor_cat = getattr(ventas.groupby("Categoria")["UNIDADES_DIA_SKU_TIENDA"], agg)()

    resultado = ventas.apply(
        lambda r: _baseline_y_fuente(r, valor_tienda, conteo_tienda, valor_cat), axis=1
    )
    return resultado.str[0].astype(float), resultado.str[1]


def get_baseline_categoria(cur, ventana_inicio="2026-01-01", ventana_fin=None) -> pd.DataFrame:
    """Unidades/dia real y su inverso (dias promedio entre venta) por
    SKU+tienda, mas DOS baselines de categoria distintos - no intercambiables:

    - `UNIDADES_DIA_CATEGORIA_BASELINE` (promedio): "unidades/dia de un SKU
      tipico de esta categoria" - para comparar UN SKU contra su categoria
      (asi lo usa strategy.py en ROTACION_REAL_RATIO).
    - `UNIDADES_DIA_CATEGORIA_TOTAL` (suma): "unidades/dia de TODA la
      categoria combinada" - para comparar un total agregado de VARIOS SKUs
      (asi lo usa postmortem.performance_por_mecanica, que suma unidades de
      todos los SKUs de una mecanica/origen/categoria). Usar el promedio ahi
      por error compara "1 SKU típico" contra "N SKUs sumados" y da
      tracciones absurdas (miles de x).

    Cascada de 3 niveles para cada uno si una categoria tiene pocos datos:
    1. Categoria x STORE_ID (si hay >= MIN_SKU_TIENDAS_POR_CATEGORIA SKU-tienda)
    2. Categoria agrupando ambas tiendas
    3. NaN (marcado en FUENTE_BASELINE_CATEGORIA como "Sin baseline")

    Devuelve un DataFrame a grano SKU+STORE_ID; para consumo a nivel
    Categoria (ej. en postmortem.py), dedup por (Categoria, STORE_ID) o por
    Categoria segun se necesite.
    """
    ventana_inicio = pd.Timestamp(ventana_inicio)
    ventana_fin = pd.Timestamp(ventana_fin) if ventana_fin is not None else pd.Timestamp.now().normalize()
    dias_periodo = (ventana_fin - ventana_inicio).days

    cur.execute(
        """
        SELECT
            PRODUCT_ID::VARCHAR        AS SKU,
            STORE_ID,
            SUM(QUANTITY_FULFILLED_PZ) AS UNIDADES
        FROM MX_JUSTO_PROD.DR_MASTER_TABLES.MASTER_ORDERLINE
        WHERE STATUS_ORDER          = 'delivered'
          AND STORE_ID              IN (9, 14)
          AND QUANTITY_FULFILLED_PZ > 0
          AND DATETIME_DELIVERY     BETWEEN %s AND %s
        GROUP BY 1, 2
        """,
        (ventana_inicio.date(), ventana_fin.date()),
    )
    columnas = [c[0] for c in cur.description]
    ventas = pd.DataFrame(cur.fetchall(), columns=columnas)
    ventas["SKU"] = pd.to_numeric(ventas["SKU"], errors="coerce")
    ventas = ventas.dropna(subset=["SKU"])
    ventas["SKU"] = ventas["SKU"].astype(int)
    ventas["STORE_ID"] = ventas["STORE_ID"].astype(int)

    catalogo = catalog.get_full_master_catalog(cur)
    ventas = ventas.merge(catalogo[["SKU", "Categoria"]], on="SKU", how="left")

    ventas["UNIDADES_DIA_SKU_TIENDA"] = ventas["UNIDADES"] / dias_periodo
    ventas["DIAS_ENTRE_VENTA_SKU_TIENDA"] = dias_periodo / ventas["UNIDADES"]

    ventas["UNIDADES_DIA_CATEGORIA_BASELINE"], ventas["FUENTE_BASELINE_CATEGORIA"] = _agregado_con_cascada(
        ventas, "mean"
    )
    ventas["UNIDADES_DIA_CATEGORIA_TOTAL"], _ = _agregado_con_cascada(ventas, "sum")
    ventas["DIAS_ENTRE_VENTA_CATEGORIA_BASELINE"] = 1 / ventas["UNIDADES_DIA_CATEGORIA_BASELINE"]

    return ventas[
        [
            "SKU",
            "STORE_ID",
            "Categoria",
            "UNIDADES_DIA_SKU_TIENDA",
            "DIAS_ENTRE_VENTA_SKU_TIENDA",
            "UNIDADES_DIA_CATEGORIA_BASELINE",
            "UNIDADES_DIA_CATEGORIA_TOTAL",
            "DIAS_ENTRE_VENTA_CATEGORIA_BASELINE",
            "FUENTE_BASELINE_CATEGORIA",
        ]
    ]
