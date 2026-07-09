# Campaña 10-12 jul 2026: aplicar lo aprendido del post-mortem 3-5 jul

## Contexto

El fin de semana 3-5 jul ya se ejecutó y se midió a fondo (ver `.claude/plans/vamos-a-cambiar-de-glowing-plum.md`, Fases 0-5). En el camino aparecieron 3 bugs de medición (ya corregidos: fan-out de campañas traslapadas, fragmentación de un SKU por mecánica-día, selección de "mecánica dominante") y 2 problemas de fondo sin resolver del todo: (a) para SKUs de peso variable (fruver, ej. Tomate Verde SKU 23827) el precio de catálogo está en $/kg pero la mecánica de precios lo trata como precio por pieza — generó una oferta ~14x más cara que el precio real ("3 x $87" en vez de ~"3 x $6-9") que nadie usó; (b) el costo/margen del post-mortem viene de `VW_PRICING_DASHBOARD`/`PRICE_JUSTO_MS_HISTORY`, pero `docs/diccionario_metricas_margen.csv` (diccionario oficial de Finanzas, agregado al repo el 2026-07-09) confirma que la fuente correcta es `ODS_MS_PRICING.PRICE_PRODUCT_FULFILLED_PER_ITEM.COST_NOMINAL` — la otra fuente candidata (`PRODUCT_PRICE_CATALOG_EVENT.NOMINAL_COST`, "motor de precios") está confirmada como stale desde 2026-06-26 e infla el margen +6.22 pts.

Llegó el nuevo insumo `data/inputs/oportunidad_10jul_12jul_2026.xlsx` (verificado: 3,225 filas válidas, 1,790 SKUs únicos, tiendas 9/14 — universo más grande que el de la campaña anterior) para construir la estrategia del fin de semana 10-12 jul. El objetivo de estas 3 fases es construir esa estrategia aplicando lo aprendido, sin repetir el error del tomate, y dejar la medición del post-mortem lista con la fuente de costo correcta.

**Cronograma**: hoy es 2026-07-09 (varios días después de que cerró la campaña 3-5 jul, tiempo que se usó para todo el post-mortem y las correcciones de esa sesión). El fin de semana 10-12 jul arranca **mañana** — la Fase 6 (salvaguarda de peso variable + Tema Mundial por categoría + construir y publicar la estrategia) es urgente, debe quedar lista hoy. La Fase 7 (migrar el costo del post-mortem) explícitamente no bloquea esto y puede hacerse después, incluso ya iniciado el fin de semana. La Fase 8 (ficha técnica) se entrega junto con la Fase 6, el mismo día, para que el usuario tenga el brief antes de que arranque la campaña.

Decisiones ya tomadas con el usuario:
- El fix de peso variable es **solo de marcado/revisión manual** — no cambia la mecánica asignada sola. `_asignar_mecanica` no se toca.
- La migración de costo/margen del post-mortem a la fuente oficial **sí entra en este plan**, aunque no bloquea construir la estrategia de este finde (aplica cuando se mida el 10-12 jul después).

## Fase 6 — Salvaguarda de peso variable + construir la estrategia 10-12 jul

**Nueva función en `backend/pricing/catalog.py`**: `get_medida_variable(cur) -> pd.DataFrame`. Estado real (2026-07-09): `PRICE_PRODUCT_FULFILLED_PER_ITEM` (la fuente que sugería el diccionario) resultó **bloqueada por permisos** ("SQL access control error"), sin acceso SELECT. Se resolvió con `MX_JUSTO_PROD.DM_CORE.FACT_FULFILLMENT_LINE` (tabla ya confirmada accesible, usada también en `validar_redencion_real`) — esa tabla trae `QUANTITY_KG` directo por línea; si un SKU+tienda alguna vez se vendió con `QUANTITY_KG > 0`, se vende por peso. Confirmado en vivo con una fila de muestra (SKU por pieza: `QUANTITY_PZ=1`, `QUANTITY_KG=0.000`). Devuelve `ES_PESO_VARIABLE` (bool) por SKU+STORE_ID.

**`backend/pricing/strategy.py` — `construir_estrategia`**: merge de `get_medida_variable` por SKU+STORE_ID justo después de `agregar_catalogo_real` (mismo punto donde ya se mergea `agregar_rotacion_real`).

**`exportar_excel`**: agregar `REQUIERE_REVISION_PESO_VARIABLE` a `cols_out` (cerca de `MOTIVO_SIN_OFERTA`/`ESTRATEGIA`); entrada nueva en la hoja `Leyenda` explicando el porqué (referencia al caso del SKU 23827: precio en $/kg tratado como precio por pieza); resaltar esas filas con un fill adicional distinto en la hoja "Estrategia FDS" (mismo patrón condicional que ya existe en `strategy.py:613-617` para `TEMA_MUNDIAL`/`REQUIERE_APROBACION` — agregar una condición más al `if/elif` de relleno, ej. un tono rojizo/naranja claro que no se confunda con los 3 ya usados). Agregar el conteo al resumen impreso en consola: `"Requieren revisión manual por peso variable: N de M ofertas"`.

**Tema Mundial por categoría, no solo por nombre**: `detectar_tema_mundial` hoy solo usa `PATRON_MUNDIAL` (regex sobre `Nombre`) — frágil, se le escapan productos de categorías obvias que no traen esas palabras exactas en el nombre. El usuario confirmó la lista completa de categorías del catálogo y eligió el alcance más amplio ("bebidas/botanas directas + acompañamientos + carnes de asador"). Agregar en `strategy.py` una constante `CATEGORIAS_MUNDIAL` con esas categorías reales:
`Cervezas y Coolers, Destilados, Vinos, Refrescos, Botanas, Snacks Dulces y Salados, Salsas y Aderezos, Queso, Carne de Res, Carne de Cerdo, Embutidos, Salchichas, Tocino`
y cambiar `detectar_tema_mundial` a `df["TEMA_MUNDIAL"] = df["Nombre"].str.contains(PATRON_MUNDIAL, na=False) | df["Categoria"].isin(CATEGORIAS_MUNDIAL)` — el regex de nombre se mantiene (sigue capturando casos fuera de estas categorías, ej. marcas de salsa específicas mencionadas ahí), se suma la categoría como una segunda vía, no un reemplazo. `Categoria` ya está disponible en `df` en este punto (se mergea antes, en `agregar_catalogo_real`), no hace falta reordenar el pipeline.

**Correr la campaña**: en el notebook, apuntar `RUTA_OPORTUNIDAD` a `data/inputs/oportunidad_10jul_12jul_2026.xlsx`, `WEEKEND_INICIO=2026-07-10`, `WEEKEND_FIN=2026-07-12`, correr `construir_estrategia` (usa automáticamente todo lo ya activo: `ROTACION_REAL_RATIO` en el `SCORE`, `Q0_DIA` desde `FACT_FULFILLMENT_LINE`). Revisar a mano cada fila marcada `REQUIERE_REVISION_PESO_VARIABLE` antes de dar la estrategia por lista. Subir el plan con `postmortem.subir_plan_y_crear_vistas` como ya se hace, para que el dashboard pueda medir esta campaña después.

## Fase 7 — Migrar costo/margen del post-mortem a la fuente oficial (BLOQUEADA, revertida)

**Estado real (2026-07-09)**: se implementó y luego se revirtió. `PRICE_PRODUCT_FULFILLED_PER_ITEM` (la fuente recomendada por el diccionario) no es accesible con el rol actual ("SQL access control error") — el mismo bloqueo que afectó la Fase 6. Como `crear_postmortem_promo_v` se llama automáticamente al subir el plan (`subir_plan_y_crear_vistas`), dejar la migración a medias hubiera roto la subida de la campaña 10-12 jul. Se revirtió `crear_postmortem_promo_v` a la fuente anterior (`PRICE_JUSTO_MS_HISTORY`, que sí funciona) para no bloquear hoy.

**Diseño original (para cuando se consiga el permiso)**: reemplazar la CTE `precio_costo_activo` por un cálculo sobre `PRICE_PRODUCT_FULFILLED_PER_ITEM` siguiendo las fórmulas de `docs/diccionario_metricas_margen.csv`:
- `cost_total = (COST_NOMINAL/1000 si MEASUREMENT_UNIT=GRAMOS, si no COST_NOMINAL) x QUANTITY`
- `MARGIN` expuesto en la vista = `margin_con_descuento_pct` = `(SUM(FINAL_PRICE_TOTAL) - SUM(cost_total)) / SUM(FINAL_PRICE_TOTAL) x 100` (el "GP%" del diccionario), no `MARGIN_PERCENTAGE` de `PRODUCT_PRICE_CATALOG_EVENT` (ese es el margen objetivo del motor, no el realizado).
- `FINAL_PRICE` expuesto = `FINAL_PRICE_TOTAL`.
- Punto sin resolver: si tomar la línea de pedido más reciente por SKU+tienda es un proxy razonable para "costo/precio vigente" con esta tabla (pensada para métricas de un período de órdenes, no necesariamente para esto).

**Pendiente**: pedir el permiso SELECT sobre `PRICE_PRODUCT_FULFILLED_PER_ITEM` y retomar esta migración cuando se consiga.

## Fase 8 — Ficha técnica de la campaña 10-12 jul (entregable)

Una vez corrida la Fase 6, producir un Artifact HTML tipo la ficha técnica del post-mortem 3-5 jul (mismo sistema de tokens/paleta), pero como brief hacia adelante. El usuario pidió explícitamente que explique **por qué** se construyó la estrategia así, no solo qué números salieron — la ficha debe tener una sección de justificación/razonamiento, no ser solo un reporte de cifras. Contenido:
- **Qué cambió desde la campaña pasada y por qué**: salvaguarda de peso variable (por qué existe — el caso del tomate SKU 23827), `CATEGORIAS_MUNDIAL` ampliado (por qué se amplió — el regex de nombre por sí solo era frágil), `ROTACION_REAL_RATIO`/`Q0_DIA` real ya activos (por qué se mantienen).
- **Universo y cobertura**: 3,225 filas / 1,790 SKUs evaluados, cuántos terminaron con oferta y por qué (guardrails de margen/elasticidad aplicados).
- **Categorías priorizadas y el porqué**: cuáles ya demostraron tracción alta el finde pasado (Destilados, Queso, Botanas, Sopas/Pastas) y por qué eso justifica priorizarlas de nuevo si vuelven a aparecer.
- **Qué requiere revisión humana y por qué**: conteo de filas `REQUIERE_REVISION_PESO_VARIABLE`, explicando la razón (precio en $/kg vs. mecánica pensada en pieza).
- **Riesgos aceptados y por qué se aceptaron de todas formas**: `Q0_DIA` en piezas (puede inflar `GMV_PROY_DIA`/`UTIL_PROY_DIA` ~15x en peso variable) — explicar que fue una decisión consciente del usuario, no un descuido.

## Verificación

1. ~~`SELECT DISTINCT MEASUREMENT_UNIT FROM PRICE_PRODUCT_FULFILLED_PER_ITEM`~~ — obsoleto, esa tabla está bloqueada por permisos. En su lugar, ya confirmado en vivo: `FACT_FULFILLMENT_LINE` trae `QUANTITY_KG`/`QUANTITY_PZ`/`MEASUREMENT_UNIT_ID`/`UNIT_AVERAGE_WEIGHT` reales.
2. Correr `catalog.get_medida_variable(cur)` suelto y confirmar que el SKU 23827 (Tomate Verde, tienda 9) sale `ES_PESO_VARIABLE = True`.
3. Correr `construir_estrategia` con `data/inputs/oportunidad_10jul_12jul_2026.xlsx` y fechas `2026-07-10`/`2026-07-12`; confirmar que el Excel trae `REQUIERE_REVISION_PESO_VARIABLE`, que esas filas están resaltadas distinto en "Estrategia FDS", y que el conteo impreso en consola coincide con `sum(REQUIERE_REVISION_PESO_VARIABLE)` del Excel.
4. Revisar a mano 2-3 filas marcadas: confirmar que de verdad son productos de peso variable (fruver u otros) y no falsos positivos.
5. La Fase 7 quedó revertida (bloqueada por permisos) — no requiere verificación por ahora. Cuando se consiga el permiso sobre `PRICE_PRODUCT_FULFILLED_PER_ITEM`:
   - Antes de recrear la vista, correr un `SELECT` de sanity check de `margin_con_descuento_pct` para 2-3 SKUs conocidos y comparar contra lo que ya se vio en el dashboard con la fuente vieja — la diferencia debe ser explicable (no un salto arbitrario).
   - Recrear `WKND_POSTMORTEM_PROMO_V` y confirmar que `performance_por_mecanica`/`top_skus` siguen corriendo sin error con la nueva fuente de `MARGIN`/`FINAL_PRICE`.
   - Confirmar que esto NO tocó `WKND_PROMO_PLAN` (el plan recién subido de la campaña 10-12 jul debe seguir igual).
6. Para la Fase 8 (ficha técnica 10-12 jul): confirmar que el Artifact refleja los números reales de la corrida (no los del post-mortem anterior) — universo, ofertas, conteo de peso variable, categorías priorizadas.
