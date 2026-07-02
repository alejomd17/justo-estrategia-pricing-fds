# Estrategia de Precios Fin de Semana (FDS)

## ¿Qué es esto?

Un análisis para armar la oferta de precios del próximo fin de semana (viernes 3 a domingo 5 de julio de 2026) en las tiendas Atizapán (#9) y Coyoacán (#14). El objetivo: elegir qué productos ofertar, con qué tipo de promoción y en qué día, de forma que la oferta sea atractiva para el cliente **sin que la tienda pierda rentabilidad**.

El resultado final es un archivo Excel (`data/output/estrategia_fds.xlsx`) con la lista de productos recomendados, la promoción sugerida para cada uno, y una proyección de cuánto se espera vender.

## De dónde salen los datos

| Fuente | Qué aporta |
|---|---|
| `oportunidad.xlsx` | El universo de productos candidatos: ya viene filtrado para excluir marca propia y productos con promoción activa hoy. |
| `Descuentos comerciales.xlsx` | Lista negra de productos que nunca se deben ofertar, y el calendario de promociones ya comprometidas por el equipo comercial. |
| Catálogo de Snowflake | Departamento y categoría real de cada producto |
| Histórico de ventas y elasticidad (Snowflake) | Qué tan sensible es cada producto a cambios de precio, y cuánto se vende normalmente, para poder proyectar el efecto de la oferta. |
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

### 4. Elegir la promoción de cada producto

Para cada producto que sobrevive los filtros anteriores, se calcula matemáticamente **el descuento más grande posible que ese producto puede aguantar sin romper el piso del 22% de margen.** Ese es el techo — nunca se ofrece menos descuento del que el margen permite.

Con ese techo, se decide cómo comunicarlo al cliente:

- Si el producto tiene margen suficiente para mecánicas tipo **"paga 1 y llévate 2" (2x1), "paga 2 y llévate 3" (3x2)**, o variantes similares, se usa esa mecánica — son más atractivas y fáciles de entender para el cliente que un simple "% de descuento".
- Si no alcanza para ninguna de esas mecánicas, se ofrece el **descuento exacto** que sí es viable, presentado de la forma que más impacta al cliente: en **porcentaje** para productos baratos (menos de $100), o en **pesos** para productos caros (a partir de $100) — es un principio conocido de pricing: un "20% de descuento" en algo barato suena más grande que "$2 de descuento", pero en algo caro pasa lo contrario ("$50 de descuento" suena mejor que "16% off").

### 5. Detección de productos relacionados con el Mundial

Estamos en fechas de Mundial de fútbol (a jugarse parcialmente en México), así que se marcaron los productos típicos de "ver el partido en casa": cervezas, refrescos, botanas saladas, salsas picantes. No hay mercancía oficial con licencia FIFA en el catálogo, así que esto es una marca de referencia para que el equipo comercial decida si destacar estos productos con exhibición o banner especial — no cambia el orden ni el día de la oferta.

### 6. Día sugerido

Cada producto se asigna a Viernes, Sábado o Domingo con una lógica simple:

- **Domingo**: productos de Despensa (categoría de reabastecimiento antes de empezar la semana).
- **Viernes**: productos de alta rotación (los que ya se venden mucho, para capturar tráfico desde el inicio del fin de semana).
- **Sábado**: el resto — es el día "bandera" del fin de semana, donde cae la mayoría de la oferta.

### 7. ¿Cuánto se espera vender? (validación de demanda)

Elegir un descuento que no rompa el margen es solo la mitad del trabajo — la otra mitad es saber si esa oferta realmente va a mover ventas. Para eso se cruzó cada producto con:

- Su **sensibilidad histórica al precio** (elasticidad): un número que indica cuánto sube la demanda cuando baja el precio.
- Sus **ventas promedio actuales**, como punto de partida.

Con eso se proyecta cuántas unidades por día se esperan vender con la oferta puesta, y cuánto más representa eso frente a la venta normal (el "uplift" proyectado).

**Nivel de confianza de cada proyección.** No todas las proyecciones son igual de confiables, así que cada producto queda etiquetado:

- **Alta**: el producto tiene su propio dato de sensibilidad al precio, y además ya tuvo una promoción real en el pasado con la que se puede comparar.
- **Media**: tiene su propio dato de sensibilidad al precio, pero nunca se le ha probado una promoción real.
- **Baja**: no hay dato propio de sensibilidad al precio; se usó un promedio de su categoría como aproximación.

**Prueba contra la realidad (backtesting).** Para los productos que sí tuvieron promociones en el pasado, se comparó lo que la proyección hubiera dicho contra lo que realmente pasó en ventas. Esto permite decir, en una frase, si el modelo de sensibilidad al precio tiende a **quedarse corto o pasarse** al proyectar el efecto de una oferta — información clave para tomar la proyección de demanda con el grado de escepticismo correcto, no como una cifra exacta.

## Qué NO hace este análisis (para ser transparentes)

- No garantiza que el producto se va a vender exactamente lo proyectado — es una estimación estadística, con niveles de confianza distintos por producto.
- No considera quiebres de inventario ni capacidad logística — solo pricing.
- La detección de "Mundial" es una aproximación por nombre de producto, no un dato oficial de licencia.
- El día sugerido usa una regla simple (categoría + rotación); no considera calendario de partidos, clima, ni otros factores externos al pricing.

## Cómo leer el archivo final

`data/output/estrategia_fds.xlsx` trae una fila por producto y tienda, con: departamento/categoría, margen actual, mecánica de oferta recomendada, margen resultante, precio de oferta, cuánto se espera vender, qué tan confiable es esa proyección, día sugerido, y si es un producto afín al Mundial.

---

*(Pendiente: agregar aquí el resumen de resultados de la corrida más reciente — total de productos incluidos, distribución por mecánica, por día, y conclusión del backtesting — en cuanto se comparta el output del notebook.)*
