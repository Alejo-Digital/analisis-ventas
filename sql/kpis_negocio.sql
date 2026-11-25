-- ============================================================================
-- KPIs de Negocio — Base de datos: data/ventas.db (Tabla: ordenes)
-- Motor: SQLite 3
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Ingresos mensuales y variación porcentual mes a mes (MoM)
--    - Se excluyen órdenes 'Cancelado' y 'Devuelto' para reflejar ingresos
--      efectivos (realizados o en curso de entrega).
--    - Se usa la Window Function LAG() sobre la serie ordenada por mes.
-- ----------------------------------------------------------------------------
WITH ingresos_por_mes AS (
    SELECT
        strftime('%Y-%m', fecha_orden) AS mes,
        COUNT(*) AS total_ordenes,
        ROUND(SUM(ingreso_neto), 2) AS ingreso_neto_mensual
    FROM ordenes
    WHERE estado_orden NOT IN ('Cancelado', 'Devuelto')
    GROUP BY strftime('%Y-%m', fecha_orden)
)
SELECT
    mes,
    total_ordenes,
    ingreso_neto_mensual,
    LAG(ingreso_neto_mensual) OVER (ORDER BY mes) AS ingreso_mes_anterior,
    ROUND(
        ingreso_neto_mensual - LAG(ingreso_neto_mensual) OVER (ORDER BY mes),
        2
    ) AS variacion_absoluta_mom,
    ROUND(
        (ingreso_neto_mensual - LAG(ingreso_neto_mensual) OVER (ORDER BY mes)) * 100.0
        / NULLIF(LAG(ingreso_neto_mensual) OVER (ORDER BY mes), 0),
        2
    ) AS variacion_pct_mom
FROM ingresos_por_mes
ORDER BY mes;


-- ----------------------------------------------------------------------------
-- 2. Ticket promedio (AOV) y tasa de cancelación por canal de venta
--    NOTA DE ESQUEMA: El archivo fuente data/raw/ordenes_raw.csv no contiene
--    la columna `canal_venta` (p. ej. App, Web, Marketplace). Para que esta
--    consulta sea ejecutable sobre el esquema real de `ordenes`, se usa
--    `metodo_pago` como segmento sustituto. Si se agrega `canal_venta` al
--    origen, basta reemplazar `metodo_pago` por `canal_venta`.
--    - Tasa de cancelación: porcentaje de órdenes en estado 'Cancelado' sobre
--      el total de órdenes del segmento.
--    - AOV: promedio de `ingreso_neto` excluyendo órdenes canceladas y
--      devueltas.
-- ----------------------------------------------------------------------------
SELECT
    metodo_pago AS canal_venta_sustituto,
    COUNT(*) AS total_ordenes,
    SUM(CASE WHEN estado_orden = 'Cancelado' THEN 1 ELSE 0 END) AS ordenes_canceladas,
    ROUND(
        SUM(CASE WHEN estado_orden = 'Cancelado' THEN 1.0 ELSE 0.0 END) * 100.0
        / COUNT(*),
        2
    ) AS tasa_cancelacion_pct,
    ROUND(
        AVG(
            CASE
                WHEN estado_orden NOT IN ('Cancelado', 'Devuelto')
                THEN ingreso_neto
            END
        ),
        2
    ) AS ticket_promedio_aov
FROM ordenes
GROUP BY metodo_pago
ORDER BY ticket_promedio_aov DESC;


-- ----------------------------------------------------------------------------
-- 3. Top 5 categorías por margen bruto total
--    - Se excluyen órdenes 'Cancelado' y 'Devuelto'.
--    - `margen_bruto` proviene del pipeline ETL (ingreso_neto - COGS estimado
--      por categoría - costo_envio).
-- ----------------------------------------------------------------------------
SELECT
    categoria,
    COUNT(*) AS total_ordenes,
    SUM(cantidad) AS unidades_vendidas,
    ROUND(SUM(ingreso_neto), 2) AS ingreso_neto_total,
    ROUND(SUM(margen_bruto), 2) AS margen_bruto_total,
    ROUND(
        SUM(margen_bruto) * 100.0 / NULLIF(SUM(ingreso_neto), 0),
        2
    ) AS margen_bruto_pct
FROM ordenes
WHERE estado_orden NOT IN ('Cancelado', 'Devuelto')
GROUP BY categoria
ORDER BY margen_bruto_total DESC
LIMIT 5;
