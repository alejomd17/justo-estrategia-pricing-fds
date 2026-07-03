# Guión de presentación — Estrategia de Precios FDS 3-5 julio 2026

**Objetivo de esta presentación:** que el equipo entienda cómo usar la estrategia de precios, y la acepte porque está construida sobre análisis real de datos — históricos de venta, elasticidad por producto, y validación contra promociones pasadas — no sobre intuición.

Guión slide por slide (9 slides). Cada slide trae: **título**, **contenido** y **habla** (lo que dices en voz).

---

## Slide 1 — Portada y el problema

**Contenido:**
Estrategia de Precios Fin de Semana — Viernes 3 a Domingo 5 de julio 2026
Tiendas Atizapán (#9) y Coyoacán (#14)

¿Qué productos ofertar? ¿Con qué tanto descuento? ¿Vale la pena, o el producto se vende bien solo? ¿Qué día?

**Habla:**
"Hasta ahora, elegir la oferta de fin de semana era manual y basado en intuición. Lo que les voy a mostrar responde estas 4 preguntas para cada uno de los 2,472 productos-tienda del catálogo, con datos reales de los sistemas — no supuestos."

---

## Slide 2 — Por qué pueden confiar en esto: es 100% data-driven

**Contenido:**
- **Margen real** de cada producto (Finanzas), no estimado.
- **Elasticidad real por producto** — qué tan sensible es cada uno al precio, medida con su propio histórico de ventas (Snowflake / Athenea), no un promedio genérico por categoría.
- **Validado contra 24,485 promociones reales del pasado** — no es una proyección a ciegas, se comprobó contra lo que de verdad pasó.

**Habla:**
"La diferencia clave de este modelo es que cada decisión tiene un dato real detrás. No decidimos qué producto ofertar por instinto — lo decidimos porque sabemos, con datos históricos de ese producto específico, cómo reacciona al precio."

---

## Slide 3 — Las reglas del modelo

**Contenido:**
- **Piso duro: 22% de margen mínimo** después de la oferta, calculado igual que lo audita Finanzas.
- **Priorización por datos**: cada producto recibe un puntaje según su sensibilidad real al precio y qué tan bien se vende ya.
- **Mecánica de oferta** según el perfil del producto (2x1, 3x2, paquetes, % o pesos de descuento) — siempre con mínimo de unidades, para que el costo real de la promoción solo lo pague quien la activa.

**Habla:**
"Ninguna de estas reglas es arbitraria — cada una está diseñada para proteger la rentabilidad mientras se maximiza el atractivo para el cliente."

---

## Slide 4 — ⭐ Dos filtros que hacen la diferencia

**Contenido:**
- **No se descuenta lo que ya se vende solo**: se proyecta si la venta extra compensa el margen regalado, usando la elasticidad real del producto. Si no compensa, se descarta — **229 productos** cayeron aquí.
- **Tope de autonomía 30%**: nada se oferta solo con más de 30% de descuento. Los que necesitarían más (**14 productos**) quedan marcados para aprobación de Comercial.

**Habla:**
"Esto es lo que hace que el modelo sea confiable para aceptar sin revisar cada producto uno por uno: filtra automáticamente lo que no tiene sentido económico, y escala a ustedes lo que sí requiere una decisión humana."

---

## Slide 5 — Contexto de temporada y ejecución

**Contenido:**
- **Mundial de fútbol**: productos afines (cerveza, refrescos, botanas) con prioridad extra, ofertados **Sábado y Domingo**.
- **Día de cada oferta**: Mundial → Sáb+Dom · Despensa → Domingo · Alta rotación → Viernes · Ticket alto → Domingo · resto → Sábado.

**Habla:**
"Aprovechamos el contexto del Mundial en México, y repartimos el resto del catálogo según cuándo compra cada tipo de producto."

---

## Slide 6 — Resultados de esta corrida

**Contenido:**
| Indicador | Valor |
|---|---|
| Ofertas asignadas | **301 de 2,472 (12.2%)** |
| Pendientes de aprobación Comercial | 14 |
| Margen mínimo en cualquier oferta | 22.03% |

Proyección del fin de semana: Unidades +21.8% · GMV +20.3% · Utilidad **+13.6%**

**Habla:**
"301 ofertas concretas, cada una con su margen protegido y su razón de negocio. El resto del catálogo — 2,171 productos — también tiene una decisión documentada de por qué no se le dio oferta."

---

## Slide 7 — Cómo validamos el modelo antes de confiar en él

**Contenido:**
- Comparamos lo que el modelo habría proyectado en 24,485 promociones **que ya pasaron**, contra lo que realmente se vendió.
- Encontramos que el modelo sobreestima el crecimiento de ventas en ~25 puntos — y por eso **ya sabemos que hay que ajustar el supuesto de "efecto de la oferta"** antes de usar esa proyección para decisiones de inventario.
- Lo que **no** depende de ese ajuste: el margen (22%) y qué productos/mecánica ofertar — es matemática de costos, ya validada.

**Habla:**
"Les muestro esto porque es la prueba de que no nos quedamos con la primera proyección — la sometimos a la realidad, encontramos dónde ajustar, y separamos claramente qué parte del modelo es sólida hoy (el margen y la selección de productos) de qué parte estamos afinando (cuánto exactamente va a subir la venta). Esto es exactamente el tipo de rigor que buscamos que le dé confianza al equipo."

---

## Slide 8 — Cómo usar esto la próxima semana

**Contenido:**
1. **Comercial**: revisar y aprobar/rechazar los 14 productos pendientes en la hoja `Estrategia FDS`.
2. **Ejecución**: cargar las 301 ofertas con su mecánica y precio tal como aparecen en el archivo.
3. **Auditoría**: cualquier producto sin oferta tiene su motivo en la hoja `Descartados` — no hay que adivinar por qué se excluyó.
4. **Ciclo de mejora**: al terminar el fin de semana, comparamos lo vendido contra lo proyectado — eso alimenta el próximo backtesting y afina el modelo.

**Habla:**
"Esto está diseñado para que se pueda usar de inmediato: no hace falta reinterpretar nada, el archivo trae la decisión y el porqué de cada producto. Y cada vez que lo corramos, va a estar mejor calibrado que la vez anterior, porque se valida contra resultados reales."

---

## Slide 9 — Cierre: por qué aceptarlo

**Contenido:**
- Basado en margen real, elasticidad real por producto, y validado contra historia real.
- Protege la rentabilidad automáticamente (piso de margen + filtro económico).
- Escala a Comercial solo lo que de verdad requiere criterio humano (14 productos).

Preguntas

**Habla:**
"No les estamos pidiendo que confíen en un modelo de caja negra — cada decisión es trazable a un dato real, y el modelo se corrige a sí mismo contra la realidad. Quedo abierto a preguntas."
