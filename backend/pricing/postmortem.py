"""Post-mortem de promos FDS: crea/consulta los objetos en
MX_JUSTO_PROD.SANDBOX definidos en el plan (ver
/home/alejomd17/.claude/plans/vamos-a-cambiar-de-glowing-plum.md):

- WKND_PROMO_RESULTS_V (VIEW): promos activas (cualquiera) x ventas reales,
  grano SKU+tienda+dia. Sin fecha fija adentro - se filtra al consultarla.
- WKND_PROMO_PLAN (TABLE): lo que nosotros planeamos, subido desde
  estrategia_fds.xlsx.
- WKND_PLAN_VS_ACTUAL_V (VIEW): join de las dos anteriores + ORIGEN_CAMPANA.
- WKND_POSTMORTEM_PROMO_V (VIEW): insights agregados (performance por mecanica,
  top ganadores/perdedores, oportunidades de subir precio).

COST/MARGIN/FINAL_PRICE se traen de PRICE_JUSTO_MS_HISTORY (ver
crear_postmortem_promo_v) - no de VW_PRICING_DASHBOARD, que no daba
confianza en el costo.
"""

import html
import math
from pathlib import Path

import pandas as pd

from . import catalog, rotacion
from .strategy import REDENCION

SCHEMA = "MX_JUSTO_PROD.SANDBOX"


def _tier_redencion(bulk_rule_buy, bulk_rule_pay):
    """Mapea BULK_RULE_BUY/BULK_RULE_PAY de FACT_FULFILLMENT_LINE al mismo
    agrupamiento de tiers que usa strategy.REDENCION.

    BULK_RULE_BUY > BULK_RULE_PAY es un umbral real de cantidad (compra N,
    paga N-1 - familia BNGM en produccion), equivalente a nuestro
    2x1/3x2/4x3/5x4/6x5. Ahi si tiene sentido comparar contra el supuesto
    declarado en REDENCION.

    BULK_RULE_BUY == BULK_RULE_PAY (el caso mas comun en produccion para
    SPON/BNSP/BNSDP) significa que esa ejecucion NO tuvo umbral de cantidad:
    el descuento aplica desde la primera unidad, sin necesidad de juntar
    varias - aunque nuestro modelo asuma esas mecanicas con umbral de 2-3
    unidades. Ahi la redencion real es trivialmente ~100% (no hay nada que
    "no redimir"), no es comparable contra el supuesto - se marca aparte
    como 'sin_umbral'."""
    if bulk_rule_buy is None or bulk_rule_pay is None:
        return None
    if bulk_rule_buy == bulk_rule_pay:
        return "sin_umbral"
    if bulk_rule_pay in (3, 4, 5) and bulk_rule_buy == bulk_rule_pay + 1:
        return "multibuy_grande"  # 4x3 / 5x4 / 6x5
    if bulk_rule_pay == 2 and bulk_rule_buy == 3:
        return "pack_3"  # 3x2 / BNSP
    if bulk_rule_pay == 1 and bulk_rule_buy == 2:
        return "umbral_2"  # 2x1 / SPON / BNSDP de 2 unidades
    return None


def crear_fds_promo_results_v(cur) -> None:
    """Vista recurrente: no tiene fecha fija, cualquier consumidor filtra
    `WHERE FECHA BETWEEN ...` a la ventana que le interese. Clasifica
    BY_BULK_GET/BY_BULK_PAY/BY_BULK_STRATEGY_DISCOUNT_TYPE en la misma
    taxonomia de mecanica que usa strategy.py (2x1/3x2/4x3/5x4/6x5/SPON/BNSDP).
    Lo que no encaja en esa taxonomia NO se agrupa como "Otro" - se deja el
    valor real de BY_BULK_STRATEGY_DISCOUNT_TYPE tal cual, para poder ver
    que mecanica es de verdad en vez de un cajon generico.

    IMPORTANTE: un SKU+tienda+dia puede tener varias campanas de
    DISCOUNT_CAMPAIGN_EVENT traslapando esas fechas (confirmado: 44,148 filas
    cruzan la ventana del FDS 3-5 jul para tiendas 9/14 - la mayoria son
    campanas comerciales de largo aliento que solo pasan de paso por esas
    fechas). Sin dedup, el LEFT JOIN por rango de fechas multiplica la misma
    venta real una vez por cada campana que hace match (se detecto en vivo:
    SKU 18756 mostraba 2,898 unidades en el dashboard cuando la venta real
    era 8-9). El QUALIFY se queda con una sola campana por SKU+tienda+dia,
    prefiriendo una mecanica reconocida sobre 'Sin dato' y, entre esas, la de
    ventana mas angosta (mas especifica que una campana comercial generica).
    """
    cur.execute(f"""
        CREATE OR REPLACE VIEW {SCHEMA}.WKND_PROMO_RESULTS_V AS
        WITH CAMPANAS AS (
            SELECT
                REGEXP_REPLACE(PRODUCT_ID, '[^0-9]', '') AS SKU,
                WAREHOUSE_ID                              AS STORE_ID,
                START_DATE,
                END_DATE,
                BY_BULK_STRATEGY_DISCOUNT_TYPE             AS TIPO_DESCUENTO,
                BY_BULK_STRATEGY_VALUE                     AS VALOR_DESCUENTO,
                BY_BULK_GET,
                BY_BULK_PAY,
                CASE
                    WHEN BY_BULK_PAY = 1 AND BY_BULK_GET = 2 THEN '2x1'
                    WHEN BY_BULK_PAY = 2 AND BY_BULK_GET = 3 THEN '3x2'
                    WHEN BY_BULK_PAY = 3 AND BY_BULK_GET = 4 THEN '4x3'
                    WHEN BY_BULK_PAY = 4 AND BY_BULK_GET = 5 THEN '5x4'
                    WHEN BY_BULK_PAY = 5 AND BY_BULK_GET = 6 THEN '6x5'
                    WHEN BY_BULK_STRATEGY_DISCOUNT_TYPE = 'PERCENTAGE' THEN 'SPON'
                    WHEN BY_BULK_STRATEGY_DISCOUNT_TYPE = 'FIXED' THEN 'BNSDP'
                    ELSE COALESCE(BY_BULK_STRATEGY_DISCOUNT_TYPE, 'Sin dato')
                END AS MECANICA
            FROM MX_JUSTO_PROD.ODS_MS_PRICING_V.DISCOUNT_CAMPAIGN_EVENT
            -- Rango amplio (no todo el historico) para no escanear de mas;
            -- ajustar si se necesita ver campanas mas viejas.
            WHERE START_DATE >= '2025-01-01'
        ),
        VENTAS AS (
            SELECT
                PRODUCT_ID::VARCHAR                     AS SKU,
                STORE_ID,
                TO_DATE(DATETIME_DELIVERY)               AS FECHA,
                SUM(QUANTITY_FULFILLED_PZ)               AS UNIDADES,
                SUM(AMOUNT_GROSS_DELIVERED)               AS GMV
            FROM MX_JUSTO_PROD.DR_MASTER_TABLES.MASTER_ORDERLINE
            WHERE STATUS_ORDER          = 'delivered'
              AND STORE_ID              IN (9, 14)
              AND QUANTITY_FULFILLED_PZ > 0
              AND DATETIME_DELIVERY     >= '2025-01-01'
            GROUP BY 1, 2, 3
        )
        SELECT
            v.SKU,
            v.STORE_ID,
            v.FECHA,
            v.UNIDADES,
            v.GMV,
            c.START_DATE  AS CAMPANA_INICIO,
            c.END_DATE    AS CAMPANA_FIN,
            c.MECANICA,
            c.TIPO_DESCUENTO,
            c.VALOR_DESCUENTO,
            CASE WHEN c.SKU IS NOT NULL THEN TRUE ELSE FALSE END AS CON_PROMO
        FROM VENTAS v
        LEFT JOIN CAMPANAS c
            ON v.SKU = c.SKU
           AND v.STORE_ID = c.STORE_ID
           AND v.FECHA BETWEEN c.START_DATE AND c.END_DATE
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY v.SKU, v.STORE_ID, v.FECHA
            ORDER BY
                CASE WHEN c.MECANICA = 'Sin dato' THEN 1 ELSE 0 END,
                DATEDIFF(day, c.START_DATE, c.END_DATE) ASC,
                c.START_DATE DESC
        ) = 1
    """)


def crear_fds_promo_plan_tabla(cur) -> None:
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.WKND_PROMO_PLAN (
            CAMPAIGN_START DATE,
            CAMPAIGN_END DATE,
            STORE_ID NUMBER,
            SKU NUMBER,
            MECANICA_PLANEADA VARCHAR,
            PRECIO_OFERTA_PLANEADO FLOAT,
            MARGEN_PLANEADO_PCT FLOAT,
            GMV_PROYECTADO FLOAT,
            UTIL_PROYECTADA FLOAT,
            RUN_TIMESTAMP TIMESTAMP_NTZ
        )
    """)


def subir_plan(
    cur,
    estrategia_df: pd.DataFrame,
    campaign_start: pd.Timestamp,
    campaign_end: pd.Timestamp,
    run_timestamp: pd.Timestamp,
) -> int:
    """Sube el plan (hoja 'Estrategia FDS' de estrategia_fds.xlsx) a
    WKND_PROMO_PLAN. Borra primero cualquier fila previa de la misma ventana,
    para que volver a subir un plan corregido no duplique. Devuelve cuantas
    filas se insertaron.

    `estrategia_df` debe traer al menos: STORE_ID, SKU, ESTRATEGIA,
    PRECIO_OFERTA, MARGEN_OFERTA_%, GMV_PROY_DIA, UTIL_PROY_DIA.
    """
    cur.execute(
        f"DELETE FROM {SCHEMA}.WKND_PROMO_PLAN WHERE CAMPAIGN_START = %s AND CAMPAIGN_END = %s",
        (campaign_start.date(), campaign_end.date()),
    )

    # pd.Timestamp no lo entiende el conector en executemany (solo
    # datetime.datetime nativo) - convertir antes de bindear.
    run_timestamp_nativo = pd.Timestamp(run_timestamp).to_pydatetime()

    filas = [
        (
            campaign_start.date(),
            campaign_end.date(),
            int(r["STORE_ID"]),
            int(r["SKU"]),
            r["ESTRATEGIA"],
            float(r["PRECIO_OFERTA"]),
            float(r["MARGEN_OFERTA_%"]) if pd.notna(r.get("MARGEN_OFERTA_%")) else None,
            float(r["GMV_PROY_DIA"]) if pd.notna(r.get("GMV_PROY_DIA")) else None,
            float(r["UTIL_PROY_DIA"]) if pd.notna(r.get("UTIL_PROY_DIA")) else None,
            run_timestamp_nativo,
        )
        for _, r in estrategia_df.iterrows()
    ]
    if not filas:
        return 0

    cur.executemany(
        f"""
        INSERT INTO {SCHEMA}.WKND_PROMO_PLAN (
            CAMPAIGN_START, CAMPAIGN_END, STORE_ID, SKU, MECANICA_PLANEADA,
            PRECIO_OFERTA_PLANEADO, MARGEN_PLANEADO_PCT, GMV_PROYECTADO,
            UTIL_PROYECTADA, RUN_TIMESTAMP
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        filas,
    )
    return len(filas)


def crear_fds_plan_vs_actual_v(cur) -> None:
    """ORIGEN_CAMPANA: 'WKND' si el SKU+tienda+ventana esta en
    WKND_PROMO_PLAN; 'Otra fuente' si hay promo real pero
    no es la nuestra; 'Sin promo' si ninguna de las dos."""
    cur.execute(f"""
        CREATE OR REPLACE VIEW {SCHEMA}.WKND_PLAN_VS_ACTUAL_V AS
        SELECT
            COALESCE(p.SKU, r.SKU)             AS SKU,
            COALESCE(p.STORE_ID, r.STORE_ID)   AS STORE_ID,
            p.CAMPAIGN_START,
            p.CAMPAIGN_END,
            p.MECANICA_PLANEADA,
            p.PRECIO_OFERTA_PLANEADO,
            p.MARGEN_PLANEADO_PCT,
            p.GMV_PROYECTADO,
            p.UTIL_PROYECTADA,
            r.FECHA,
            r.UNIDADES,
            r.GMV,
            r.MECANICA        AS MECANICA_EJECUTADA,
            r.CON_PROMO,
            CASE
                WHEN p.SKU IS NOT NULL THEN 'WKND'
                WHEN r.CON_PROMO THEN 'Otra fuente'
                ELSE 'Sin promo'
            END AS ORIGEN_CAMPANA
        FROM {SCHEMA}.WKND_PROMO_PLAN p
        FULL OUTER JOIN {SCHEMA}.WKND_PROMO_RESULTS_V r
            ON p.SKU = r.SKU
           AND p.STORE_ID = r.STORE_ID
           AND r.FECHA BETWEEN p.CAMPAIGN_START AND p.CAMPAIGN_END
    """)


def crear_postmortem_promo_v(cur) -> None:
    """Insights agregados sobre WKND_PLAN_VS_ACTUAL_V (hereda ORIGEN_CAMPANA)
    + FULL_MASTER_CATALOG para Departamento/Categoria (Fase 5 - filtros del
    dashboard y traccion por categoria).

    COST/MARGIN/FINAL_PRICE: el diccionario oficial de Finanzas/Data
    (docs/diccionario_metricas_margen.csv) confirma que la fuente
    recomendada es MX_JUSTO_PROD.ODS_MS_PRICING.PRICE_PRODUCT_FULFILLED_PER_ITEM
    (COST_NOMINAL, con ajuste de gramos), pero esa migracion quedo
    BLOQUEADA el 2026-07-09: sin permiso SELECT sobre esa tabla ("SQL
    access control error"). Mientras se consigue el permiso, se sigue
    usando PRICE_JUSTO_MS_HISTORY (ver commit anterior / memoria
    reference_diccionario_metricas_margen) - no es la fuente ideal, pero es
    la que SI funciona hoy. El CTE `precio_costo_activo` trae el
    precio/costo vigente: solo catalogo activo+publicado (via
    CURRENT_PRODUCT_CATALOG_WITH_CATEGORY, tiendas AT=9/CO=14), deduplicado
    a la fila mas reciente por PRODUCT_ID+STORE_ID+BRAND+SEGMENT_ID+
    SUBCATEGORY_ID+CATEGORY_ID+DEPARTMENT_ID (ORDER BY LOADED_LAKED_DATE
    DESC, NEXT_CREATED_AT DESC), acotado a SEGMENT_ID='default' y
    BRAND='justo' (query provista por Data/Finance)."""
    cur.execute(f"""
        CREATE OR REPLACE VIEW {SCHEMA}.WKND_POSTMORTEM_PROMO_V AS
        WITH catalogo_activo AS (
            SELECT DISTINCT
                p.PRODUCT_ID,
                CASE
                    WHEN wh.value::STRING = 'AT' THEN 9
                    WHEN wh.value::STRING = 'CO' THEN 14
                END AS STORE_ID
            FROM MX_JUSTO_PROD.ODS_MS_PRODUCT_V.CURRENT_PRODUCT_CATALOG_WITH_CATEGORY p,
                 LATERAL FLATTEN(input => p.ACTIVE_WAREHOUSES) wh
            WHERE p.is_active = TRUE
              AND p.is_published = TRUE
              AND wh.value::STRING IN ('AT', 'CO')
        ),
        precio_costo_activo AS (
            SELECT
                h.PRODUCT_ID AS SKU,
                h.STORE_ID,
                h.COST,
                h.MARGIN,
                h.FINAL_PRICE,
                ROW_NUMBER() OVER (
                    PARTITION BY
                        h.PRODUCT_ID, h.STORE_ID, h.BRAND, h.SEGMENT_ID,
                        h.SUBCATEGORY_ID, h.CATEGORY_ID, h.DEPARTMENT_ID
                    ORDER BY h.LOADED_LAKED_DATE DESC, h.NEXT_CREATED_AT DESC
                ) AS rn
            FROM MX_JUSTO_PROD.DA_PRICING.PRICE_JUSTO_MS_HISTORY h
            INNER JOIN catalogo_activo ca
                ON h.PRODUCT_ID = ca.PRODUCT_ID
               AND h.STORE_ID = ca.STORE_ID
            WHERE h.STORE_ID IN (9, 14)
              AND h.SEGMENT_ID = 'default'
              AND h.BRAND = 'justo'
            QUALIFY rn = 1
        )
        SELECT
            pva.SKU,
            pva.STORE_ID,
            pva.CAMPAIGN_START,
            pva.CAMPAIGN_END,
            pva.FECHA,
            pva.MECANICA_PLANEADA,
            pva.MECANICA_EJECUTADA,
            pva.ORIGEN_CAMPANA,
            pva.UNIDADES,
            pva.GMV,
            pva.GMV_PROYECTADO,
            pva.UTIL_PROYECTADA,
            pva.CON_PROMO,
            vpd.MARGIN,
            vpd.COST,
            vpd.FINAL_PRICE,
            fmc.DEPARTMENT AS DEPARTAMENTO,
            fmc.CATEGORY   AS CATEGORIA
        FROM {SCHEMA}.WKND_PLAN_VS_ACTUAL_V pva
        LEFT JOIN precio_costo_activo vpd
            ON TRY_TO_NUMBER(pva.SKU::VARCHAR) = TRY_TO_NUMBER(vpd.SKU::VARCHAR)
           AND pva.STORE_ID = vpd.STORE_ID
        LEFT JOIN {SCHEMA}.FULL_MASTER_CATALOG fmc
            ON TRY_TO_NUMBER(pva.SKU::VARCHAR) = TRY_TO_NUMBER(fmc.SKU::VARCHAR)
    """)


def _filtros_departamento_categoria_tienda(departamento=None, categoria=None, store_id=None, origen=None, adopcion=None):
    """Cláusulas/params opcionales compartidas por performance_por_mecanica,
    resumen_adopcion y top_skus - mismo patrón de condición armada en Python
    que ya usa catalog.get_pricing_dashboard con su parametro `skus`.
    `origen` filtra por ORIGEN_CAMPANA ('WKND' / 'Otra fuente' / 'Sin promo').
    `adopcion` filtra por si hubo mecanica real cargada o no ('con_mecanica'
    / 'sin_mecanica') - responde 'lo propusimos en WKND pero, ¿lo
    adoptaron?'."""
    condiciones = []
    params = []
    if departamento:
        condiciones.append("DEPARTAMENTO = %s")
        params.append(departamento)
    if categoria:
        condiciones.append("CATEGORIA = %s")
        params.append(categoria)
    if store_id:
        condiciones.append("STORE_ID = %s")
        params.append(int(store_id))
    if origen:
        condiciones.append("ORIGEN_CAMPANA = %s")
        params.append(origen)
    if adopcion == "con_mecanica":
        condiciones.append("MECANICA_EJECUTADA IS NOT NULL")
    elif adopcion == "sin_mecanica":
        condiciones.append("MECANICA_EJECUTADA IS NULL")
    return condiciones, params


def performance_por_mecanica(
    cur,
    campaign_start: pd.Timestamp,
    campaign_end: pd.Timestamp,
    departamento=None,
    categoria=None,
    store_id=None,
    origen=None,
    adopcion=None,
) -> pd.DataFrame:
    """GMV/unidades/margen promedio por mecanica planeada vs. ejecutada,
    ORIGEN_CAMPANA, Departamento, Categoria y tienda, para la ventana dada -
    responde '¿gano SPON o 6x5?' y '¿se ejecuto lo que planeamos?' sin
    mezclar lo nuestro con promos de otros equipos. Los filtros opcionales
    acotan el WHERE; Departamento/Categoria/STORE_ID quedan en el
    SELECT/GROUP BY como dimensiones de desglose, no solo de filtro.

    Incluye DOS versiones de traccion (rotacion.py), no intercambiables -
    ambas se calculan aqui, pero el frontend (MechanicsTable) solo muestra
    TRACCION_SKUS; HISTORICO_UNIDADES_DIA_CATEGORIA/TRACCION_CATEGORIA
    quedan disponibles en la API para quien las necesite:
    - TRACCION_SKUS: UNIDADES_DIA (real, de esta fila) vs. el historico de
      SOLO los SKUs que participan en esta fila, sumado - "¿estos SKUs
      especificos vendieron mas de lo normal?". Evita el sesgo de comparar
      pocos SKUs promovidos contra una categoria de 100+ SKUs.
    - TRACCION_CATEGORIA: UNIDADES_DIA vs. el historico de TODA la
      categoria-tienda, sumado - "¿la categoria completa crecio?", aunque
      solo hayamos tocado una fraccion de sus SKUs.

    INGRESO_SUPUESTO_SIN_PROMO / GANANCIA_POR_ESTRATEGIA: la resta simulada
    para saber cuanto genero la estrategia en plata. Por SKU: precio
    promedio (FINAL_PRICE, ver crear_postmortem_promo_v - viene de
    PRICE_JUSTO_MS_HISTORY, catalogo activo/publicado, mas confiable que
    VW_PRICING_DASHBOARD o FACT_FULFILLMENT_LINE) x su ritmo historico de
    unidades/dia x los dias de la ventana = cuanto hubiera facturado ese SKU
    sin promo, a su ritmo normal. GANANCIA_POR_ESTRATEGIA = GMV_TOTAL real -
    ese supuesto. CAVEAT: es el precio VIGENTE mas reciente (la fila mas
    nueva de PRICE_JUSTO_MS_HISTORY), no necesariamente el precio regular
    exacto del 3-5 jul si hubo un cambio de precio despues - proxy
    razonable, pero no historico exacto.

    El filtro `adopcion` se aplica DESPUES de colapsar por SKU (ver
    `llave_sku` abajo), no en el WHERE de la query: MECANICA_EJECUTADA puede
    variar dia a dia para un mismo SKU (ej. el evento real de
    DISCOUNT_CAMPAIGN_EVENT se cargo un dia despues del inicio de la
    ventana), y GROUP BY MECANICA_EJECUTADA fragmenta ese SKU en varias
    filas SQL - una por dia/mecanica distinta. Filtrar por adopcion en el
    WHERE descartaba los dias sin mecanica pero dejaba los dias CON mecanica
    sueltos, mostrando solo una fraccion de las unidades reales del fin de
    semana de ese SKU (se detecto en vivo: SKU 23827 mostraba 258 unidades
    en el dashboard cuando el fin de semana completo sumaba 258+149+lo del
    domingo).

    ORIGEN_CAMPANA = 'Sin promo' se excluye SIEMPRE (no es un filtro
    opcional): esto es un post-mortem de CAMPAÑA, no un reporte de ventas
    general - una categoria sin ninguna oferta propuesta ni ejecutada no
    aporta nada a "¿como nos fue con la campaña?", y su GMV organico (a
    veces enorme, ej. Frutas y Verduras) solo satura la tabla y distorsiona
    cualquier lectura. Si se necesita ver el panorama sin promo, usar
    `resumen_adopcion`, que si lo incluye a proposito para el KPI de
    cobertura.

    Peso variable (catalog.get_medida_variable, ES_PESO_VARIABLE real por
    SKU+tienda): INGRESO_SUPUESTO_SIN_PROMO/GANANCIA_POR_ESTRATEGIA salen
    NULL si el grupo tiene algun SKU de peso variable - el mismo problema
    del SKU 23827 (precio en $/kg contra unidades reales en piezas) aparecia
    agregado a nivel de categoria completa (ej. Verduras mostraba una
    "perdida" de -$723k que en realidad era el mismatch de unidad, no un
    resultado real de negocio)."""
    condiciones, params_filtro = _filtros_departamento_categoria_tienda(
        departamento, categoria, store_id, origen, adopcion=None
    )
    condiciones.append("ORIGEN_CAMPANA != 'Sin promo'")
    where_clause = " AND ".join(["FECHA BETWEEN %s AND %s"] + condiciones)
    cur.execute(
        f"""
        SELECT
            SKU,
            STORE_ID,
            MECANICA_PLANEADA,
            MECANICA_EJECUTADA,
            ORIGEN_CAMPANA,
            DEPARTAMENTO,
            CATEGORIA,
            SUM(UNIDADES) AS UNIDADES_TOTALES,
            SUM(GMV) AS GMV_TOTAL,
            AVG(MARGIN) AS MARGEN_PROMEDIO,
            AVG(FINAL_PRICE) AS PRECIO_PROMEDIO
        FROM {SCHEMA}.WKND_POSTMORTEM_PROMO_V
        WHERE {where_clause}
        GROUP BY SKU, STORE_ID, MECANICA_PLANEADA, MECANICA_EJECUTADA, ORIGEN_CAMPANA, DEPARTAMENTO, CATEGORIA
        """,
        [campaign_start.date(), campaign_end.date()] + params_filtro,
    )
    columnas = [c[0] for c in cur.description]
    detalle = pd.DataFrame(cur.fetchall(), columns=columnas)
    if detalle.empty:
        return detalle

    detalle["SKU"] = pd.to_numeric(detalle["SKU"], errors="coerce")
    detalle = detalle.dropna(subset=["SKU"])
    detalle["SKU"] = detalle["SKU"].astype(int)
    detalle["STORE_ID"] = detalle["STORE_ID"].astype(int)
    # AVG(...) de Snowflake vuelve como decimal.Decimal, no float - sin este
    # cast, PRECIO_PROMEDIO * UNIDADES_DIA_SKU_TIENDA (float64) revienta con
    # TypeError (Decimal no opera con float directamente).
    detalle["PRECIO_PROMEDIO"] = detalle["PRECIO_PROMEDIO"].astype(float)
    detalle["MARGEN_PROMEDIO"] = detalle["MARGEN_PROMEDIO"].astype(float)

    # Colapsar a UNA fila por SKU+tienda: sumar unidades/GMV de TODOS sus
    # fragmentos (con y sin mecanica ejecutada) y quedarse con la mecanica
    # ejecutada dominante: prioriza CUALQUIER mecanica real sobre "sin
    # mecanica" (si un dia tuvo mecanica y otros no, mostrar la real, no la
    # que junto mas unidades a secas - si no, un SKU con 1 dia de mecanica y
    # 2 dias de venta organica normal mostraba "Sin mecanica" pese a pasar
    # el filtro de adopcion "con_mecanica", una contradiccion). Entre
    # mecanicas reales de distintos dias, se desempata por unidades.
    # TUVO_MECANICA marca si ALGUN dia tuvo mecanica real - eso es lo que
    # decide el filtro de adopcion, sin descartar unidades de los otros
    # dias de ese mismo SKU.
    llave_sku = ["SKU", "STORE_ID", "MECANICA_PLANEADA", "ORIGEN_CAMPANA", "DEPARTAMENTO", "CATEGORIA"]
    detalle["TUVO_MECANICA"] = detalle["MECANICA_EJECUTADA"].notna()
    dominante = (
        detalle.sort_values(["TUVO_MECANICA", "UNIDADES_TOTALES"], ascending=[False, False])
        .drop_duplicates(subset=llave_sku, keep="first")[llave_sku + ["MECANICA_EJECUTADA"]]
    )
    detalle_sku = (
        detalle.groupby(llave_sku, dropna=False)
        .agg(
            UNIDADES_TOTALES=("UNIDADES_TOTALES", "sum"),
            GMV_TOTAL=("GMV_TOTAL", "sum"),
            MARGEN_PROMEDIO=("MARGEN_PROMEDIO", "mean"),
            PRECIO_PROMEDIO=("PRECIO_PROMEDIO", "mean"),
            TUVO_MECANICA=("TUVO_MECANICA", "any"),
        )
        .reset_index()
        .merge(dominante, on=llave_sku, how="left")
    )

    if adopcion == "con_mecanica":
        detalle_sku = detalle_sku[detalle_sku["TUVO_MECANICA"]]
    elif adopcion == "sin_mecanica":
        detalle_sku = detalle_sku[~detalle_sku["TUVO_MECANICA"]]
    if detalle_sku.empty:
        return detalle_sku

    baseline = rotacion.get_baseline_categoria(cur)
    baseline_sku = baseline[["SKU", "STORE_ID", "UNIDADES_DIA_SKU_TIENDA"]]
    detalle_sku = detalle_sku.merge(baseline_sku, on=["SKU", "STORE_ID"], how="left")

    # ES_PESO_VARIABLE real por SKU+tienda (FACT_FULFILLMENT_LINE.QUANTITY_KG
    # via catalog.get_medida_variable) - mismo dato que usa la salvaguarda de
    # la estrategia (strategy.agregar_medida_variable), no una lista de
    # categorias armada a mano.
    medida = catalog.get_medida_variable(cur)
    detalle_sku = detalle_sku.merge(medida, on=["SKU", "STORE_ID"], how="left")
    detalle_sku["ES_PESO_VARIABLE"] = detalle_sku["ES_PESO_VARIABLE"].fillna(False)

    dias_ventana = (campaign_end - campaign_start).days + 1
    detalle_sku["INGRESO_SUPUESTO_SIN_PROMO"] = (
        detalle_sku["PRECIO_PROMEDIO"] * detalle_sku["UNIDADES_DIA_SKU_TIENDA"] * dias_ventana
    )

    grupo = ["MECANICA_PLANEADA", "MECANICA_EJECUTADA", "ORIGEN_CAMPANA", "DEPARTAMENTO", "CATEGORIA", "STORE_ID"]
    df = (
        detalle_sku.groupby(grupo, dropna=False)
        .agg(
            SKUS=("SKU", "nunique"),
            UNIDADES_TOTALES=("UNIDADES_TOTALES", "sum"),
            GMV_TOTAL=("GMV_TOTAL", "sum"),
            MARGEN_PROMEDIO=("MARGEN_PROMEDIO", "mean"),
            HISTORICO_UNIDADES_DIA_SKUS=("UNIDADES_DIA_SKU_TIENDA", "sum"),
            INGRESO_SUPUESTO_SIN_PROMO=("INGRESO_SUPUESTO_SIN_PROMO", "sum"),
            ES_PESO_VARIABLE=("ES_PESO_VARIABLE", "any"),
        )
        .reset_index()
    )

    baseline_cat = baseline.drop_duplicates(subset=["Categoria", "STORE_ID"])[
        ["Categoria", "STORE_ID", "UNIDADES_DIA_CATEGORIA_TOTAL"]
    ].rename(columns={"Categoria": "CATEGORIA", "UNIDADES_DIA_CATEGORIA_TOTAL": "HISTORICO_UNIDADES_DIA_CATEGORIA"})
    df = df.merge(baseline_cat, on=["CATEGORIA", "STORE_ID"], how="left")

    df["UNIDADES_DIA"] = df["UNIDADES_TOTALES"] / dias_ventana
    df["TRACCION_SKUS"] = df["UNIDADES_DIA"] / df["HISTORICO_UNIDADES_DIA_SKUS"]
    df["TRACCION_CATEGORIA"] = df["UNIDADES_DIA"] / df["HISTORICO_UNIDADES_DIA_CATEGORIA"]
    df["GANANCIA_POR_ESTRATEGIA"] = df["GMV_TOTAL"] - df["INGRESO_SUPUESTO_SIN_PROMO"]

    # PRECIO_PROMEDIO viene en $/kg para SKUs de peso variable, pero
    # UNIDADES_DIA_SKU_TIENDA esta en piezas - la resta sale sin sentido (ver
    # docstring, caso SKU 23827). Si ALGUN SKU del grupo es de peso
    # variable, se anula el grupo completo - mejor NULL que un numero
    # parcial o equivocado.
    df.loc[df["ES_PESO_VARIABLE"], ["INGRESO_SUPUESTO_SIN_PROMO", "GANANCIA_POR_ESTRATEGIA"]] = None

    return df.sort_values("GMV_TOTAL", ascending=False)


def listar_campanas(cur) -> pd.DataFrame:
    """Ventanas de campana distintas ya subidas a WKND_PROMO_PLAN, para
    poblar el selector del dashboard."""
    cur.execute(f"""
        SELECT DISTINCT CAMPAIGN_START, CAMPAIGN_END
        FROM {SCHEMA}.WKND_PROMO_PLAN
        ORDER BY CAMPAIGN_START DESC
    """)
    columnas = [c[0] for c in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=columnas)


def resumen_adopcion(
    cur,
    campaign_start: pd.Timestamp,
    campaign_end: pd.Timestamp,
    departamento=None,
    categoria=None,
    store_id=None,
) -> pd.DataFrame:
    """SKU-tienda distintos por ORIGEN_CAMPANA en la ventana, y de esos
    cuantos tuvieron venta con promo real (CON_PROMO). Consulta
    WKND_POSTMORTEM_PROMO_V (no WKND_PLAN_VS_ACTUAL_V directo) porque ahi ya
    estan DEPARTAMENTO/CATEGORIA para poder filtrar. Filtra por FECHA, NO
    por CAMPAIGN_START/CAMPAIGN_END: esas dos columnas vienen solo del lado
    de WKND_PROMO_PLAN, y son NULL para las filas que en el FULL OUTER JOIN
    original solo existen del lado de WKND_PROMO_RESULTS_V (es decir, 'Otra
    fuente' y 'Sin promo') - filtrar por esas columnas dejaria esos dos
    buckets siempre vacios."""
    condiciones, params_filtro = _filtros_departamento_categoria_tienda(departamento, categoria, store_id)
    where_clause = " AND ".join(["FECHA BETWEEN %s AND %s"] + condiciones)
    cur.execute(
        f"""
        SELECT
            ORIGEN_CAMPANA,
            COUNT(DISTINCT SKU || '-' || STORE_ID) AS SKU_TIENDAS,
            COUNT(DISTINCT CASE WHEN CON_PROMO THEN SKU || '-' || STORE_ID END) AS SKU_TIENDAS_CON_PROMO_REAL
        FROM {SCHEMA}.WKND_POSTMORTEM_PROMO_V
        WHERE {where_clause}
        GROUP BY ORIGEN_CAMPANA
        ORDER BY SKU_TIENDAS DESC
        """,
        [campaign_start.date(), campaign_end.date()] + params_filtro,
    )
    columnas = [c[0] for c in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=columnas)


def top_skus(
    cur,
    campaign_start: pd.Timestamp,
    campaign_end: pd.Timestamp,
    n: int = 20,
    departamento=None,
    categoria=None,
    store_id=None,
    origen=None,
    adopcion=None,
) -> pd.DataFrame:
    """Ranking de SKUs mas vendidos (unidades) en la ventana, con
    Departamento/Categoria/tienda/mecanica/origen y filtros opcionales sobre
    esas mismas dimensiones. No hay nombre de producto disponible en los
    objetos de Snowflake usados aqui (FULL_MASTER_CATALOG solo trae
    SKU/DEPARTMENT/CATEGORY) - el ranking muestra el codigo de SKU crudo.

    Igual que performance_por_mecanica: MECANICA_EJECUTADA puede variar dia
    a dia para un mismo SKU, asi que se colapsa a UNA fila por SKU+tienda
    ANTES de rankear/filtrar por adopcion - de lo contrario el ORDER BY +
    LIMIT de SQL rankeaba fragmentos sueltos (una fraccion de las unidades
    reales de cada SKU), no el total del fin de semana.

    ORIGEN_CAMPANA = 'Sin promo' se excluye SIEMPRE, igual que en
    performance_por_mecanica - este ranking es de SKUs de campaña, no un
    top general de ventas (un SKU sin ninguna oferta propuesta ni ejecutada
    no aporta al post-mortem)."""
    condiciones, params_filtro = _filtros_departamento_categoria_tienda(
        departamento, categoria, store_id, origen, adopcion=None
    )
    condiciones.append("ORIGEN_CAMPANA != 'Sin promo'")
    where_clause = " AND ".join(["FECHA BETWEEN %s AND %s"] + condiciones)
    cur.execute(
        f"""
        SELECT
            SKU,
            STORE_ID,
            DEPARTAMENTO,
            CATEGORIA,
            MECANICA_EJECUTADA,
            ORIGEN_CAMPANA,
            SUM(UNIDADES) AS UNIDADES_TOTALES,
            SUM(GMV) AS GMV_TOTAL
        FROM {SCHEMA}.WKND_POSTMORTEM_PROMO_V
        WHERE {where_clause}
        GROUP BY SKU, STORE_ID, DEPARTAMENTO, CATEGORIA, MECANICA_EJECUTADA, ORIGEN_CAMPANA
        """,
        [campaign_start.date(), campaign_end.date()] + params_filtro,
    )
    columnas = [c[0] for c in cur.description]
    detalle = pd.DataFrame(cur.fetchall(), columns=columnas)
    if detalle.empty:
        return detalle

    llave_sku = ["SKU", "STORE_ID", "DEPARTAMENTO", "CATEGORIA", "ORIGEN_CAMPANA"]
    detalle["TUVO_MECANICA"] = detalle["MECANICA_EJECUTADA"].notna()
    # Prioriza cualquier mecanica real sobre "sin mecanica" - ver la nota en
    # performance_por_mecanica.
    dominante = (
        detalle.sort_values(["TUVO_MECANICA", "UNIDADES_TOTALES"], ascending=[False, False])
        .drop_duplicates(subset=llave_sku, keep="first")[llave_sku + ["MECANICA_EJECUTADA"]]
    )
    df = (
        detalle.groupby(llave_sku, dropna=False)
        .agg(
            UNIDADES_TOTALES=("UNIDADES_TOTALES", "sum"),
            GMV_TOTAL=("GMV_TOTAL", "sum"),
            TUVO_MECANICA=("TUVO_MECANICA", "any"),
        )
        .reset_index()
        .merge(dominante, on=llave_sku, how="left")
    )

    if adopcion == "con_mecanica":
        df = df[df["TUVO_MECANICA"]]
    elif adopcion == "sin_mecanica":
        df = df[~df["TUVO_MECANICA"]]

    return df.sort_values("UNIDADES_TOTALES", ascending=False).head(n).drop(columns="TUVO_MECANICA")


def contar_plan(cur, campaign_start: pd.Timestamp, campaign_end: pd.Timestamp) -> int:
    """Total de filas planeadas (SKU x tienda) para la ventana, leido
    directo de WKND_PROMO_PLAN. Denominador confiable para el % de adopcion
    - a diferencia del bucket 'WKND' de resumen_adopcion (que depende de que
    haya habido AL MENOS una venta en la ventana), esto cuenta el plan
    completo, incluidos los SKUs planeados que terminaron sin ninguna
    venta."""
    cur.execute(
        f"SELECT COUNT(*) FROM {SCHEMA}.WKND_PROMO_PLAN WHERE CAMPAIGN_START = %s AND CAMPAIGN_END = %s",
        (campaign_start.date(), campaign_end.date()),
    )
    return cur.fetchone()[0]


def plan_aun_no_ejecutado(weekend_fin: pd.Timestamp) -> bool:
    """True si el fin de semana del plan todavia no paso. En ese caso es
    seguro subir/sobreescribir el plan automaticamente al construirlo (cada
    corrida reemplaza a la anterior) porque no hay un registro historico
    real que se pueda pisar por error - eso solo puede pasar despues de que
    el fin de semana ya se ejecuto."""
    return pd.Timestamp.now().normalize() <= pd.Timestamp(weekend_fin).normalize()


def subir_plan_y_crear_vistas(
    cur,
    estrategia_df: pd.DataFrame,
    weekend_inicio: pd.Timestamp,
    weekend_fin: pd.Timestamp,
) -> int:
    """Sube `estrategia_df` a WKND_PROMO_PLAN y crea/reemplaza las 3 vistas
    de post-mortem. Comun a los dos flujos de subida: automatico al construir
    un plan para un finde que todavia no pasa, y manual (leyendo el Excel
    real desde disco) para un finde ya ejecutado. `estrategia_df` debe traer
    las columnas que pide `subir_plan` (ver su docstring)."""
    crear_fds_promo_results_v(cur)
    crear_fds_promo_plan_tabla(cur)
    n = subir_plan(cur, estrategia_df, weekend_inicio, weekend_fin, pd.Timestamp.now())
    crear_fds_plan_vs_actual_v(cur)
    crear_postmortem_promo_v(cur)
    return n


def crear_objetos_postmortem(cur) -> None:
    """Crea/reemplaza los 3 objetos que no dependen del plan subido
    (WKND_PROMO_RESULTS_V) y la tabla del plan. WKND_PLAN_VS_ACTUAL_V y
    WKND_POSTMORTEM_PROMO_V se crean por separado, despues de subir el plan con
    `subir_plan`, para que el primer CREATE no falle por WKND_PROMO_PLAN
    vacia (aunque CREATE TABLE IF NOT EXISTS ya la deja vacia y valida)."""
    crear_fds_promo_results_v(cur)
    crear_fds_promo_plan_tabla(cur)
    crear_fds_plan_vs_actual_v(cur)
    crear_postmortem_promo_v(cur)


def validar_redencion_real(cur, campaign_start: pd.Timestamp, campaign_end: pd.Timestamp) -> pd.DataFrame:
    """Compara la tasa de redencion REAL (IS_DISCOUNT/IS_BULK_APPLIED a nivel
    de linea de pedido en FACT_FULFILLMENT_LINE) contra los supuestos
    declarados en `strategy.REDENCION` (35%/40%/55%), para la ventana dada.

    Requiere acceso a MX_JUSTO_PROD.DM_CORE.FACT_FULFILLMENT_LINE - se
    confirmo en vivo que es accesible con el rol DATA_BI (ver Fase 0 del
    plan). Usa DELIVERED_DATE IS NOT NULL como filtro de "efectivamente
    entregado" en vez de adivinar los valores validos de ORDER_STATUS.
    """
    cur.execute(
        """
        SELECT
            BULK_STRATEGY,
            BULK_RULE_BUY,
            BULK_RULE_PAY,
            SUM(QUANTITY) AS UNIDADES_TOTALES,
            SUM(CASE WHEN IS_DISCOUNT OR IS_BULK_APPLIED THEN QUANTITY ELSE 0 END) AS UNIDADES_CON_DESCUENTO
        FROM MX_JUSTO_PROD.DM_CORE.FACT_FULFILLMENT_LINE
        WHERE WAREHOUSE_ID IN (9, 14)
          AND DELIVERED_DATE IS NOT NULL
          AND DELIVERED_DATE BETWEEN %s AND %s
        GROUP BY BULK_STRATEGY, BULK_RULE_BUY, BULK_RULE_PAY
        """,
        (campaign_start.date(), campaign_end.date()),
    )
    columnas = [c[0] for c in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=columnas)
    if df.empty:
        return df

    df["TIER"] = df.apply(lambda r: _tier_redencion(r["BULK_RULE_BUY"], r["BULK_RULE_PAY"]), axis=1)
    df["REDENCION_REAL"] = (df["UNIDADES_CON_DESCUENTO"] / df["UNIDADES_TOTALES"]).round(4)
    # 'sin_umbral' no esta en strategy.REDENCION (no es una mecanica nuestra,
    # es la ausencia de umbral en la ejecucion real) - se compara contra 1.0
    # porque sin umbral el descuento aplica siempre, trivialmente.
    tier_a_supuesta = {**REDENCION, "sin_umbral": 1.0}
    df["REDENCION_SUPUESTA"] = df["TIER"].map(tier_a_supuesta)
    df["DIFERENCIA"] = (df["REDENCION_REAL"] - df["REDENCION_SUPUESTA"]).round(4)
    return df.sort_values("UNIDADES_TOTALES", ascending=False)


def _fmt_moneda(v) -> str:
    return "N/D" if pd.isna(v) else f"${v:,.0f}"


def _fmt_num(v) -> str:
    return "N/D" if pd.isna(v) else f"{v:,.0f}"


def _fmt_pct(v) -> str:
    return "N/D" if pd.isna(v) else f"{v:.1f}%"


def _fmt_ratio(v) -> str:
    return "N/D" if pd.isna(v) else f"{v:.2f}x"


def _fmt_num_ceil(v) -> str:
    return "N/D" if pd.isna(v) else f"{math.ceil(v):,d}"


_STORE_NAMES_REPORTE = {9: "Atizapan", 14: "Coyoacan"}


def _fmt_bodega(v) -> str:
    return "N/D" if pd.isna(v) else _STORE_NAMES_REPORTE.get(int(v), str(v))

_GOOD_REPORTE = "#158158"
_WARN_REPORTE = "#ed561b"


def _etiqueta_barra(row) -> str:
    """Categoria + mecanica propuesta - una categoria sola se repite (misma
    categoria, distinta mecanica), igual que en TopChartsSection.tsx del
    dashboard."""
    cat = row.get("CATEGORIA") or "N/D"
    mecanica = row.get("MECANICA_PLANEADA") or "N/A"
    return f"{cat} · {mecanica}"


def _barras_html(items: list[tuple[str, float]], color: str, fmt) -> str:
    """Barras horizontales HTML - mismo mark spec que HorizontalBarChart.tsx
    del dashboard (barra con extremos redondeados, gap entre filas, valor
    directo al final, etiqueta truncada a la izquierda)."""
    if not items:
        return "<p class='nota'>Sin datos.</p>"
    maximo = max(abs(v) for _, v in items) or 1
    filas = []
    for label, valor in items:
        pct = abs(valor) / maximo * 100
        filas.append(
            f'<div class="bar-row">'
            f'<div class="bar-label" title="{html.escape(label)}">{html.escape(label)}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%;background:{color};"></div></div>'
            f'<div class="bar-value">{fmt(valor)}</div>'
            f"</div>"
        )
    return f'<div class="bar-chart">{"".join(filas)}</div>'


def _top_por(df: pd.DataFrame, campo: str, n: int = 10, asc: bool = False) -> list[tuple[str, float]]:
    sub = df.dropna(subset=[campo])
    sub = sub.sort_values(campo, ascending=asc).head(n)
    return [(_etiqueta_barra(r), r[campo]) for _, r in sub.iterrows()]


def _tops_campana_html(performance_df: pd.DataFrame) -> str:
    """Reproduce TopChartsSection.tsx del dashboard: 4 metricas x 2 tiendas
    (Atizapan/Coyoacan), cada una con sus top/peores 10."""
    metricas = [
        ("Top 10 por GMV", "GMV_TOTAL", False, _GOOD_REPORTE, _fmt_moneda),
        ("Top 10 por unidades vendidas", "UNIDADES_TOTALES", False, _GOOD_REPORTE, _fmt_num),
        ("Top 10 por traccion (mejor desempeno)", "TRACCION_SKUS", False, _GOOD_REPORTE, _fmt_ratio),
        ("Peores 10 por traccion (no funcionaron)", "TRACCION_SKUS", True, _WARN_REPORTE, _fmt_ratio),
    ]
    bloques = []
    for titulo, campo, asc, color, fmt in metricas:
        columnas_tienda = []
        for store_id, nombre in _STORE_NAMES_REPORTE.items():
            items = _top_por(performance_df[performance_df["STORE_ID"] == store_id], campo, 10, asc)
            columnas_tienda.append(
                f'<div><p class="chart-subtitle">{html.escape(nombre)}</p>{_barras_html(items, color, fmt)}</div>'
            )
        bloques.append(
            f'<div class="chart-block"><h3>{html.escape(titulo)}</h3>'
            f'<div class="chart-grid">{"".join(columnas_tienda)}</div></div>'
        )
    return "".join(bloques)


def _tabla_html(df: pd.DataFrame, columnas: list[tuple[str, str, callable]]) -> str:
    """Arma un <table> HTML a partir de `df` y una lista de
    (columna, encabezado, formateador). `html.escape` en celdas de texto -
    Departamento/Categoria/mecanica son texto libre, no confiar en que
    nunca traigan '<'/'&'."""
    encabezados = "".join(f"<th>{html.escape(h)}</th>" for _, h, _ in columnas)
    filas = []
    for _, row in df.iterrows():
        celdas = []
        for col, _, fmt in columnas:
            valor = row.get(col)
            texto = fmt(valor) if fmt else html.escape(str(valor)) if pd.notna(valor) else "N/D"
            celdas.append(f"<td>{texto}</td>")
        filas.append(f"<tr>{''.join(celdas)}</tr>")
    return f"<table><thead><tr>{encabezados}</tr></thead><tbody>{''.join(filas)}</tbody></table>"


def generar_reporte_html(
    performance_df: pd.DataFrame,
    top_skus_df: pd.DataFrame,
    campaign_start: pd.Timestamp,
    campaign_end: pd.Timestamp,
    resumen_df: pd.DataFrame = None,
    total_planeado: int = None,
    ruta_salida: str = None,
    top_n: int = 20,
) -> str:
    """Reporte HTML autonomo (mismo sistema de tokens/paleta que las fichas
    tecnicas hechas a mano durante el proyecto) a partir de los resultados
    del post-mortem (`performance_por_mecanica`, `top_skus`). Pensado para
    correr SIEMPRE despues de medir una campana en el notebook, no como un
    entregable manual aparte.

    `resumen_df` (salida de `resumen_adopcion`) y `total_planeado` (salida de
    `contar_plan`) son opcionales - si no se pasan, el KPI de Planeado/
    Adopcion/tarjetas por origen se omite (solo se muestran los KPIs
    calculables directo de `performance_df`). Se piden por separado, no
    recalculados aqui adentro, porque `resumen_adopcion` necesita ver TODOS
    los origenes (incluye 'Sin promo') para el denominador, mientras que
    `performance_df` ya viene filtrado.

    Nota: `performance_df`/`top_skus_df` ya excluyen 'Sin promo' (ver
    performance_por_mecanica) y ya traen INGRESO_SUPUESTO_SIN_PROMO/
    GANANCIA_POR_ESTRATEGIA en NULL para SKUs de peso variable - el reporte
    no necesita re-aplicar ninguno de esos dos filtros, solo mostrarlos.

    No incluye validacion de redencion (validar_redencion_real) a proposito
    - se saco del reporte y del dashboard por decision del usuario."""
    if ruta_salida is None:
        ruta_salida = (
            f"data/output/postmortem_{campaign_start.strftime('%b%d').lower()}_"
            f"{campaign_end.strftime('%b%d').lower()}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.html"
        )

    gmv_total = performance_df["GMV_TOTAL"].sum() if len(performance_df) else float("nan")
    ganancia_total = performance_df["GANANCIA_POR_ESTRATEGIA"].sum() if len(performance_df) else float("nan")
    n_peso_variable = int(performance_df["ES_PESO_VARIABLE"].sum()) if len(performance_df) else 0
    n_grupos = len(performance_df)

    # Mismo calculo que KpiCards.tsx: promedio de TRACCION_SKUS ignorando
    # nulos/infinitos (un SKU sin historico previo da traccion infinita).
    traccion_validas = (
        performance_df["TRACCION_SKUS"].replace([float("inf"), float("-inf")], pd.NA).dropna()
        if len(performance_df)
        else pd.Series(dtype=float)
    )
    traccion_promedio = traccion_validas.mean() if len(traccion_validas) else float("nan")

    # Adopcion/Planeado/tarjetas por origen: igual que /summary del backend
    # (routes.py::campaign_summary) - requieren resumen_df/total_planeado
    # porque performance_df ya excluye 'Sin promo' y no trae el universo
    # completo planeado (incluye SKUs planeados sin ninguna venta real).
    adopcion_pct = None
    if resumen_df is not None and len(resumen_df) and total_planeado:
        wknd = resumen_df[resumen_df["ORIGEN_CAMPANA"] == "WKND"]
        if len(wknd):
            adopcion_pct = round(wknd["SKU_TIENDAS_CON_PROMO_REAL"].iloc[0] / total_planeado * 100, 1)

    origen_cards = ""
    if resumen_df is not None and len(resumen_df):
        for _, row in resumen_df[resumen_df["ORIGEN_CAMPANA"] != "Sin promo"].iterrows():
            origen_cards += (
                f'<div class="kpi"><div class="label">{html.escape(str(row["ORIGEN_CAMPANA"]))}</div>'
                f'<div class="value">{_fmt_num(row["SKU_TIENDAS_CON_PROMO_REAL"])} / {_fmt_num(row["SKU_TIENDAS"])}</div></div>'
            )

    tabla_performance = _tabla_html(
        performance_df.head(top_n),
        [
            ("MECANICA_PLANEADA", "Mecanica propuesta", None),
            ("MECANICA_EJECUTADA", "Mecanica real", None),
            ("ORIGEN_CAMPANA", "Origen", None),
            ("STORE_ID", "Bodega", _fmt_bodega),
            ("DEPARTAMENTO", "Departamento", None),
            ("CATEGORIA", "Categoria", None),
            ("SKUS", "SKUs", _fmt_num),
            ("UNIDADES_TOTALES", "Unidades (FDS)", _fmt_num),
            ("GMV_TOTAL", "GMV", _fmt_moneda),
            ("MARGEN_PROMEDIO", "Margen prom.", _fmt_pct),
            ("UNIDADES_DIA", "Unidades/dia", _fmt_num),
            ("HISTORICO_UNIDADES_DIA_SKUS", "Historico (estos SKUs)", _fmt_num_ceil),
            ("TRACCION_SKUS", "Traccion", _fmt_ratio),
            ("INGRESO_SUPUESTO_SIN_PROMO", "Ingreso supuesto sin promo", _fmt_moneda),
            ("GANANCIA_POR_ESTRATEGIA", "Ganancia por estrategia", _fmt_moneda),
        ],
    )
    tabla_top_skus = _tabla_html(
        top_skus_df.head(top_n),
        [
            ("SKU", "SKU", _fmt_num),
            ("STORE_ID", "Tienda", None),
            ("DEPARTAMENTO", "Departamento", None),
            ("CATEGORIA", "Categoria", None),
            ("MECANICA_EJECUTADA", "Mecanica", None),
            ("ORIGEN_CAMPANA", "Origen", None),
            ("UNIDADES_TOTALES", "Unidades", _fmt_num),
            ("GMV_TOTAL", "GMV", _fmt_moneda),
        ],
    )
    tops_campana_html = _tops_campana_html(performance_df) if len(performance_df) else "<p class='nota'>Sin datos.</p>"
    # Validacion de redencion (validar_redencion_real) sacada del reporte a
    # proposito - el usuario aun no la entiende bien del todo. Queda
    # comentado (no borrado) porque eventualmente se va a volver a meter:
    #
    # tabla_redencion = _tabla_html(
    #     redemption_df,
    #     [
    #         ("BULK_STRATEGY", "Estrategia", None),
    #         ("TIER", "Tier", None),
    #         ("UNIDADES_TOTALES", "Unidades", _fmt_num),
    #         ("REDENCION_REAL", "Redencion real", lambda v: _fmt_pct(v * 100) if pd.notna(v) else "N/D"),
    #         ("REDENCION_SUPUESTA", "Redencion supuesta", lambda v: _fmt_pct(v * 100) if pd.notna(v) else "N/D"),
    #         ("DIFERENCIA", "Diferencia", lambda v: _fmt_pct(v * 100) if pd.notna(v) else "N/D"),
    #     ],
    # )
    # <section>
    #   <h2>Validacion de redencion real vs. supuesta</h2>
    #   <div class="table-wrap">{tabla_redencion}</div>
    #   <p class="nota">Redencion real desde FACT_FULFILLMENT_LINE (IS_DISCOUNT/IS_BULK_APPLIED) - directional, muestras chicas en algunos tiers.</p>
    # </section>

    html_doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Post-mortem {campaign_start.date()} a {campaign_end.date()}</title>
<style>
  :root {{
    --paper: #f6f7f3; --ink: #16231d; --muted: #56645b; --line: #dbe0d6;
    --good: #158158; --good-soft: #e4f2ec; --warn: #c8460f; --warn-soft: #fdece3;
    --card: #ffffff;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --paper: #10160f; --ink: #ecf1ec; --muted: #9fb0a4; --line: #253229;
      --good: #3ecf90; --good-soft: #163325; --warn: #ff8a5c; --warn-soft: #3a2015;
      --card: #161d15;
    }}
  }}
  :root[data-theme="dark"] {{
    --paper: #10160f; --ink: #ecf1ec; --muted: #9fb0a4; --line: #253229;
    --good: #3ecf90; --good-soft: #163325; --warn: #ff8a5c; --warn-soft: #3a2015; --card: #161d15;
  }}
  :root[data-theme="light"] {{
    --paper: #f6f7f3; --ink: #16231d; --muted: #56645b; --line: #dbe0d6;
    --good: #158158; --good-soft: #e4f2ec; --warn: #c8460f; --warn-soft: #fdece3; --card: #ffffff;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--paper); color: var(--ink);
    font-family: Arial, Helvetica, sans-serif; font-size: 15px; line-height: 1.55;
    margin: 0; padding: 3rem 1.5rem 5rem;
  }}
  .sheet {{ max-width: 1800px; margin: 0 auto; }}
  .masthead {{ border-bottom: 2px solid var(--ink); padding-bottom: 1.25rem; margin-bottom: 2rem; }}
  .masthead .eyebrow {{
    font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
    font-style: italic; color: var(--muted); font-size: 0.85rem; margin: 0 0 0.35rem;
  }}
  h1 {{
    font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
    font-weight: 400; font-size: 1.9rem; margin: 0; text-wrap: balance;
  }}
  .masthead .meta {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.4rem; }}
  h2 {{
    font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
    font-weight: 400; font-style: italic; font-size: 1.1rem; color: var(--muted);
    margin: 0 0 0.9rem;
  }}
  section {{ margin-top: 2.5rem; }}
  .kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1rem; }}
  @media (max-width: 640px) {{ .kpis {{ grid-template-columns: repeat(2, 1fr); }} }}
  .kpi {{
    background: var(--card); border: 1px solid var(--line); border-left: 3px solid var(--good);
    border-radius: 3px; padding: 0.9rem 1rem;
  }}
  .kpi .label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }}
  .kpi .value {{ font-size: 1.3rem; font-weight: 700; font-variant-numeric: tabular-nums; margin-top: 0.3rem; }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th, td {{ text-align: left; padding: 0.45rem 0.6rem; border-bottom: 1px solid var(--line); font-variant-numeric: tabular-nums; white-space: nowrap; }}
  th {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 700; }}
  .nota {{ font-size: 0.85rem; color: var(--muted); margin-top: 0.6rem; }}
  .chart-block + .chart-block {{ margin-top: 2rem; }}
  .chart-block h3 {{
    font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
    font-weight: 400; font-style: italic; font-size: 1rem; color: var(--ink); margin: 0 0 0.75rem;
  }}
  .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }}
  @media (max-width: 720px) {{ .chart-grid {{ grid-template-columns: 1fr; }} }}
  .chart-subtitle {{ font-weight: 700; margin: 0 0 0.5rem; color: var(--ink); }}
  .bar-chart {{ display: flex; flex-direction: column; gap: 2px; }}
  .bar-row {{ display: flex; align-items: center; gap: 0.5rem; }}
  .bar-label {{
    width: 220px; flex-shrink: 0; font-size: 0.8rem; text-align: right; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis; color: var(--ink);
  }}
  .bar-track {{ flex: 1; background: var(--line); border-radius: 4px; height: 20px; }}
  .bar-fill {{ height: 100%; border-radius: 4px; }}
  .bar-value {{ width: 100px; flex-shrink: 0; font-size: 0.8rem; font-weight: 700; color: var(--ink); }}
  @media print {{
    :root, :root[data-theme="light"], :root[data-theme="dark"] {{
      --paper: #10160f; --ink: #ecf1ec; --muted: #9fb0a4; --line: #253229;
      --good: #3ecf90; --good-soft: #163325; --warn: #ff8a5c; --warn-soft: #3a2015; --card: #161d15;
    }}
    * {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
    body {{ padding: 0; background: var(--paper) !important; color: var(--ink) !important; }}
    .sheet {{ max-width: 100%; }}
  }}
</style>
</head>
<body>
<div class="sheet">
  <div class="masthead">
    <p class="eyebrow">Post-mortem de campana</p>
    <h1>{campaign_start.date()} a {campaign_end.date()}</h1>
    <p class="meta">Generado {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} · Tiendas 9 (Atizapan) y 14 (Coyoacan)</p>
  </div>

  <div class="kpis">
    <div class="kpi"><div class="label">Planeado</div><div class="value">{_fmt_num(total_planeado) if total_planeado is not None else "N/D"}</div></div>
    <div class="kpi"><div class="label">Adopcion</div><div class="value">{f"{adopcion_pct}%" if adopcion_pct is not None else "N/D"}</div></div>
    <div class="kpi"><div class="label">GMV total (con campana)</div><div class="value">{_fmt_moneda(gmv_total)}</div></div>
    <div class="kpi"><div class="label">Ganancia por estrategia</div><div class="value">{_fmt_moneda(ganancia_total)}</div></div>
    <div class="kpi"><div class="label">Traccion promedio</div><div class="value">{_fmt_ratio(traccion_promedio)}</div></div>
    <div class="kpi"><div class="label">Grupos mecanica x categoria</div><div class="value">{n_grupos}</div></div>
    <!-- Grupos de peso variable sacado del KPI grid a proposito (pedido del
         usuario) - se mantiene la variable n_peso_variable porque la nota de
         abajo la sigue usando para explicar los N/D en la tabla.
    <div class="kpi"><div class="label">Grupos de peso variable (N/D)</div><div class="value">{n_peso_variable}</div></div>
    -->
    {origen_cards}
  </div>
  <!-- Nota de "Sin promo"/peso variable sacada del visual a proposito (pedido
       del usuario, mismo criterio que el KPI de peso variable de arriba).
  <p class="nota">"Sin promo" (sin oferta propuesta ni ejecutada) se excluye siempre de este reporte - no es relevante para un post-mortem de campana. {n_peso_variable} grupo(s) de peso variable tienen Ganancia por estrategia en N/D (precio en $/kg no comparable contra unidades en piezas).</p>
  -->

  <section>
    <h2>Performance por mecanica (top {top_n} por GMV)</h2>
    <div class="table-wrap">{tabla_performance}</div>
  </section>

  <section>
    <h2>Tops de la campana</h2>
    {tops_campana_html}
  </section>

  <section>
    <h2>SKUs mas vendidos (top {top_n})</h2>
    <div class="table-wrap">{tabla_top_skus}</div>
  </section>

  <!-- Validacion de redencion sacada a proposito (ver comentario arriba de
       html_doc) - no eliminada, el usuario aun no la entiende del todo pero
       eventualmente vuelve a entrar. -->
</div>
</body>
</html>
"""

    Path(ruta_salida).parent.mkdir(parents=True, exist_ok=True)
    Path(ruta_salida).write_text(html_doc, encoding="utf-8")
    return ruta_salida
