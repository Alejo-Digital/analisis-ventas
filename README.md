# Análisis de Ventas y Entregas (E-Commerce & Delivery)

Proyecto integral de análisis de datos que simula datos transaccionales con problemas reales de calidad, implementa un pipeline ETL reproducible hacia SQLite, calcula KPIs comerciales con SQL avanzado y expone un dashboard interactivo en Streamlit.

## Problema de negocio

Una plataforma de comercio electrónico y entregas a domicilio necesita visibilidad confiable sobre su desempeño comercial y operativo de los últimos 12 meses. Los datos crudos presentan incidencias frecuentes (duplicados exactos, valores faltantes, formatos de fecha mezclados, categorías inconsistentes y registros con precios o cantidades negativas) que distorsionan métricas clave como ingresos netos, margen bruto, ticket promedio (AOV) y tasa de cancelación.

Este proyecto resuelve el ciclo completo desde la ingesta y limpieza auditable hasta la visualización ejecutiva para responder:
- ¿Cómo evolucionan los ingresos mes a mes (MoM)?
- ¿Qué categorías generan mayor margen bruto real frente a su volumen de ventas?
- ¿Qué métodos de pago/canales concentran mayor tasa de cancelación y mejor AOV?

## Arquitectura del proyecto

```text
analisis-ventas-jr/
├── src/
│   ├── generar_datos.py          # Genera 5,000 órdenes sintéticas con anomalías controladas
│   └── etl.py                    # Pipeline de limpieza, imputación, cálculo de métricas y carga SQLite
├── data/
│   ├── raw/
│   │   └── ordenes_raw.csv       # Dataset crudo (5,000 filas)
│   ├── processed/
│   │   ├── ordenes_limpias.csv   # Dataset depurado (4,835 filas)
│   │   └── auditoria_errores.csv # Registro auditable de descartes (165 filas)
│   └── ventas.db                 # Base de datos SQLite (tabla `ordenes` + índices)
├── sql/
│   └── kpis_negocio.sql          # Consultas SQL con Window Functions (MoM), AOV/cancelación y Top 5
├── app.py                        # Dashboard interactivo (Streamlit + Plotly + sqlite3)
├── requirements.txt              # Dependencias del dashboard
└── README.md
```

### Flujo de datos y decisiones técnicas

1. **Generación (`src/generar_datos.py`):** Crea `5,000` registros de los últimos 12 meses (`2025-11-26` a `2026-11-25`) con semilla `42` e inyecta `3%` (`150`) de duplicados exactos, nulos en `descuento` y `tiempo_entrega_min`, fechas `YYYY-MM-DD` / `DD/MM/YYYY`, variantes sucias en `categoria` y `15` registros con precio o cantidad negativa.
2. **ETL (`src/etl.py`):**
   - Estandariza fechas a `YYYY-MM-DD`, limpia espacios en textos y normaliza categorías a 6 nombres canónicos.
   - Separa `150` duplicados exactos y `15` registros con `cantidad <= 0` o `precio_unitario <= 0` en `data/processed/auditoria_errores.csv` con su `motivo_descarte`.
   - Imputa `descuento` nulo con `0.0` (ausencia de promoción) y `tiempo_entrega_min` nulo con la **mediana por ciudad** (resistente a extremos). Mantiene `calificacion` nula en órdenes no entregadas.
   - Calcula `ingreso_neto` y `margen_bruto` (modelando el COGS estimado por categoría al no existir `costo_unitario` en el origen).
   - Carga los `4,835` registros limpios en `data/ventas.db` (`ordenes`).
3. **Analítica SQL (`sql/kpis_negocio.sql`):**
   - Ingresos mensuales y variación porcentual MoM con `LAG() OVER (ORDER BY mes)`.
   - Ticket promedio (AOV) y tasa de cancelación usando `metodo_pago` como dimensión sustituta documentada de `canal_venta` (columna ausente en el CSV crudo).
   - Top 5 categorías por margen bruto total.
4. **Dashboard (`app.py`):** Interfaz en Streamlit + Plotly conectada directamente a `data/ventas.db` con filtros laterales, 4 tarjetas KPI, tendencia mensual, margen horizontal por categoría y sección de hallazgos.

## Cómo ejecutarlo

1. **Instalar dependencias** (en entorno virtual recomendado):
   ```bash
   pip install -r requirements.txt
   ```

2. **Generar datos crudos** (opcional si ya existen en `data/raw/`):
   ```bash
   python3 src/generar_datos.py
   ```

3. **Ejecutar el pipeline ETL**:
   ```bash
   python3 src/etl.py
   ```

4. **Ejecutar las consultas SQL de KPIs** (opcional, requiere `sqlite3` CLI o Python):
   ```bash
   sqlite3 -header -column data/ventas.db < sql/kpis_negocio.sql
   ```

5. **Iniciar el dashboard interactivo**:
   ```bash
   streamlit run app.py
   ```

## Hallazgos principales

Con base en los **4,835** registros limpios en `data/ventas.db` (ingresos netos efectivos de **$6,944,248.01**, margen bruto global de **26.36%** / **$1,830,234.04**, AOV de **$2,025.15** y tasa de cancelación global de **15.49%**):

1. **Brecha entre volumen y rentabilidad por categoría:** **Electrónica** lidera los ingresos (`$2,156,820.87`) con un margen de `18.90%`, mientras **Moda** genera el mayor margen bruto total (`$544,529.88`, `37.68%`). En contraste, **Supermercado** apenas alcanza `5.85%` de margen (`$18,899.17`) y concentra `242` órdenes con margen bruto negativo por pedidos pequeños con descuentos (`~15.1%`) y costo de envío (`~$54`).
2. **Mayor cancelación en pagos con Efectivo:** **Efectivo** presenta una tasa de cancelación de **18.34%** (`175/954`), superior a **Transferencia** (**14.23%**) y tarjetas (**14.90%–14.98%**). **Tarjeta Crédito** logra el AOV más alto (`$2,110.84`).
3. **Estacionalidad con picos en mayo y caídas en febrero/agosto:** Excluyendo los meses parciales de frontera (`2025-11` y `2026-11`), mayo 2026 fue el mes pico (`$671,780.60`, `+21.63%` MoM), mientras febrero (`-19.13%` MoM) y agosto (`-12.77%` MoM) concentraron las mayores caídas.
