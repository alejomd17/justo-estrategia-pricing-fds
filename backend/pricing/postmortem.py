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
- WKND_POSTMORTEM_PROMO_T (TABLE): materializacion de la vista anterior (ver
  materializar_postmortem) - lo que consultan el dashboard y el notebook.

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

# Materializacion de WKND_POSTMORTEM_PROMO_V (ver materializar_postmortem):
# la vista encadena joins pesados que Snowflake recalculaba en CADA query
# del dashboard (~11 por cambio de filtro). Todas las funciones de LECTURA
# consultan esta tabla; la vista sigue siendo la definicion canonica y solo
# se consulta al materializar.
TABLA_POSTMORTEM = f"{SCHEMA}.WKND_POSTMORTEM_PROMO_T"


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

    MARKETPLACE/SEGMENTO_USUARIO (agregado 2026-07-13): MASTER_ORDERLINE ya
    trae MARKETPLACE directo en la linea (justo/express/uber/rappi/didi,
    confirmado en vivo) - sin join. SEGMENTO_USUARIO (clasificacion OFICIAL
    de Justo: Recurrente/Reactivado/New, o 'Sin dato' si viene NULL/vacio -
    confirmado ~37% en blanco en la ventana 10-12 jul, causa no confirmada)
    sale de MASTER_ORDER.USER_STATUS_ORDER_DELIVERED via LEFT JOIN por
    ORDER_ID (ambas tablas lo tienen, join limpio 1 orden : N lineas, sin
    fan-out del lado de MASTER_ORDER).

    USER_ID (agregado 2026-07-14): tambien directo de MASTER_ORDERLINE, sin
    join extra - necesario para contar usuarios DISTINTOS por segmento
    (resumen_usuarios_por_segmento), no solo GMV/unidades agregados.

    Estas 3 columnas nuevas vuelven el grano de VENTAS mas fino
    (SKU+STORE_ID+FECHA+MARKETPLACE+SEGMENTO_USUARIO+USER_ID en vez de
    SKU+STORE_ID+FECHA) - el QUALIFY de abajo tiene que particionar tambien
    por ellas, si no colapsa de vuelta a la granularidad vieja y se pierde
    silenciosamente. Funciones que NO agrupan por estas columnas
    (performance_por_mecanica, top_skus) no se ven afectadas: es solo una
    particion mas fina de la misma suma.
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
                ml.PRODUCT_ID::VARCHAR                   AS SKU,
                ml.STORE_ID                              AS STORE_ID,
                TO_DATE(ml.DATETIME_DELIVERY)             AS FECHA,
                ml.MARKETPLACE                            AS MARKETPLACE,
                COALESCE(NULLIF(mo.USER_STATUS_ORDER_DELIVERED, ''), 'Sin dato') AS SEGMENTO_USUARIO,
                ml.USER_ID                                AS USER_ID,
                SUM(ml.QUANTITY_FULFILLED_PZ)             AS UNIDADES,
                SUM(ml.AMOUNT_GROSS_DELIVERED)            AS GMV
            FROM MX_JUSTO_PROD.DR_MASTER_TABLES.MASTER_ORDERLINE ml
            LEFT JOIN MX_JUSTO_PROD.DR_MASTER_TABLES.MASTER_ORDER mo
                ON ml.ORDER_ID = mo.ORDER_ID
            WHERE ml.STATUS_ORDER          = 'delivered'
              AND ml.STORE_ID              IN (9, 14)
              AND ml.QUANTITY_FULFILLED_PZ > 0
              AND ml.DATETIME_DELIVERY     >= '2025-01-01'
            GROUP BY 1, 2, 3, 4, 5, 6
        )
        SELECT
            v.SKU,
            v.STORE_ID,
            v.FECHA,
            v.MARKETPLACE,
            v.SEGMENTO_USUARIO,
            v.USER_ID,
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
            PARTITION BY v.SKU, v.STORE_ID, v.FECHA, v.MARKETPLACE, v.SEGMENTO_USUARIO, v.USER_ID
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
            r.MARKETPLACE,
            r.SEGMENTO_USUARIO,
            r.USER_ID,
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
            pva.MARKETPLACE,
            pva.SEGMENTO_USUARIO,
            pva.USER_ID,
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


def _filtros_departamento_categoria_tienda(
    departamento=None, categoria=None, store_id=None, origen=None, adopcion=None,
    marketplace=None, segmento_usuario=None, mecanica=None,
):
    """Cláusulas/params opcionales compartidas por todas las funciones de
    resumen (performance_por_mecanica, resumen_adopcion, top_skus,
    resumen_por_marketplace/segmento_usuario, los 4 cruces categoria/
    departamento x plataforma/segmento, resumen_usuarios_por_segmento,
    resumen_descuento_plataforma_segmento) - mismo patrón de condición
    armada en Python que ya usa catalog.get_pricing_dashboard con su
    parametro `skus`.

    `origen` filtra por ORIGEN_CAMPANA ('WKND' / 'Otra fuente' / 'Sin promo').
    `adopcion` filtra por si hubo mecanica real cargada o no ('con_mecanica'
    / 'sin_mecanica') - responde 'lo propusimos en WKND pero, ¿lo
    adoptaron?'. `marketplace`/`segmento_usuario`/`mecanica` son los 3
    filtros globales agregados 2026-07-14 (plataforma/tipo de cliente/
    mecanica real) - `mecanica` filtra por MECANICA_EJECUTADA (la real, no
    la planeada, de ahi el nombre corto)."""
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
    if marketplace:
        condiciones.append("MARKETPLACE = %s")
        params.append(marketplace)
    if segmento_usuario:
        condiciones.append("SEGMENTO_USUARIO = %s")
        params.append(segmento_usuario)
    if mecanica:
        condiciones.append("MECANICA_EJECUTADA = %s")
        params.append(mecanica)
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
    marketplace=None,
    segmento_usuario=None,
    mecanica=None,
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
        departamento, categoria, store_id, origen, adopcion=None,
        marketplace=marketplace, segmento_usuario=segmento_usuario, mecanica=mecanica,
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
        FROM {TABLA_POSTMORTEM}
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


def listar_mecanicas(cur) -> list:
    """MECANICA_EJECUTADA distintas ya vistas - para poblar el filtro
    global de 'Mecanica (real)' del dashboard. Lee la tabla materializada
    (no la vista WKND_PROMO_RESULTS_V, que re-computa los joins pesados
    sobre todo el historico solo para un DISTINCT)."""
    cur.execute(f"""
        SELECT DISTINCT MECANICA_EJECUTADA
        FROM {TABLA_POSTMORTEM}
        WHERE MECANICA_EJECUTADA IS NOT NULL AND MECANICA_EJECUTADA != 'Sin dato'
        ORDER BY MECANICA_EJECUTADA
    """)
    return [r[0] for r in cur.fetchall()]


def resumen_adopcion(
    cur,
    campaign_start: pd.Timestamp,
    campaign_end: pd.Timestamp,
    departamento=None,
    categoria=None,
    store_id=None,
    marketplace=None,
    segmento_usuario=None,
    mecanica=None,
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
    condiciones, params_filtro = _filtros_departamento_categoria_tienda(
        departamento, categoria, store_id,
        marketplace=marketplace, segmento_usuario=segmento_usuario, mecanica=mecanica,
    )
    where_clause = " AND ".join(["FECHA BETWEEN %s AND %s"] + condiciones)
    cur.execute(
        f"""
        SELECT
            ORIGEN_CAMPANA,
            COUNT(DISTINCT SKU || '-' || STORE_ID) AS SKU_TIENDAS,
            COUNT(DISTINCT CASE WHEN CON_PROMO THEN SKU || '-' || STORE_ID END) AS SKU_TIENDAS_CON_PROMO_REAL
        FROM {TABLA_POSTMORTEM}
        WHERE {where_clause}
        GROUP BY ORIGEN_CAMPANA
        ORDER BY SKU_TIENDAS DESC
        """,
        [campaign_start.date(), campaign_end.date()] + params_filtro,
    )
    columnas = [c[0] for c in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=columnas)


def resumen_por_marketplace(
    cur,
    campaign_start: pd.Timestamp,
    campaign_end: pd.Timestamp,
    departamento=None,
    categoria=None,
    store_id=None,
    origen=None,
    adopcion=None,
    marketplace=None,
    segmento_usuario=None,
    mecanica=None,
) -> pd.DataFrame:
    """Performance de la campana por plataforma (MARKETPLACE:
    justo/express/uber/rappi/didi - MASTER_ORDERLINE.MARKETPLACE, directo en
    la linea, confirmado en vivo). Responde '¿en que plataforma funciono
    mejor la campana?'. Mismo criterio que performance_por_mecanica: excluye
    ORIGEN_CAMPANA='Sin promo' siempre (post-mortem de CAMPAÑA, no reporte de
    ventas general).

    A diferencia de performance_por_mecanica, NO colapsa por SKU antes de
    aplicar `adopcion` - MARKETPLACE/SEGMENTO_USUARIO son atributos reales de
    cada venta (no una asignacion que varie dia a dia para el mismo SKU como
    MECANICA_EJECUTADA), asi que un GROUP BY directo sobre la vista ya
    refleja la suma real sin riesgo de fragmentar el total de un SKU."""
    condiciones, params_filtro = _filtros_departamento_categoria_tienda(
        departamento, categoria, store_id, origen, adopcion,
        marketplace=marketplace, segmento_usuario=segmento_usuario, mecanica=mecanica,
    )
    condiciones.append("ORIGEN_CAMPANA != 'Sin promo'")
    where_clause = " AND ".join(["FECHA BETWEEN %s AND %s"] + condiciones)
    cur.execute(
        f"""
        SELECT
            MARKETPLACE,
            COUNT(DISTINCT SKU) AS SKUS,
            SUM(UNIDADES) AS UNIDADES_TOTALES,
            SUM(GMV) AS GMV_TOTAL,
            AVG(MARGIN) AS MARGEN_PROMEDIO
        FROM {TABLA_POSTMORTEM}
        WHERE {where_clause}
        GROUP BY MARKETPLACE
        ORDER BY GMV_TOTAL DESC
        """,
        [campaign_start.date(), campaign_end.date()] + params_filtro,
    )
    columnas = [c[0] for c in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=columnas)
    if df.empty:
        return df
    df["GMV_TOTAL"] = df["GMV_TOTAL"].astype(float)
    df["MARGEN_PROMEDIO"] = df["MARGEN_PROMEDIO"].astype(float)
    df["TICKET_POR_UNIDAD"] = df["GMV_TOTAL"] / df["UNIDADES_TOTALES"]
    return df


def resumen_por_segmento_usuario(
    cur,
    campaign_start: pd.Timestamp,
    campaign_end: pd.Timestamp,
    departamento=None,
    categoria=None,
    store_id=None,
    origen=None,
    adopcion=None,
    marketplace=None,
    segmento_usuario=None,
    mecanica=None,
) -> pd.DataFrame:
    """Performance de la campana por SEGMENTO_USUARIO - clasificacion
    OFICIAL de Justo (MASTER_ORDER.USER_STATUS_ORDER_DELIVERED, via
    crear_fds_promo_results_v): 'Recurrente'/'Reactivado'/'New', o 'Sin dato'
    si venia NULL/vacio. Responde '¿la campana funciono mejor en
    recurrentes o en reactivados?'. Mismo criterio que
    performance_por_mecanica: excluye ORIGEN_CAMPANA='Sin promo' siempre.

    'Sin dato' (~37% de las ordenes en la ventana 10-12 jul, tiendas 9/14 -
    causa no confirmada, no explicada solo por marketplace externo, ver
    skill justo-snowflake-context) no se descarta - se muestra como una fila
    mas de la tabla, no oculta el resto de la comparacion."""
    condiciones, params_filtro = _filtros_departamento_categoria_tienda(
        departamento, categoria, store_id, origen, adopcion,
        marketplace=marketplace, segmento_usuario=segmento_usuario, mecanica=mecanica,
    )
    condiciones.append("ORIGEN_CAMPANA != 'Sin promo'")
    where_clause = " AND ".join(["FECHA BETWEEN %s AND %s"] + condiciones)
    cur.execute(
        f"""
        SELECT
            SEGMENTO_USUARIO,
            COUNT(DISTINCT SKU) AS SKUS,
            SUM(UNIDADES) AS UNIDADES_TOTALES,
            SUM(GMV) AS GMV_TOTAL,
            AVG(MARGIN) AS MARGEN_PROMEDIO
        FROM {TABLA_POSTMORTEM}
        WHERE {where_clause}
        GROUP BY SEGMENTO_USUARIO
        ORDER BY GMV_TOTAL DESC
        """,
        [campaign_start.date(), campaign_end.date()] + params_filtro,
    )
    columnas = [c[0] for c in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=columnas)
    if df.empty:
        return df
    df["GMV_TOTAL"] = df["GMV_TOTAL"].astype(float)
    df["MARGEN_PROMEDIO"] = df["MARGEN_PROMEDIO"].astype(float)
    df["TICKET_POR_UNIDAD"] = df["GMV_TOTAL"] / df["UNIDADES_TOTALES"]
    return df


def _resumen_por_dimension(performance_df: pd.DataFrame, columna: str) -> pd.DataFrame:
    """Rollup puro pandas (sin cur) de la salida de performance_por_mecanica
    a nivel `columna` (CATEGORIA o DEPARTAMENTO) - no re-consulta Snowflake,
    solo re-agrega lo que performance_por_mecanica ya trajo. SKUS se suma
    (no nunique) porque performance_por_mecanica ya cuenta SKU-tienda por
    grupo - sumar aqui preserva ese mismo criterio (un SKU vendido en 2
    tiendas cuenta 2 veces, igual que en resumen_adopcion).

    MARGEN_PROMEDIO se recalcula ponderado por GMV (no un promedio simple
    de promedios) - una categoria con una mecanica de $50k GMV y otra de
    $500 no deberia pesar igual en el margen combinado.

    TICKET_POR_UNIDAD = GMV_TOTAL / UNIDADES_TOTALES - precio promedio
    realizado por unidad vendida, para comparar entre categorias/
    departamentos sin que el tamano del grupo distorsione la lectura."""
    if not len(performance_df):
        return performance_df
    df = performance_df.copy()
    df["_GMV_X_MARGEN"] = df["GMV_TOTAL"] * df["MARGEN_PROMEDIO"]
    agg = (
        df.groupby(columna, dropna=False)
        .agg(
            SKUS=("SKUS", "sum"),
            UNIDADES_TOTALES=("UNIDADES_TOTALES", "sum"),
            GMV_TOTAL=("GMV_TOTAL", "sum"),
            _GMV_X_MARGEN=("_GMV_X_MARGEN", "sum"),
        )
        .reset_index()
    )
    agg["MARGEN_PROMEDIO"] = agg["_GMV_X_MARGEN"] / agg["GMV_TOTAL"]
    agg["TICKET_POR_UNIDAD"] = agg["GMV_TOTAL"] / agg["UNIDADES_TOTALES"]
    return agg.drop(columns="_GMV_X_MARGEN").sort_values("GMV_TOTAL", ascending=False)


def resumen_por_categoria(performance_df: pd.DataFrame) -> pd.DataFrame:
    """Rollup de performance_por_mecanica a nivel Categoria - GMV, unidades,
    SKUs, margen ponderado por GMV y ticket por unidad. Ver
    `_resumen_por_dimension` para el detalle de cada calculo."""
    return _resumen_por_dimension(performance_df, "CATEGORIA")


def resumen_por_departamento(performance_df: pd.DataFrame) -> pd.DataFrame:
    """Rollup de performance_por_mecanica a nivel Departamento - mismo
    calculo que resumen_por_categoria, un nivel mas arriba en la
    jerarquia."""
    return _resumen_por_dimension(performance_df, "DEPARTAMENTO")


def resumen_por_plataforma_y_segmento(
    cur,
    campaign_start: pd.Timestamp,
    campaign_end: pd.Timestamp,
    departamento=None,
    categoria=None,
    store_id=None,
    origen=None,
    adopcion=None,
    marketplace=None,
    segmento_usuario=None,
    mecanica=None,
) -> pd.DataFrame:
    """Cruce MARKETPLACE x SEGMENTO_USUARIO - responde si 'Sin dato' en
    tipo de cliente es en realidad marketplace externo (Justo no puede
    clasificar el usuario final de ordenes via Uber/Rappi/Didi, a
    diferencia de justo/express que si tienen la clasificacion oficial
    casi siempre poblada). Mismo criterio que performance_por_mecanica:
    excluye ORIGEN_CAMPANA='Sin promo' siempre."""
    condiciones, params_filtro = _filtros_departamento_categoria_tienda(
        departamento, categoria, store_id, origen, adopcion,
        marketplace=marketplace, segmento_usuario=segmento_usuario, mecanica=mecanica,
    )
    condiciones.append("ORIGEN_CAMPANA != 'Sin promo'")
    where_clause = " AND ".join(["FECHA BETWEEN %s AND %s"] + condiciones)
    cur.execute(
        f"""
        SELECT
            MARKETPLACE,
            SEGMENTO_USUARIO,
            COUNT(DISTINCT SKU) AS SKUS,
            SUM(UNIDADES) AS UNIDADES_TOTALES,
            SUM(GMV) AS GMV_TOTAL,
            AVG(MARGIN) AS MARGEN_PROMEDIO
        FROM {TABLA_POSTMORTEM}
        WHERE {where_clause}
        GROUP BY MARKETPLACE, SEGMENTO_USUARIO
        ORDER BY MARKETPLACE, GMV_TOTAL DESC
        """,
        [campaign_start.date(), campaign_end.date()] + params_filtro,
    )
    columnas = [c[0] for c in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=columnas)
    if df.empty:
        return df
    df["GMV_TOTAL"] = df["GMV_TOTAL"].astype(float)
    df["MARGEN_PROMEDIO"] = df["MARGEN_PROMEDIO"].astype(float)
    return df


def resumen_usuarios_por_segmento(
    cur,
    campaign_start: pd.Timestamp,
    campaign_end: pd.Timestamp,
    departamento=None,
    categoria=None,
    store_id=None,
    origen=None,
    adopcion=None,
    marketplace=None,
    segmento_usuario=None,
    mecanica=None,
) -> pd.DataFrame:
    """Usuarios DISTINTOS por SEGMENTO_USUARIO (no solo GMV/unidades
    agregados, que pueden estar concentrados en pocos usuarios) y ticket
    promedio POR USUARIO (GMV_TOTAL / N_USUARIOS - distinto de
    TICKET_POR_UNIDAD, que es GMV/unidades). Responde '¿cuanta GENTE
    distinta hay en cada segmento?', el dato que faltaba para poder decir
    si la campana funciono mejor en un segmento que en otro (comparar GMV
    total entre segmentos esta sesgado por el tamano de cada grupo).

    Requiere USER_ID (agregado a WKND_PROMO_RESULTS_V el 2026-07-14) - si
    corres esto contra una vista creada antes de esa fecha, USER_ID no
    existe todavia; correr crear_objetos_postmortem o subir_plan_y_crear_vistas
    de nuevo para recrear la vista con la columna."""
    condiciones, params_filtro = _filtros_departamento_categoria_tienda(
        departamento, categoria, store_id, origen, adopcion,
        marketplace=marketplace, segmento_usuario=segmento_usuario, mecanica=mecanica,
    )
    condiciones.append("ORIGEN_CAMPANA != 'Sin promo'")
    where_clause = " AND ".join(["FECHA BETWEEN %s AND %s"] + condiciones)
    cur.execute(
        f"""
        SELECT
            SEGMENTO_USUARIO,
            COUNT(DISTINCT USER_ID) AS USUARIOS_DISTINTOS,
            SUM(GMV) AS GMV_TOTAL
        FROM {TABLA_POSTMORTEM}
        WHERE {where_clause}
        GROUP BY SEGMENTO_USUARIO
        ORDER BY GMV_TOTAL DESC
        """,
        [campaign_start.date(), campaign_end.date()] + params_filtro,
    )
    columnas = [c[0] for c in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=columnas)
    if df.empty:
        return df
    df["GMV_TOTAL"] = df["GMV_TOTAL"].astype(float)
    df["TICKET_PROMEDIO_USUARIO"] = df["GMV_TOTAL"] / df["USUARIOS_DISTINTOS"]
    return df


def resumen_enganche_ticket(
    cur,
    campaign_start: pd.Timestamp,
    campaign_end: pd.Timestamp,
    store_id=None,
    marketplace=None,
) -> pd.DataFrame:
    """Enganche en el ticket COMPLETO: el ticket promedio por cliente de la
    campana (~$86 en 11-13 jul) solo cuenta lo gastado en PRODUCTOS DE LA
    CAMPANA - esta funcion responde la pregunta que sigue: ¿cuanto gasto
    ese cliente en TODO su carrito de la ventana (incluyendo lo que no
    estaba en promocion), y cuanto gasto el cliente que NO compro nada de
    la campana?

    Devuelve 2 filas (compraron campana / no compraron campana) con:
    - USUARIOS: clientes distintos del grupo.
    - TICKET_TOTAL_PROMEDIO: gasto TOTAL por cliente en la ventana (todo el
      carrito, cualquier origen - promovido o no).
    - GASTO_CAMPANA_PROMEDIO: de ese total, cuanto fue en productos de la
      campana (WKND con mecanica real).
    - GASTO_RESTO_PROMEDIO: el "arrastre" - lo demas que echaron al carrito.
    - PCT_CAMPANA_EN_TICKET: % del ticket que fue campana (a nivel grupo).

    Lectura: si el que compro campana tiene un ticket total mucho mayor que
    su gasto en campana, la promo arrastro carrito completo; compararlo
    contra el grupo que no compro campana da la referencia de si ese
    cliente ya era de ticket alto o el enganche es real. CAVEAT: es una
    comparacion descriptiva, no causal (el que busca la promo puede ser de
    por si un cliente de canasta grande).

    Solo acepta filtros de tienda/plataforma: filtrar por categoria o
    mecanica romperia la definicion de "ticket completo". Pedidos sin
    USER_ID identificable quedan fuera (no se puede seguir su carrito)."""
    condiciones = []
    params = []
    if store_id:
        condiciones.append("STORE_ID = %s")
        params.append(int(store_id))
    if marketplace:
        condiciones.append("MARKETPLACE = %s")
        params.append(marketplace)
    where_clause = " AND ".join(["FECHA BETWEEN %s AND %s", "USER_ID IS NOT NULL"] + condiciones)
    cur.execute(
        f"""
        WITH gasto_por_usuario AS (
            SELECT
                USER_ID,
                SUM(GMV) AS GMV_TOTAL,
                SUM(CASE WHEN ORIGEN_CAMPANA = 'WKND' AND MECANICA_EJECUTADA IS NOT NULL
                         THEN GMV ELSE 0 END) AS GMV_CAMPANA
            FROM {TABLA_POSTMORTEM}
            WHERE {where_clause}
            GROUP BY USER_ID
        )
        SELECT
            CASE WHEN GMV_CAMPANA > 0 THEN 'Compraron campaña' ELSE 'No compraron campaña' END AS GRUPO,
            COUNT(*) AS USUARIOS,
            SUM(GMV_TOTAL) AS GMV_TOTAL,
            SUM(GMV_CAMPANA) AS GMV_CAMPANA
        FROM gasto_por_usuario
        GROUP BY 1
        ORDER BY GRUPO
        """,
        [campaign_start.date(), campaign_end.date()] + params,
    )
    columnas = [c[0] for c in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=columnas)
    if df.empty:
        return df
    df["GMV_TOTAL"] = df["GMV_TOTAL"].astype(float)
    df["GMV_CAMPANA"] = df["GMV_CAMPANA"].astype(float)
    df["TICKET_TOTAL_PROMEDIO"] = df["GMV_TOTAL"] / df["USUARIOS"]
    df["GASTO_CAMPANA_PROMEDIO"] = df["GMV_CAMPANA"] / df["USUARIOS"]
    df["GASTO_RESTO_PROMEDIO"] = df["TICKET_TOTAL_PROMEDIO"] - df["GASTO_CAMPANA_PROMEDIO"]
    df["PCT_CAMPANA_EN_TICKET"] = df["GMV_CAMPANA"] / df["GMV_TOTAL"] * 100
    return df


def resumen_enganche_por_segmento(
    cur,
    campaign_start: pd.Timestamp,
    campaign_end: pd.Timestamp,
    store_id=None,
    marketplace=None,
) -> pd.DataFrame:
    """Enganche cruzado con tipo de cliente - responde '¿el REACTIVADO que
    compro campana termino comprando mas cosas, o no?': para cada
    SEGMENTO_USUARIO compara el gasto TOTAL en la ventana (todo el carrito)
    de quien compro algo de la campana vs. quien no compro nada, dentro del
    mismo segmento. Comparar dentro del segmento quita parte del sesgo de
    la comparacion global (un reactivado se compara contra otros
    reactivados, no contra recurrentes de canasta grande).

    Un cliente puede aparecer con 2 clasificaciones en la misma ventana
    (ej. su primera orden fue 'Reactivado' y la segunda ya 'Recurrente') -
    aqui se le asigna UN solo segmento, el de mayor gasto (dominante), para
    no contarlo doble. Por eso los conteos pueden diferir en +-1 de la
    tabla de usuarios por segmento (que cuenta al cliente en cada segmento
    donde aparecio).

    Mismos filtros/caveats que resumen_enganche_ticket: solo tienda/
    plataforma, requiere USER_ID (marketplaces externos quedan fuera),
    descriptivo no causal."""
    condiciones = []
    params = []
    if store_id:
        condiciones.append("STORE_ID = %s")
        params.append(int(store_id))
    if marketplace:
        condiciones.append("MARKETPLACE = %s")
        params.append(marketplace)
    where_clause = " AND ".join(["FECHA BETWEEN %s AND %s", "USER_ID IS NOT NULL"] + condiciones)
    cur.execute(
        f"""
        WITH gasto AS (
            SELECT
                USER_ID,
                SEGMENTO_USUARIO,
                SUM(GMV) AS GMV_SEG,
                SUM(CASE WHEN ORIGEN_CAMPANA = 'WKND' AND MECANICA_EJECUTADA IS NOT NULL
                         THEN GMV ELSE 0 END) AS GMV_CAMPANA_SEG
            FROM {TABLA_POSTMORTEM}
            WHERE {where_clause}
            GROUP BY USER_ID, SEGMENTO_USUARIO
        ),
        dominante AS (
            SELECT USER_ID, SEGMENTO_USUARIO,
                   ROW_NUMBER() OVER (PARTITION BY USER_ID ORDER BY GMV_SEG DESC) AS rn
            FROM gasto
        ),
        usuario AS (
            SELECT
                g.USER_ID,
                d.SEGMENTO_USUARIO,
                SUM(g.GMV_SEG) AS GMV_TOTAL,
                SUM(g.GMV_CAMPANA_SEG) AS GMV_CAMPANA
            FROM gasto g
            JOIN dominante d ON g.USER_ID = d.USER_ID AND d.rn = 1
            GROUP BY g.USER_ID, d.SEGMENTO_USUARIO
        )
        SELECT
            SEGMENTO_USUARIO,
            CASE WHEN GMV_CAMPANA > 0 THEN 'Compraron campaña' ELSE 'No compraron campaña' END AS GRUPO,
            COUNT(*) AS USUARIOS,
            SUM(GMV_TOTAL) AS GMV_TOTAL,
            SUM(GMV_CAMPANA) AS GMV_CAMPANA
        FROM usuario
        GROUP BY 1, 2
        ORDER BY SUM(GMV_TOTAL) DESC
        """,
        [campaign_start.date(), campaign_end.date()] + params,
    )
    columnas = [c[0] for c in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=columnas)
    if df.empty:
        return df
    df["GMV_TOTAL"] = df["GMV_TOTAL"].astype(float)
    df["GMV_CAMPANA"] = df["GMV_CAMPANA"].astype(float)
    df["TICKET_TOTAL_PROMEDIO"] = df["GMV_TOTAL"] / df["USUARIOS"]
    df["GASTO_CAMPANA_PROMEDIO"] = df["GMV_CAMPANA"] / df["USUARIOS"]
    df["GASTO_RESTO_PROMEDIO"] = df["TICKET_TOTAL_PROMEDIO"] - df["GASTO_CAMPANA_PROMEDIO"]
    df["PCT_CAMPANA_EN_TICKET"] = df["GMV_CAMPANA"] / df["GMV_TOTAL"] * 100
    return df


def resumen_enganche_por_orden(
    cur,
    campaign_start: pd.Timestamp,
    campaign_end: pd.Timestamp,
    store_id=None,
    marketplace=None,
) -> pd.DataFrame:
    """Enganche a nivel de ORDEN (la unidad correcta para 'gancho'): ¿el
    carrito donde venia un producto de la campana fue mas grande que un
    carrito normal? A diferencia de resumen_enganche_ticket (por CLIENTE,
    que mezcla tamano de carrito con frecuencia de compra en la ventana),
    aqui cada orden cuenta una vez.

    Devuelve 2 filas (ordenes con producto de campana / sin) con:
    - ORDENES: cuantas ordenes hay en el grupo.
    - TICKET_PROMEDIO_ORDEN: total del carrito promedio (todo el pedido,
      promovido o no).
    - GASTO_CAMPANA_PROMEDIO / GASTO_RESTO_PROMEDIO: dentro de las ordenes
      con campana, cuanto fue producto promovido y cuanto arrastre.
    - PCT_CAMPANA_EN_TICKET: % del carrito que fue campana (a nivel grupo).

    Consulta MASTER_ORDERLINE directo (la ventana son ~3 dias, query
    chica) porque la tabla materializada no guarda ORDER_ID; los SKUs "de
    campana" salen de la tabla materializada (WKND con mecanica real en la
    ventana). Bonus sobre la version por cliente: no necesita USER_ID, asi
    que las ordenes de marketplaces externos (uber/rappi/didi) SI entran.
    Misma advertencia: comparacion descriptiva, no causal."""
    condiciones = []
    params = []
    if store_id:
        condiciones.append("ml.STORE_ID = %s")
        params.append(int(store_id))
    if marketplace:
        condiciones.append("ml.MARKETPLACE = %s")
        params.append(marketplace)
    where_extra = (" AND " + " AND ".join(condiciones)) if condiciones else ""
    cur.execute(
        f"""
        WITH skus_campana AS (
            SELECT DISTINCT TRY_TO_NUMBER(SKU::VARCHAR) AS SKU, STORE_ID
            FROM {TABLA_POSTMORTEM}
            WHERE FECHA BETWEEN %s AND %s
              AND ORIGEN_CAMPANA = 'WKND'
              AND MECANICA_EJECUTADA IS NOT NULL
        ),
        ordenes AS (
            SELECT
                ml.ORDER_ID,
                SUM(ml.AMOUNT_GROSS_DELIVERED) AS TICKET_ORDEN,
                SUM(CASE WHEN sc.SKU IS NOT NULL THEN ml.AMOUNT_GROSS_DELIVERED ELSE 0 END) AS GMV_CAMPANA
            FROM MX_JUSTO_PROD.DR_MASTER_TABLES.MASTER_ORDERLINE ml
            LEFT JOIN skus_campana sc
                ON TRY_TO_NUMBER(ml.PRODUCT_ID::VARCHAR) = sc.SKU
               AND ml.STORE_ID = sc.STORE_ID
            WHERE ml.STATUS_ORDER = 'delivered'
              AND ml.STORE_ID IN (9, 14)
              AND ml.QUANTITY_FULFILLED_PZ > 0
              AND TO_DATE(ml.DATETIME_DELIVERY) BETWEEN %s AND %s{where_extra}
            GROUP BY ml.ORDER_ID
        )
        SELECT
            CASE WHEN GMV_CAMPANA > 0 THEN 'Ordenes con producto de campaña'
                 ELSE 'Ordenes sin producto de campaña' END AS GRUPO,
            COUNT(*) AS ORDENES,
            SUM(TICKET_ORDEN) AS GMV_TOTAL,
            SUM(GMV_CAMPANA) AS GMV_CAMPANA
        FROM ordenes
        GROUP BY 1
        ORDER BY GRUPO
        """,
        [campaign_start.date(), campaign_end.date(), campaign_start.date(), campaign_end.date()] + params,
    )
    columnas = [c[0] for c in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=columnas)
    if df.empty:
        return df
    df["GMV_TOTAL"] = df["GMV_TOTAL"].astype(float)
    df["GMV_CAMPANA"] = df["GMV_CAMPANA"].astype(float)
    df["TICKET_PROMEDIO_ORDEN"] = df["GMV_TOTAL"] / df["ORDENES"]
    df["GASTO_CAMPANA_PROMEDIO"] = df["GMV_CAMPANA"] / df["ORDENES"]
    df["GASTO_RESTO_PROMEDIO"] = df["TICKET_PROMEDIO_ORDEN"] - df["GASTO_CAMPANA_PROMEDIO"]
    df["PCT_CAMPANA_EN_TICKET"] = df["GMV_CAMPANA"] / df["GMV_TOTAL"] * 100
    return df


def resumen_descuento_plataforma_segmento(
    cur,
    campaign_start: pd.Timestamp,
    campaign_end: pd.Timestamp,
    departamento=None,
    categoria=None,
    store_id=None,
    origen=None,
    adopcion=None,
    marketplace=None,
    segmento_usuario=None,
    mecanica=None,
) -> pd.DataFrame:
    """Cruce de 3 dimensiones - MECANICA_EJECUTADA x MARKETPLACE x
    SEGMENTO_USUARIO - GMV/margen/unidades. Tabla granular a proposito (no
    grafica): responde preguntas puntuales tipo '¿el 5x4 en Uber le fue
    mejor a Recurrentes o a Nuevos?' filtrando/ordenando la tabla, no un
    resumen ya decidido de antemano. Mismo criterio que
    performance_por_mecanica: excluye ORIGEN_CAMPANA='Sin promo' siempre."""
    condiciones, params_filtro = _filtros_departamento_categoria_tienda(
        departamento, categoria, store_id, origen, adopcion,
        marketplace=marketplace, segmento_usuario=segmento_usuario, mecanica=mecanica,
    )
    condiciones.append("ORIGEN_CAMPANA != 'Sin promo'")
    where_clause = " AND ".join(["FECHA BETWEEN %s AND %s"] + condiciones)
    cur.execute(
        f"""
        SELECT
            MECANICA_EJECUTADA,
            MARKETPLACE,
            SEGMENTO_USUARIO,
            COUNT(DISTINCT SKU) AS SKUS,
            SUM(UNIDADES) AS UNIDADES_TOTALES,
            SUM(GMV) AS GMV_TOTAL,
            AVG(MARGIN) AS MARGEN_PROMEDIO
        FROM {TABLA_POSTMORTEM}
        WHERE {where_clause}
        GROUP BY MECANICA_EJECUTADA, MARKETPLACE, SEGMENTO_USUARIO
        ORDER BY GMV_TOTAL DESC
        """,
        [campaign_start.date(), campaign_end.date()] + params_filtro,
    )
    columnas = [c[0] for c in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=columnas)
    if df.empty:
        return df
    df["GMV_TOTAL"] = df["GMV_TOTAL"].astype(float)
    df["MARGEN_PROMEDIO"] = df["MARGEN_PROMEDIO"].astype(float)
    return df


def _resumen_por_dos_dimensiones(
    cur,
    campaign_start: pd.Timestamp,
    campaign_end: pd.Timestamp,
    col1: str,
    col2: str,
    departamento=None,
    categoria=None,
    store_id=None,
    origen=None,
    adopcion=None,
    marketplace=None,
    segmento_usuario=None,
    mecanica=None,
) -> pd.DataFrame:
    """Base compartida de los 4 cruces categoria/departamento x
    plataforma/segmento - mismo shape que resumen_descuento_plataforma_segmento
    pero con 2 dimensiones en vez de 3, mas TICKET_POR_UNIDAD calculado
    despues (GMV/unidades), igual que _resumen_por_dimension. `col1`/`col2`
    son nombres de columna literales (CATEGORIA/DEPARTAMENTO/MARKETPLACE/
    SEGMENTO_USUARIO) - no vienen del usuario final, no hay riesgo de
    inyeccion SQL aqui."""
    condiciones, params_filtro = _filtros_departamento_categoria_tienda(
        departamento, categoria, store_id, origen, adopcion,
        marketplace=marketplace, segmento_usuario=segmento_usuario, mecanica=mecanica,
    )
    condiciones.append("ORIGEN_CAMPANA != 'Sin promo'")
    where_clause = " AND ".join(["FECHA BETWEEN %s AND %s"] + condiciones)
    cur.execute(
        f"""
        SELECT
            {col1},
            {col2},
            COUNT(DISTINCT SKU) AS SKUS,
            SUM(UNIDADES) AS UNIDADES_TOTALES,
            SUM(GMV) AS GMV_TOTAL,
            AVG(MARGIN) AS MARGEN_PROMEDIO
        FROM {TABLA_POSTMORTEM}
        WHERE {where_clause}
        GROUP BY {col1}, {col2}
        ORDER BY GMV_TOTAL DESC
        """,
        [campaign_start.date(), campaign_end.date()] + params_filtro,
    )
    columnas = [c[0] for c in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=columnas)
    if df.empty:
        return df
    df["GMV_TOTAL"] = df["GMV_TOTAL"].astype(float)
    df["MARGEN_PROMEDIO"] = df["MARGEN_PROMEDIO"].astype(float)
    df["TICKET_POR_UNIDAD"] = df["GMV_TOTAL"] / df["UNIDADES_TOTALES"]
    return df


def resumen_por_categoria_y_plataforma(
    cur, campaign_start: pd.Timestamp, campaign_end: pd.Timestamp,
    departamento=None, categoria=None, store_id=None, origen=None, adopcion=None,
    marketplace=None, segmento_usuario=None, mecanica=None,
) -> pd.DataFrame:
    """GMV/ticket por unidad/unidades/margen por Categoria x MARKETPLACE -
    alimenta las barras agrupadas (una serie por plataforma) dentro de la
    seccion 'Performance por plataforma' - responde si el patron de una
    categoria se explica por mezcla de plataforma o es parejo en todas."""
    return _resumen_por_dos_dimensiones(
        cur, campaign_start, campaign_end, "CATEGORIA", "MARKETPLACE",
        departamento, categoria, store_id, origen, adopcion,
        marketplace, segmento_usuario, mecanica,
    )


def resumen_por_departamento_y_plataforma(
    cur, campaign_start: pd.Timestamp, campaign_end: pd.Timestamp,
    departamento=None, categoria=None, store_id=None, origen=None, adopcion=None,
    marketplace=None, segmento_usuario=None, mecanica=None,
) -> pd.DataFrame:
    """Mismo que resumen_por_categoria_y_plataforma, un nivel mas arriba en
    la jerarquia (Departamento x MARKETPLACE)."""
    return _resumen_por_dos_dimensiones(
        cur, campaign_start, campaign_end, "DEPARTAMENTO", "MARKETPLACE",
        departamento, categoria, store_id, origen, adopcion,
        marketplace, segmento_usuario, mecanica,
    )


def resumen_por_categoria_y_segmento(
    cur, campaign_start: pd.Timestamp, campaign_end: pd.Timestamp,
    departamento=None, categoria=None, store_id=None, origen=None, adopcion=None,
    marketplace=None, segmento_usuario=None, mecanica=None,
) -> pd.DataFrame:
    """GMV/ticket por unidad/unidades/margen por Categoria x
    SEGMENTO_USUARIO - alimenta las barras agrupadas (una serie por tipo de
    cliente) dentro de la seccion 'Performance por tipo de cliente'."""
    return _resumen_por_dos_dimensiones(
        cur, campaign_start, campaign_end, "CATEGORIA", "SEGMENTO_USUARIO",
        departamento, categoria, store_id, origen, adopcion,
        marketplace, segmento_usuario, mecanica,
    )


def resumen_por_departamento_y_segmento(
    cur, campaign_start: pd.Timestamp, campaign_end: pd.Timestamp,
    departamento=None, categoria=None, store_id=None, origen=None, adopcion=None,
    marketplace=None, segmento_usuario=None, mecanica=None,
) -> pd.DataFrame:
    """Mismo que resumen_por_categoria_y_segmento, un nivel mas arriba en la
    jerarquia (Departamento x SEGMENTO_USUARIO)."""
    return _resumen_por_dos_dimensiones(
        cur, campaign_start, campaign_end, "DEPARTAMENTO", "SEGMENTO_USUARIO",
        departamento, categoria, store_id, origen, adopcion,
        marketplace, segmento_usuario, mecanica,
    )


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
    marketplace=None,
    segmento_usuario=None,
    mecanica=None,
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
        departamento, categoria, store_id, origen, adopcion=None,
        marketplace=marketplace, segmento_usuario=segmento_usuario, mecanica=mecanica,
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
        FROM {TABLA_POSTMORTEM}
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
    materializar_postmortem(cur)
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
    materializar_postmortem(cur)


def materializar_postmortem(cur) -> None:
    """Congela WKND_POSTMORTEM_PROMO_V en la tabla WKND_POSTMORTEM_PROMO_T.

    La vista encadena joins pesados (DISCOUNT_CAMPAIGN_EVENT deduplicada x
    MASTER_ORDERLINE x MASTER_ORDER x PRICE_JUSTO_MS_HISTORY x catalogo) que
    Snowflake recalculaba en CADA query del dashboard - con ~11 queries por
    cambio de filtro, esa era la parte lenta que quedaba despues de cachear
    el baseline/peso variable. Materializar paga el costo UNA vez aqui;
    todas las funciones de lectura consultan TABLA_POSTMORTEM.

    Trade-off aceptado: la tabla es una FOTO al momento de materializar -
    ventas que lleguen despues a Snowflake no aparecen hasta re-materializar.
    Irrelevante para el post-mortem de una campana ya pasada; si se mide una
    campana EN CURSO, correr esta funcion (o subir_plan_y_crear_vistas, que
    la incluye) para refrescar."""
    cur.execute(f"CREATE OR REPLACE TABLE {TABLA_POSTMORTEM} AS SELECT * FROM {SCHEMA}.WKND_POSTMORTEM_PROMO_V")


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


_COLORES_PLATAFORMA_REPORTE = {
    "justo": "#158158", "express": "#058dc7", "uber": "#ed561b",
    "rappi": "#24cbe5", "didi": "#64e572",
}

_COLORES_SEGMENTO_REPORTE = {
    "Recurrente": "#158158", "Reactivado": "#058dc7", "New": "#ed561b", "Sin dato": "#888888",
}


def _pie_html(items: list[tuple[str, float]], colores: dict, fmt) -> str:
    """Pastel via CSS conic-gradient (sin JS/libreria) - mismo enfoque que
    PieChart.tsx del dashboard, para que documento y dashboard se vean
    iguales."""
    if not items:
        return "<p class='nota'>Sin datos.</p>"
    total = sum(v for _, v in items) or 1
    acumulado = 0.0
    stops = []
    leyenda = []
    for label, valor in items:
        inicio = acumulado / total * 100
        acumulado += valor
        fin = acumulado / total * 100
        color = colores.get(label, "#888888")
        stops.append(f"{color} {inicio:.2f}% {fin:.2f}%")
        pct = valor / total * 100
        leyenda.append(
            f'<div class="pie-legend-row">'
            f'<span class="pie-swatch" style="background:{color};"></span>'
            f"<span>{html.escape(label)}</span>"
            f'<span class="pie-legend-value">{fmt(valor)} ({pct:.1f}%)</span>'
            f"</div>"
        )
    gradiente = ", ".join(stops)
    return (
        f'<div class="pie-wrap">'
        f'<div class="pie" style="background:conic-gradient({gradiente});"></div>'
        f'<div class="pie-legend">{"".join(leyenda)}</div>'
        f"</div>"
    )


def _pivot_html(df: pd.DataFrame, index_col: str, columns_col: str, values_col: str, fmt) -> str:
    """Tabla pivote simple (filas=index_col, columnas=columns_col,
    celda=fmt(valor)) - no usa pandas.pivot para controlar el formato de
    celda y el manejo de NaN/'Sin dato' a mano. Filas y columnas ordenadas
    por su total de `values_col` descendente (no alfabetico - didi con $80
    no debe salir arriba de justo con $30k)."""
    if not len(df):
        return "<p class='nota'>Sin datos.</p>"
    tmp = df.copy()
    tmp["_IDX"] = tmp[index_col].fillna("N/D")
    tmp["_COL"] = tmp[columns_col].fillna("Sin dato")
    filas_idx = list(tmp.groupby("_IDX")[values_col].sum().sort_values(ascending=False).index)
    cols_idx = list(tmp.groupby("_COL")[values_col].sum().sort_values(ascending=False).index)
    mapa = {(r["_IDX"], r["_COL"]): r[values_col] for _, r in tmp.iterrows()}
    encabezados = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols_idx)
    filas_html = []
    for fi in filas_idx:
        celdas = "".join(f"<td>{fmt(mapa.get((fi, c)))}</td>" for c in cols_idx)
        filas_html.append(f"<tr><td>{html.escape(str(fi))}</td>{celdas}</tr>")
    return f"<table><thead><tr><th></th>{encabezados}</tr></thead><tbody>{''.join(filas_html)}</tbody></table>"


_GBAR_N_TICKS = 4  # 4 intervalos -> 5 lineas de eje


def _paso_bonito_eje(maximo: float) -> float:
    """Paso "bonito" para el eje Y: redondea maximo/_GBAR_N_TICKS hacia
    arriba al multiplo 1/1.25/1.5/2/2.5/3/4/5/6/8 x 10^k mas cercano, para
    ticks redondos ($1,250 / $2,500...) en vez de fracciones crudas del
    maximo ($4,783 / $3,587...) - espejo de pasoBonito en
    GroupedBarChart.tsx."""
    bruto = maximo / _GBAR_N_TICKS
    pot = 10 ** math.floor(math.log10(bruto)) if bruto > 0 else 1
    for m in (1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8):
        if m * pot >= bruto:
            return m * pot
    return 10 * pot


def _grouped_bar_html(groups: list[tuple[str, list[tuple[str, float]]]], color_map: dict, fmt, default_color: str = "#888888") -> str:
    """Barras verticales agrupadas (una serie por plataforma/tipo de
    cliente - color por `color_map`, un grupo por categoria/departamento) -
    mismo criterio que GroupedBarChart.tsx del dashboard, incluye eje Y con
    lineas guia + valores (sin esto una barra sola no dice nada - solo
    comparacion relativa sin escala). `groups` es
    [(label_grupo, [(label_serie, valor), ...]), ...]. Scroll horizontal
    via CSS si hay muchos grupos (ej. ~24 categorias) - el eje Y queda
    fijo, fuera del contenedor con scroll."""
    if not groups:
        return "<p class='nota'>Sin datos.</p>"
    valores = [v for _, bars in groups for _, v in bars]
    maximo = max((abs(v) for v in valores), default=1) or 1
    colores_vistos = {}
    for _, bars in groups:
        for serie, _ in bars:
            colores_vistos.setdefault(serie, color_map.get(serie, default_color))
    leyenda = "".join(
        f'<span class="gbar-legend-item"><span class="gbar-swatch" style="background:{color};"></span>{html.escape(str(serie))}</span>'
        for serie, color in colores_vistos.items()
    )

    paso = _paso_bonito_eje(maximo)
    top_escala = paso * _GBAR_N_TICKS
    ticks = [paso * (_GBAR_N_TICKS - i) for i in range(_GBAR_N_TICKS + 1)]
    eje_y = "".join(f"<span>{fmt(v)}</span>" for v in ticks)
    lineas_guia = "".join('<div class="gbar-gridline"></div>' for _ in ticks)

    grupos_html = []
    etiquetas_html = []
    for label_grupo, bars in groups:
        barras = "".join(
            f'<div class="gbar" title="{html.escape(str(label_grupo))} · {html.escape(str(serie))}: {fmt(valor)}" '
            f'style="height:{abs(valor) / top_escala * 100:.1f}%;background:{color_map.get(serie, default_color)};"></div>'
            for serie, valor in bars
        )
        grupos_html.append(f'<div class="gbar-bars">{barras}</div>')
        ancho = len(bars) * 16 - 2
        etiquetas_html.append(
            f'<div class="gbar-label" style="width:{ancho}px;" title="{html.escape(str(label_grupo))}">{html.escape(str(label_grupo))}</div>'
        )
    return (
        f'<div class="gbar-legend">{leyenda}</div>'
        f'<div class="gbar-wrap">'
        f'<div class="gbar-axis">{eje_y}</div>'
        f'<div class="gbar-scroll"><div class="gbar-inner">'
        f'<div class="gbar-gridlines">{lineas_guia}</div>'
        f'<div class="gbar-chart">{"".join(grupos_html)}</div>'
        f'<div class="gbar-labels">{"".join(etiquetas_html)}</div>'
        f"</div></div></div>"
    )


def _grid_cruzado_html(df: pd.DataFrame, label_col: str, series_col: str, color_map: dict) -> str:
    """4 graficas de barras agrupadas (GMV/ticket por unidad/unidades/
    margen), una serie por `series_col`, un grupo por `label_col` - mismo
    criterio que CrossDimensionSection.tsx del dashboard."""
    if df is None or not len(df):
        return "<p class='nota'>Sin datos.</p>"
    metricas = [
        ("GMV", "GMV_TOTAL", _fmt_moneda),
        ("Ticket por unidad", "TICKET_POR_UNIDAD", _fmt_moneda),
        ("Unidades", "UNIDADES_TOTALES", _fmt_num),
        ("Margen", "MARGEN_PROMEDIO", _fmt_pct),
    ]
    bloques = []
    for titulo, campo, fmt in metricas:
        sub = df.dropna(subset=[campo]).copy()
        sub["_LABEL"] = sub[label_col].fillna("N/D")
        sub["_SERIE"] = sub[series_col].fillna("N/D")
        groups = [(lbl, list(zip(g["_SERIE"], g[campo]))) for lbl, g in sub.groupby("_LABEL", sort=False)]
        bloques.append(
            f'<div class="chart-block"><h3>{html.escape(titulo)}</h3>{_grouped_bar_html(groups, color_map, fmt)}</div>'
        )
    return f'<div class="chart-grid-cross">{"".join(bloques)}</div>'


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
    marketplace_df: pd.DataFrame = None,
    segmento_usuario_df: pd.DataFrame = None,
    categoria_df: pd.DataFrame = None,
    departamento_df: pd.DataFrame = None,
    plataforma_segmento_df: pd.DataFrame = None,
    usuarios_segmento_df: pd.DataFrame = None,
    descuento_plataforma_segmento_df: pd.DataFrame = None,
    categoria_plataforma_df: pd.DataFrame = None,
    departamento_plataforma_df: pd.DataFrame = None,
    categoria_segmento_df: pd.DataFrame = None,
    departamento_segmento_df: pd.DataFrame = None,
    enganche_df: pd.DataFrame = None,
    enganche_orden_df: pd.DataFrame = None,
    enganche_segmento_df: pd.DataFrame = None,
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
    - se saco del reporte y del dashboard por decision del usuario.

    `marketplace_df` (salida de `resumen_por_marketplace`) y
    `segmento_usuario_df` (salida de `resumen_por_segmento_usuario`) son
    opcionales - si no se pasan, esas 2 secciones se omiten. Mismo criterio
    que `resumen_df`: se piden ya calculadas, no recalculadas aqui.

    `categoria_df`/`departamento_df` (salida de `resumen_por_categoria`/
    `resumen_por_departamento`), `plataforma_segmento_df` (salida de
    `resumen_por_plataforma_y_segmento`), `usuarios_segmento_df` (salida de
    `resumen_usuarios_por_segmento`) y `descuento_plataforma_segmento_df`
    (salida de `resumen_descuento_plataforma_segmento`) son igual de
    opcionales - mismo criterio, se omite la seccion correspondiente si no
    se pasan.

    `categoria_plataforma_df`/`departamento_plataforma_df` (salida de
    `resumen_por_categoria_y_plataforma`/`resumen_por_departamento_y_plataforma`)
    y `categoria_segmento_df`/`departamento_segmento_df` (salida de
    `resumen_por_categoria_y_segmento`/`resumen_por_departamento_y_segmento`)
    alimentan las barras agrupadas dentro de las secciones de plataforma/
    tipo de cliente respectivamente - TODO lo de plataforma vive junto en
    una sola seccion, TODO lo de tipo de cliente en otra, sin interfolar
    (pedido explicito del usuario) - mismo orden que App.tsx."""
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

    # Solo WKND - "Otra fuente" sacada del visual a proposito (pedido del
    # usuario 2026-07-14, mismo criterio que KpiCards.tsx): no responde a
    # los filtros y con WKND fijo solo confundia.
    origen_cards = ""
    if resumen_df is not None and len(resumen_df):
        for _, row in resumen_df[resumen_df["ORIGEN_CAMPANA"] == "WKND"].iterrows():
            origen_cards += (
                f'<div class="kpi"><div class="label">{html.escape(str(row["ORIGEN_CAMPANA"]))}</div>'
                f'<div class="value">{_fmt_num(row["SKU_TIENDAS_CON_PROMO_REAL"])} / {_fmt_num(row["SKU_TIENDAS"])}</div></div>'
            )

    # Resumen ejecutivo (mismos 5 KPIs y subtitulo que KpiCards.tsx del
    # dashboard) - "el resultado de la campana como tal, ya no granulado".
    pct_incremental = (
        ganancia_total / gmv_total * 100 if pd.notna(gmv_total) and gmv_total > 0 and pd.notna(ganancia_total) else None
    )
    clientes_reactivados = None
    if usuarios_segmento_df is not None and len(usuarios_segmento_df):
        fila = usuarios_segmento_df[usuarios_segmento_df["SEGMENTO_USUARIO"] == "Reactivado"]
        if len(fila):
            clientes_reactivados = int(fila["USUARIOS_DISTINTOS"].iloc[0])
    margen_reactivados = None
    if segmento_usuario_df is not None and len(segmento_usuario_df):
        fila = segmento_usuario_df[segmento_usuario_df["SEGMENTO_USUARIO"] == "Reactivado"]
        if len(fila) and pd.notna(fila["MARGEN_PROMEDIO"].iloc[0]):
            margen_reactivados = float(fila["MARGEN_PROMEDIO"].iloc[0])

    partes_subtitulo = []
    if pd.notna(traccion_promedio):
        partes_subtitulo.append(f"Lift {traccion_promedio:.2f}x vs ritmo historico")
    if resumen_df is not None and len(resumen_df):
        wknd_fila = resumen_df[resumen_df["ORIGEN_CAMPANA"] == "WKND"]
        if len(wknd_fila):
            partes_subtitulo.append(
                f"{_fmt_num(wknd_fila['SKU_TIENDAS_CON_PROMO_REAL'].iloc[0])} de "
                f"{_fmt_num(wknd_fila['SKU_TIENDAS'].iloc[0])} grupos ejecutados del plan WKND"
            )
    if len(performance_df) and pd.notna(gmv_total) and gmv_total > 0:
        por_tienda = performance_df.groupby("STORE_ID")["GMV_TOTAL"].sum().sort_values(ascending=False)
        tienda_top = por_tienda.index[0]
        partes_subtitulo.append(
            f"{_STORE_NAMES_REPORTE.get(int(tienda_top), tienda_top)} concentro "
            f"{por_tienda.iloc[0] / gmv_total * 100:.0f}% del GMV"
        )
    subtitulo_html = (
        f'<p class="meta">{html.escape(" · ".join(partes_subtitulo))}</p>' if partes_subtitulo else ""
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

    tabla_marketplace = pastel_marketplace_gmv = pastel_marketplace_vol = None
    if marketplace_df is not None and len(marketplace_df):
        tabla_marketplace = _tabla_html(
            marketplace_df,
            [
                ("MARKETPLACE", "Plataforma", None),
                ("SKUS", "SKUs", _fmt_num),
                ("UNIDADES_TOTALES", "Unidades", _fmt_num),
                ("GMV_TOTAL", "GMV", _fmt_moneda),
                ("MARGEN_PROMEDIO", "Margen prom.", _fmt_pct),
            ],
        )
        items_gmv = [
            (r["MARKETPLACE"] if pd.notna(r["MARKETPLACE"]) else "N/D", r["GMV_TOTAL"])
            for _, r in marketplace_df.sort_values("GMV_TOTAL", ascending=False).iterrows()
            if pd.notna(r["GMV_TOTAL"])
        ]
        items_vol = [
            (r["MARKETPLACE"] if pd.notna(r["MARKETPLACE"]) else "N/D", r["UNIDADES_TOTALES"])
            for _, r in marketplace_df.sort_values("UNIDADES_TOTALES", ascending=False).iterrows()
            if pd.notna(r["UNIDADES_TOTALES"])
        ]
        pastel_marketplace_gmv = _pie_html(items_gmv, _COLORES_PLATAFORMA_REPORTE, _fmt_moneda)
        pastel_marketplace_vol = _pie_html(items_vol, _COLORES_PLATAFORMA_REPORTE, _fmt_num)

    tabla_segmento_usuario = pastel_segmento_gmv = pastel_segmento_vol = None
    if segmento_usuario_df is not None and len(segmento_usuario_df):
        tabla_segmento_usuario = _tabla_html(
            segmento_usuario_df,
            [
                ("SEGMENTO_USUARIO", "Tipo de cliente", None),
                ("SKUS", "SKUs", _fmt_num),
                ("UNIDADES_TOTALES", "Unidades", _fmt_num),
                ("GMV_TOTAL", "GMV", _fmt_moneda),
                ("MARGEN_PROMEDIO", "Margen prom.", _fmt_pct),
            ],
        )
        items_gmv = [
            (r["SEGMENTO_USUARIO"] if pd.notna(r["SEGMENTO_USUARIO"]) else "Sin dato", r["GMV_TOTAL"])
            for _, r in segmento_usuario_df.sort_values("GMV_TOTAL", ascending=False).iterrows()
            if pd.notna(r["GMV_TOTAL"])
        ]
        items_vol = [
            (r["SEGMENTO_USUARIO"] if pd.notna(r["SEGMENTO_USUARIO"]) else "Sin dato", r["UNIDADES_TOTALES"])
            for _, r in segmento_usuario_df.sort_values("UNIDADES_TOTALES", ascending=False).iterrows()
            if pd.notna(r["UNIDADES_TOTALES"])
        ]
        pastel_segmento_gmv = _pie_html(items_gmv, _COLORES_SEGMENTO_REPORTE, _fmt_moneda)
        pastel_segmento_vol = _pie_html(items_vol, _COLORES_SEGMENTO_REPORTE, _fmt_num)

    def _grid_metricas_dimension(df: pd.DataFrame, columna: str, campos: set = None) -> str:
        """Graficas de barra (GMV/ticket por unidad/unidades/margen) para
        una dimension - mismo criterio que DimensionMetricsSection.tsx del
        dashboard. `campos` (set de nombres de columna) acota el subconjunto:
        las secciones de plataforma/tipo de cliente ya muestran GMV/Unidades
        como pastel, ahi solo se piden las 2 tasas para no duplicar."""
        if df is None or not len(df):
            return "<p class='nota'>Sin datos.</p>"
        metricas = [
            ("GMV", "GMV_TOTAL", _fmt_moneda),
            ("Ticket por unidad", "TICKET_POR_UNIDAD", _fmt_moneda),
            ("Unidades", "UNIDADES_TOTALES", _fmt_num),
            ("Margen", "MARGEN_PROMEDIO", _fmt_pct),
        ]
        if campos:
            metricas = [m for m in metricas if m[1] in campos]
        bloques = []
        for titulo, campo, fmt in metricas:
            sub = df.dropna(subset=[campo]).sort_values(campo, ascending=False)
            items = [(r[columna] if pd.notna(r[columna]) else "N/D", r[campo]) for _, r in sub.iterrows()]
            bloques.append(
                f'<div class="chart-block"><h3>{html.escape(titulo)}</h3>{_barras_html(items, _GOOD_REPORTE, fmt)}</div>'
            )
        return f'<div class="chart-grid">{"".join(bloques)}</div>'

    grid_categoria = _grid_metricas_dimension(categoria_df, "CATEGORIA")
    grid_departamento = _grid_metricas_dimension(departamento_df, "DEPARTAMENTO")
    grid_marketplace = _grid_metricas_dimension(
        marketplace_df, "MARKETPLACE", campos={"TICKET_POR_UNIDAD", "MARGEN_PROMEDIO"}
    )
    grid_segmento_usuario = _grid_metricas_dimension(
        segmento_usuario_df, "SEGMENTO_USUARIO", campos={"TICKET_POR_UNIDAD", "MARGEN_PROMEDIO"}
    )

    grid_categoria_plataforma = _grid_cruzado_html(categoria_plataforma_df, "CATEGORIA", "MARKETPLACE", _COLORES_PLATAFORMA_REPORTE)
    grid_departamento_plataforma = _grid_cruzado_html(departamento_plataforma_df, "DEPARTAMENTO", "MARKETPLACE", _COLORES_PLATAFORMA_REPORTE)
    grid_categoria_segmento = _grid_cruzado_html(categoria_segmento_df, "CATEGORIA", "SEGMENTO_USUARIO", _COLORES_SEGMENTO_REPORTE)
    grid_departamento_segmento = _grid_cruzado_html(departamento_segmento_df, "DEPARTAMENTO", "SEGMENTO_USUARIO", _COLORES_SEGMENTO_REPORTE)

    tabla_enganche = None
    if enganche_df is not None and len(enganche_df):
        tabla_enganche = _tabla_html(
            enganche_df,
            [
                ("GRUPO", "Grupo", None),
                ("USUARIOS", "Clientes", _fmt_num),
                ("TICKET_TOTAL_PROMEDIO", "Gasto TOTAL por cliente (ventana)", _fmt_moneda),
                ("GASTO_CAMPANA_PROMEDIO", "Gasto en campaña", _fmt_moneda),
                ("GASTO_RESTO_PROMEDIO", "Resto del carrito", _fmt_moneda),
                ("PCT_CAMPANA_EN_TICKET", "% campaña en el ticket", _fmt_pct),
            ],
        )

    tabla_enganche_segmento = grafica_enganche_segmento = None
    if enganche_segmento_df is not None and len(enganche_segmento_df):
        tabla_enganche_segmento = _tabla_html(
            enganche_segmento_df,
            [
                ("SEGMENTO_USUARIO", "Tipo de cliente", None),
                ("GRUPO", "Grupo", None),
                ("USUARIOS", "Clientes", _fmt_num),
                ("TICKET_TOTAL_PROMEDIO", "Gasto TOTAL por cliente (ventana)", _fmt_moneda),
                ("GASTO_CAMPANA_PROMEDIO", "Gasto en campaña", _fmt_moneda),
                ("GASTO_RESTO_PROMEDIO", "Resto del carrito", _fmt_moneda),
                ("PCT_CAMPANA_EN_TICKET", "% campaña en el ticket", _fmt_pct),
            ],
        )
        # Barras comparativas (verde=compro campaña, gris=no) por segmento -
        # mismo visual que EngancheTable.tsx del dashboard.
        colores_enganche = {"Compraron campaña": _GOOD_REPORTE, "No compraron campaña": "#888888"}
        seg_tmp = enganche_segmento_df.dropna(subset=["TICKET_TOTAL_PROMEDIO"]).copy()
        seg_tmp["_SEG"] = seg_tmp["SEGMENTO_USUARIO"].fillna("Sin dato")
        grupos_enganche = [
            (seg, list(zip(g.sort_values("GRUPO")["GRUPO"], g.sort_values("GRUPO")["TICKET_TOTAL_PROMEDIO"])))
            for seg, g in seg_tmp.groupby("_SEG", sort=False)
        ]
        grafica_enganche_segmento = _grouped_bar_html(grupos_enganche, colores_enganche, _fmt_moneda)

    tabla_enganche_orden = None
    if enganche_orden_df is not None and len(enganche_orden_df):
        tabla_enganche_orden = _tabla_html(
            enganche_orden_df,
            [
                ("GRUPO", "Grupo", None),
                ("ORDENES", "Ordenes", _fmt_num),
                ("TICKET_PROMEDIO_ORDEN", "Ticket promedio por orden", _fmt_moneda),
                ("GASTO_CAMPANA_PROMEDIO", "Gasto en campaña", _fmt_moneda),
                ("GASTO_RESTO_PROMEDIO", "Resto del carrito", _fmt_moneda),
                ("PCT_CAMPANA_EN_TICKET", "% campaña en el ticket", _fmt_pct),
            ],
        )

    tabla_plataforma_segmento = None
    if plataforma_segmento_df is not None and len(plataforma_segmento_df):
        tabla_plataforma_segmento = _pivot_html(
            plataforma_segmento_df, "MARKETPLACE", "SEGMENTO_USUARIO", "GMV_TOTAL", _fmt_moneda
        )

    tabla_usuarios_segmento = None
    if usuarios_segmento_df is not None and len(usuarios_segmento_df):
        tabla_usuarios_segmento = _tabla_html(
            usuarios_segmento_df,
            [
                ("SEGMENTO_USUARIO", "Tipo de cliente", None),
                ("USUARIOS_DISTINTOS", "Usuarios distintos", _fmt_num),
                ("GMV_TOTAL", "GMV", _fmt_moneda),
                ("TICKET_PROMEDIO_USUARIO", "Ticket promedio por usuario", _fmt_moneda),
            ],
        )

    tabla_descuento_plataforma_segmento = None
    if descuento_plataforma_segmento_df is not None and len(descuento_plataforma_segmento_df):
        tabla_descuento_plataforma_segmento = _tabla_html(
            descuento_plataforma_segmento_df,
            [
                ("MECANICA_EJECUTADA", "Mecanica", None),
                ("MARKETPLACE", "Plataforma", None),
                ("SEGMENTO_USUARIO", "Tipo de cliente", None),
                ("SKUS", "SKUs", _fmt_num),
                ("UNIDADES_TOTALES", "Unidades", _fmt_num),
                ("GMV_TOTAL", "GMV", _fmt_moneda),
                ("MARGEN_PROMEDIO", "Margen prom.", _fmt_pct),
            ],
        )

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
  .kpi .sub {{ font-size: 0.75rem; color: var(--muted); margin-top: 0.15rem; }}
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
  .pie-wrap {{ display: flex; gap: 1.5rem; align-items: center; flex-wrap: wrap; margin: 1rem 0; }}
  .pie {{ width: 180px; height: 180px; border-radius: 50%; flex-shrink: 0; }}
  .pie-legend {{ display: flex; flex-direction: column; gap: 0.4rem; }}
  .pie-legend-row {{ display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; }}
  .pie-swatch {{ width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }}
  .pie-legend-value {{ font-weight: 700; color: var(--ink); }}
  .chart-grid-cross {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }}
  @media (max-width: 720px) {{ .chart-grid-cross {{ grid-template-columns: 1fr; }} }}
  .gbar-legend {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.75rem; font-size: 0.8rem; }}
  .gbar-legend-item {{ display: inline-flex; align-items: center; gap: 0.35rem; margin-right: 0.5rem; }}
  .gbar-swatch {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
  .gbar-wrap {{ display: flex; }}
  .gbar-axis {{
    display: flex; flex-direction: column; justify-content: space-between; height: 220px;
    margin-right: 0.5rem; font-size: 0.7rem; color: var(--ink); text-align: right; flex-shrink: 0;
  }}
  .gbar-scroll {{ overflow-x: auto; flex: 1; }}
  .gbar-inner {{ position: relative; min-width: fit-content; }}
  .gbar-gridlines {{
    position: absolute; inset: 0; height: 220px; display: flex; flex-direction: column;
    justify-content: space-between; pointer-events: none;
  }}
  .gbar-gridline {{ border-top: 1px solid var(--line); }}
  .gbar-chart {{ display: flex; align-items: flex-end; gap: 1.25rem; height: 220px; position: relative; }}
  .gbar-bars {{ display: flex; align-items: flex-end; gap: 2px; height: 220px; }}
  .gbar {{ width: 14px; border-radius: 2px 2px 0 0; }}
  .gbar-labels {{ display: flex; gap: 1.25rem; margin-top: 0.4rem; }}
  .gbar-label {{
    font-size: 0.7rem; color: var(--ink); writing-mode: vertical-rl; transform: rotate(180deg);
    max-height: 130px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }}
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
    <p class="eyebrow">Resultados de campaña</p>
    <h1>{campaign_start.date()} a {campaign_end.date()}</h1>
    <p class="meta">Generado {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} · Tiendas 9 (Atizapan) y 14 (Coyoacan)</p>
    {subtitulo_html}
  </div>

  <div class="kpis">
    <div class="kpi"><div class="label">GMV de campaña</div><div class="value">{_fmt_moneda(gmv_total)}</div></div>
    <div class="kpi"><div class="label">Venta incremental</div><div class="value">{_fmt_moneda(ganancia_total)}</div>{f'<div class="sub">{pct_incremental:.0f}% del GMV · vs ritmo historico</div>' if pct_incremental is not None else ''}</div>
    <div class="kpi"><div class="label">Lift vs historico</div><div class="value">{_fmt_ratio(traccion_promedio)}</div></div>
    <div class="kpi"><div class="label">Clientes reactivados</div><div class="value">{clientes_reactivados if clientes_reactivados is not None else "N/D"}</div></div>
    <div class="kpi"><div class="label">Margen en reactivados</div><div class="value">{_fmt_pct(margen_reactivados) if margen_reactivados is not None else "N/D"}</div></div>
    <div class="kpi"><div class="label">Planeado</div><div class="value">{_fmt_num(total_planeado) if total_planeado is not None else "N/D"}</div></div>
    <div class="kpi"><div class="label">Adopcion</div><div class="value">{f"{adopcion_pct}%" if adopcion_pct is not None else "N/D"}</div></div>
    <div class="kpi"><div class="label">Grupos mecanica x categoria</div><div class="value">{n_grupos}</div></div>
    <!-- Grupos de peso variable sacado del KPI grid a proposito (pedido del
         usuario) - se mantiene la variable n_peso_variable porque la nota de
         abajo la sigue usando para explicar los N/D en la tabla.
    <div class="kpi"><div class="label">Grupos de peso variable (N/D)</div><div class="value">{n_peso_variable}</div></div>
    -->
    {origen_cards}
  </div>
  <p class="nota">Venta incremental = GMV real menos lo que estos SKUs hubieran facturado a su ritmo historico (la "Ganancia por estrategia" de la tabla de abajo).</p>

  {f'''<section>
    <h2>Enganche: ticket completo</h2>
    {f"""<h3>Por orden (¿el carrito con promo fue mas grande?)</h3>
    <div class="table-wrap">{tabla_enganche_orden}</div>""" if tabla_enganche_orden else ""}
    {f"""<h3>Por cliente (gasto total en la ventana)</h3>
    <div class="table-wrap">{tabla_enganche}</div>""" if tabla_enganche else ""}
    {f"""<h3>Por tipo de cliente (¿el reactivado que compro campaña, compro mas?)</h3>
    {grafica_enganche_segmento}
    <div class="table-wrap">{tabla_enganche_segmento}</div>""" if tabla_enganche_segmento else ""}
    <p class="nota">"Resto del carrito" = lo que se llevo ademas de los productos de campaña. La vista por orden incluye marketplaces externos; las vistas por cliente/segmento no (requieren usuario identificable). Comparacion descriptiva, no causal: quien busca promos puede ser de por si un cliente de canasta grande.</p>
  </section>''' if tabla_enganche or tabla_enganche_orden or tabla_enganche_segmento else ''}
  <!-- Nota de "Sin promo"/peso variable sacada del visual a proposito (pedido
       del usuario, mismo criterio que el KPI de peso variable de arriba).
  <p class="nota">"Sin promo" (sin oferta propuesta ni ejecutada) se excluye siempre de este reporte - no es relevante para un post-mortem de campaña. {n_peso_variable} grupo(s) de peso variable tienen Ganancia por estrategia en N/D (precio en $/kg no comparable contra unidades en piezas).</p>
  -->

  <section>
    <h2>Performance por mecanica (top {top_n} por GMV)</h2>
    <div class="table-wrap">{tabla_performance}</div>
  </section>

  <section>
    <h2>Tops de la campaña</h2>
    {tops_campana_html}
  </section>

  <section>
    <h2>SKUs mas vendidos (top {top_n})</h2>
    <div class="table-wrap">{tabla_top_skus}</div>
  </section>

  {f'''<section>
    <h2>GMV, ticket por unidad, unidades y margen por categoria</h2>
    {grid_categoria}
  </section>''' if categoria_df is not None and len(categoria_df) else ''}

  {f'''<section>
    <h2>GMV, ticket por unidad, unidades y margen por departamento</h2>
    {grid_departamento}
  </section>''' if departamento_df is not None and len(departamento_df) else ''}

  {f'''<section>
    <h2>Performance por plataforma</h2>
    <div class="table-wrap">{tabla_marketplace}</div>
    <p class="nota">Plataforma = MARKETPLACE de MASTER_ORDERLINE (justo/express/uber/rappi/didi) - en cual canal vendio mas la campaña. Pastel solo para GMV/Volumen (son "parte de un todo"); ticket por unidad y margen son tasas/promedios, se muestran como barras.</p>
    <div class="chart-grid">
      <div class="chart-block">{pastel_marketplace_gmv}</div>
      <div class="chart-block">{pastel_marketplace_vol}</div>
    </div>
    {grid_marketplace}
    <h3>Categoria x plataforma</h3>
    {grid_categoria_plataforma}
    <h3>Departamento x plataforma</h3>
    {grid_departamento_plataforma}
  </section>''' if tabla_marketplace else ''}

  {f'''<section>
    <h2>Performance por tipo de cliente</h2>
    <div class="table-wrap">{tabla_segmento_usuario}</div>
    <p class="nota">Tipo de cliente = clasificacion oficial de Justo (MASTER_ORDER.USER_STATUS_ORDER_DELIVERED): Nuevo/Recurrente/Reactivado. "Sin dato" es una orden sin esa clasificacion (no se descarta).</p>
    <div class="chart-grid">
      <div class="chart-block">{pastel_segmento_gmv}</div>
      <div class="chart-block">{pastel_segmento_vol}</div>
    </div>
    {grid_segmento_usuario}
    <h3>Categoria x tipo de cliente</h3>
    {grid_categoria_segmento}
    <h3>Departamento x tipo de cliente</h3>
    {grid_departamento_segmento}
    {f"""<h3>Usuarios distintos y ticket promedio por usuario</h3>
    <div class="table-wrap">{tabla_usuarios_segmento}</div>
    <p class="nota">Usuarios distintos (no solo GMV/unidades, que pueden estar concentrados en pocas personas) y ticket promedio POR USUARIO - compara segmentos sin el sesgo de tamano de grupo.</p>""" if tabla_usuarios_segmento else ""}
    {f"""<h3>Cruce plataforma x tipo de cliente</h3>
    <div class="table-wrap">{tabla_plataforma_segmento}</div>
    <p class="nota">GMV por plataforma x tipo de cliente - si "Sin dato" se concentra en uber/rappi/didi (no en justo/express), confirma que es marketplace externo sin clasificar.</p>""" if tabla_plataforma_segmento else ""}
  </section>''' if tabla_segmento_usuario else ''}

  {f'''<section>
    <h2>GMV, margen y volumen por mecanica x plataforma x tipo de cliente</h2>
    <div class="table-wrap">{tabla_descuento_plataforma_segmento}</div>
    <p class="nota">Tabla granular a proposito (no grafica) - para preguntas puntuales tipo "¿el 5x4 en Uber le fue mejor a Recurrentes o a Nuevos?".</p>
  </section>''' if tabla_descuento_plataforma_segmento else ''}

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
