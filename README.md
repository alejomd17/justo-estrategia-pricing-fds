# Estrategia de Precios Fin de Semana (FDS)

## ¿Qué es esto?

Un análisis para armar la oferta de precios del próximo fin de semana (viernes 3 a domingo 5 de julio de 2026) en las tiendas Atizapán (#9) y Coyoacán (#14). El objetivo: elegir qué productos ofertar, con qué tipo de promoción y en qué día, de forma que la oferta sea atractiva para el cliente **sin que la tienda pierda rentabilidad**.

El resultado final es un archivo Excel (`data/output/estrategia_fds.xlsx`) con la lista de productos recomendados, la promoción sugerida para cada uno, y una proyección de cuánto se espera vender.

Esta versión integra dos líneas de trabajo — el modelo económico y los datos reales de Snowflake — ver la sección "Historial de este documento" al final para el detalle.

## Cómo correr la app

Tres comandos, uno por flujo — todos piden el login SSO por navegador una vez:

```bash
uv sync   # solo la primera vez

# 1. Crear la estrategia del proximo finde y subir el plan (default: proximo viernes-domingo)
uv run run_estrategias.py
uv run run_estrategias.py --inicio 2026-07-18 --fin 2026-07-20   # ventana explicita

# 2. Post-mortem completo de una campana ya ejecutada (default: la ultima subida)
#    Imprime el resumen en consola y genera el reporte HTML en data/output/
uv run run_postmortem.py
uv run run_postmortem.py --inicio 2026-07-11 --fin 2026-07-13

# 3. Dashboard interactivo (backend :8000 + frontend :3000 con un solo comando)
./run_dashboard.sh
```

`--help` en cualquiera de los dos `.py` muestra todas las opciones (filtros, `--sin-subir`, `--sin-refrescar`, etc.).

### Requisitos

- Python 3.13 + [uv](https://docs.astral.sh/uv/).
- Node.js (solo para el dashboard).
- Acceso a Snowflake vía SSO (login por navegador, `authenticator="externalbrowser"`) — configurar `.env` a partir de `.env.example` con tu correo `@justo.mx`.

### Notebook (`src/exploration.ipynb`) — solo exploración

El notebook sigue existiendo para explorar celda por celda y para casos raros que los scripts no cubren (ej. subir un plan real con formato de Excel no estándar, como las hojas GENRAL/Cervezas/Limpieza de la campaña 11-13 jul):

```bash
uv run jupyter lab src/exploration.ipynb
```

El flujo estándar (crear estrategia / medir post-mortem) ya no requiere el notebook — usar los scripts de arriba.

### Dashboard a mano (si no quieres el script)

```bash
# Backend (puerto 8000) - abre el navegador para el login SSO al arrancar
uv run uvicorn backend.api.main:app --reload --port 8000

# Frontend (puerto 3000), en otra terminal
cd frontend
npm install
npm run dev
```

Abrir `http://localhost:3000` — el selector de campañas lee directo de `WKND_PROMO_PLAN`, así que cualquier plan subido aparece ahí sin pasos extra.

## De dónde salen los datos

| Fuente | Qué aporta |
|---|---|
| `oportunidad.xlsx` | El universo de productos candidatos: ya viene filtrado para excluir marca propia y productos con promoción activa hoy. |
| `Descuentos comerciales.xlsx` | Lista negra de productos que nunca se deben ofertar, y el calendario de promociones ya comprometidas o eliminadas por el equipo comercial. |
| Catálogo de Snowflake | Departamento y categoría real de cada producto. |
| Elasticidad y ventas reales (Snowflake, Athenea) | Qué tan sensible es cada producto a cambios de precio, y cuánto se vende normalmente, para poder proyectar el efecto de la oferta — con datos reales por producto en vez de supuestos genéricos por categoría. |
| Histórico de promociones y transacciones (Snowflake) | Para comparar lo que el modelo habría proyectado contra lo que realmente pasó en ofertas pasadas (backtesting). |
| Estrategia FDS anterior (jun 2026) | Referencia de qué se hizo el fin de semana pasado. |

## Cómo se construyó la lista final

### 1. Punto de partida y exclusiones

Se parte del universo de productos elegibles y se descartan dos grupos antes de cualquier otro análisis:

- Productos en la **lista negra** comercial.
- Productos que **ya tienen una promoción comercial vigente** para ese mismo fin de semana (para no duplicar ofertas sobre el mismo producto).

### 2. Regla de rentabilidad: el piso de margen del 22%

Esta es la única restricción que no se negocia: **ningún producto puede terminar con un margen menor a 22% después de aplicar la oferta.** Se descartan de entrada los productos que ya tienen menos de 22% de margen hoy (no hay espacio para ofertarlos sin perder dinero), y el margen se calcula de forma consistente con cómo lo mide Finanzas (neto de IVA e IEPS, no sobre el precio de lista).

### 3. Filtro de sensibilidad al precio

También se descartan los productos marcados como "inelásticos" o sin dato de sensibilidad al precio — ofertar un producto que no reacciona a cambios de precio no genera ningún beneficio, solo resta margen.

### 4. Priorizar: no todos los productos merecen el mismo esfuerzo

Antes de decidir el descuento, cada producto recibe un **puntaje de prioridad** según qué tan bien responde a precio (elasticidad) y qué tan bien se está vendiendo ya (rotación) — un producto que no reacciona a precio **o** que casi no se vende no suma nada al multiplicar esos dos factores, así que queda con prioridad cero. Se suma un punto extra si el producto ya pesa mucho en las ventas (alto share) y otro si es afín al Mundial. Ese puntaje determina **qué tanto del colchón de margen se autoriza a gastar** en el descuento — los productos de alta prioridad pueden usar hasta 25% de su colchón; los de baja prioridad, mucho menos o nada. Adicionalmente, a los productos que **ya están posicionados como más baratos que la competencia** se les recorta un poco el presupuesto de descuento: esa percepción de precio ya está "comprada", pagarla dos veces es desperdicio.

### 5. Elegir la promoción de cada producto

Con el presupuesto de descuento ya definido (nunca más del colchón real de margen, y nunca más del 30% sin aprobación — ver punto 7), se decide la mecánica:

- Si alcanza para mecánicas tipo **"paga 3 y llévate 4" (4x3), "paga 4 y llévate 5" (5x4)** o similares, se usa esa mecánica — comunican mejor que un "% de descuento" suelto.
- Si no, se ofrece una mecánica flexible según el tipo de producto: **ahorro en pesos redondos** para productos de ticket alto (a partir de $150 — un "$50 de descuento" pesa más que un "%" cuando el producto es caro), **paquete a precio redondo** para productos baratos de alta rotación (ej. "3 x $99" — genera tráfico), o **% de descuento** por defecto.
- **Toda mecánica exige comprar 2 o 3 unidades como mínimo.** El precio de un solo producto en el estante nunca cambia — quien compra 1 unidad paga precio completo, y el carrito crece. Esto es deliberado: significa que el costo real de la promoción **solo lo paga quien realmente activa la mecánica**, no el 100% de lo que se vende ese día (ver punto 7).

### 6. Filtro nuevo: no descontar lo que ya se vende bien solo

Esta es la pieza más importante que se agregó en esta versión. Antes, el único criterio para dar un descuento era "¿el margen aguanta?" — pero que el margen aguante no significa que valga la pena. Ahora, para cada oferta candidata se proyecta **si la venta extra que generaría el descuento realmente compensa lo que se está regalando de margen**. Si no compensa — es decir, si el producto ya se vende bien por sí solo y el descuento no le va a mover la aguja lo suficiente — **la oferta se descarta**, aunque el margen técnicamente lo permitiera. Es la diferencia entre "puedo dar este descuento" y "vale la pena dar este descuento".

### 7. Tope de autonomía: 30% de descuento

Cualquier producto cuyo colchón de margen permitiría (y ameritaría) más de 30% de descuento **no se oferta automáticamente** — se marca como *"requiere aprobación Comercial"* y se reporta en el archivo final con el descuento que tendría sentido, para que el equipo decida caso por caso. El sistema nunca publica solo una oferta tan agresiva.

### 8. Detección de productos relacionados con el Mundial

Estamos en fechas de Mundial de fútbol (con partidos en México), así que se marcaron los productos típicos de "ver el partido en casa": cervezas, refrescos, botanas saladas, totopos, palomitas, salsas picantes. No hay mercancía oficial con licencia FIFA en el catálogo, así que esto es un proxy de consumo, revisado a mano contra falsos positivos. Estos productos reciben prioridad extra (punto 4) y **corren tanto Sábado como Domingo** — hay partidos los dos días de este fin de semana.

### 9. Día sugerido

Con precedencia (la primera regla que aplica gana):

1. **Mundial → Sábado y Domingo.**
2. **Despensa → Domingo** (categoría de reabastecimiento antes de empezar la semana).
3. **Alta rotación → Viernes** (capturar tráfico desde el arranque del fin de semana).
4. **Ahorro en pesos, ticket alto → Domingo** (la compra de reposición se decide con más calma).
5. **El resto → Sábado**, el día "bandera" del fin de semana.

### 10. ¿Cuánto se espera vender? (validación de demanda)

Para cada oferta se proyecta cuántas unidades por día se esperan vender, usando la sensibilidad al precio del producto y sus ventas actuales como punto de partida — con un ajuste adicional: **una oferta anunciada con badge/precio tachado en la app genera más respuesta que el mismo cambio de precio pasando desapercibido**, así que el modelo amplifica la sensibilidad base para reflejar ese efecto de visibilidad.

**Nivel de confianza de cada proyección.** No todas son igual de confiables:

- **Alta**: el producto tiene su propio dato real de sensibilidad al precio, y además ya tuvo una promoción real en el pasado con la que se puede comparar.
- **Media**: tiene su propio dato real, pero nunca se le ha probado una promoción real.
- **Baja**: no hay dato propio — se usó un promedio de su categoría, o en último caso una magnitud típica declarada.

**Prueba contra la realidad (backtesting).** Para los productos que sí tuvieron promociones reales en el pasado, se comparó lo que el modelo habría proyectado contra lo que realmente pasó en ventas. Esto valida no solo si la sensibilidad al precio está bien calibrada, sino también si el efecto de "visibilidad de la oferta" mencionado arriba es razonable — y dice en una frase si el modelo tiende a **quedarse corto o pasarse**.

## Qué NO hace este análisis (para ser transparentes)

- No garantiza que el producto se va a vender exactamente lo proyectado — es una estimación estadística, con niveles de confianza distintos por producto.
- No considera quiebres de inventario ni capacidad logística — solo pricing.
- La detección de "Mundial" es una aproximación por nombre de producto, no un dato oficial de licencia.
- El día sugerido usa una regla simple (categoría, rotación, ticket); no considera calendario de partidos, clima, ni otros factores externos al pricing.
- El efecto de "visibilidad de la oferta" (punto 10) y las tasas de redención por mecánica (qué fracción de las unidades realmente se compra con la mecánica activa) son supuestos declarados, no medidos directamente — el backtesting los pone a prueba, pero no los reemplaza con un dato 100% real.
- Los productos que requieren más de 30% de descuento no se ofertan solos — quedan pendientes de una decisión explícita de Comercial, no es una omisión del modelo.

## Cómo leer el archivo final

`data/output/estrategia_fds.xlsx` tiene 6 hojas:

- **Estrategia FDS**: solo los productos que sí llevan oferta (301 en la corrida más reciente) — departamento/categoría, mecánica, precio, margen resultante, día, si además requiere aprobación Comercial, cuánto se espera vender y qué tan confiable es esa proyección. Color verde = oferta normal, dorado = oferta Mundial, azul = requiere aprobación Comercial para ir más profundo.
- **Descartados**: el resto del universo (2,171), con el motivo exacto por el que no lleva oferta — Black list, campaña comercial vigente, margen base insuficiente, inelástico, violación del piso al redondear, o descartada por utilidad incremental negativa. Sirve para auditar el modelo sin volver al notebook.
- **Resumen**: indicadores globales, por día y por mecánica.
- **Escenarios**: la proyección en 3 versiones (conservador / base / optimista) para ver qué tan sensible es el resultado al supuesto más incierto del modelo.
- **Backtesting**: la comparación producto por producto entre lo proyectado y lo que realmente pasó en promociones pasadas.
- **Leyenda**: diccionario de todas las columnas.

## Resultados de la corrida actual (3-5 jul 2026)

| Indicador | Valor |
|---|---|
| Universo total | 2,472 productos-tienda |
| Ofertas asignadas | **301 (12.2%)** |
| Requieren aprobación Comercial (>30% de descuento) | 14 |
| Descuento exhibido promedio | 6.8% |
| Margen mínimo en cualquier oferta | 22.03% (nunca por debajo del piso) |

**Mecánica asignada:** SPON 166 · BNSP 75 · BNSDP 40 · 6x5 14 · 5x4 4 · 4x3 2.

**Proyección del fin de semana (escenario base), solo días de oferta de cada producto:**
- Unidades: 678 → 826 (**+21.8%**)
- GMV: \$39,831 → \$47,929 (**+20.3%**)
- Utilidad: \$12,405 → \$14,087 (**+13.6%**)

**Por día:** Viernes 100 ofertas ($715 utilidad incremental) · Sábado 100 ($290) · Domingo 86 ($132) · Sábado y Domingo (Mundial) 15 ($545, la de mayor utilidad incremental por oferta).

### ⚠️ El backtesting encontró un sesgo importante

Al comparar la proyección del modelo contra lo que realmente pasó en 24,485 promociones históricas reales, el modelo **sobreestima el uplift real en 25.3 puntos porcentuales en promedio** (error absoluto medio de 48.5 puntos). Esto es una señal seria, no un detalle técnico: significa que **la proyección de +21.8% en unidades y +13.6% en utilidad de esta corrida probablemente es optimista** — el supuesto de "multiplicador promocional" (que la demanda responde más a una oferta anunciada que a la sensibilidad de lista) parece estar calibrado muy alto.

Recomendación antes de tomar decisiones de negocio con estos números: bajar el multiplicador promocional (el cálculo sugiere algo cercano a 1.5 en vez de 2.0, aunque vale la pena revisarlo con más cuidado, no tomarlo como un ajuste final) y volver a correr, o al menos leer la columna "Confianza proyección" del Excel y tratar con más escepticismo las ofertas marcadas "Media"/"Baja". El guardrail de rentabilidad (punto 6) y el piso de margen (punto 2) siguen siendo válidos de todas formas — están basados en el margen real de cada producto, no en esta proyección de demanda.

## Historial de este documento

Esta estrategia es una integración de dos líneas de trabajo: el modelo económico (priorización por score, mecánicas de volumen, guardrail de utilidad incremental, tope de autonomía, escenarios de sensibilidad) se combinó con datos reales de Snowflake — reemplazando los supuestos declarados de sensibilidad al precio y ventas base por datos reales, agregando el departamento/categoría real de catálogo, y sumando el backtesting contra promociones históricas reales.
