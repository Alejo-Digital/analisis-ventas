"""Dashboard interactivo de análisis de ventas y entregas con Streamlit y Plotly.

Se conecta directamente a data/ventas.db (tabla `ordenes`) mediante sqlite3.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

DB_PATH = Path("data/ventas.db")


def obtener_columna_canal(db_path: Path = DB_PATH) -> str:
    """Detecta si existe `canal_venta`; si no, usa `metodo_pago` como sustituto."""
    with sqlite3.connect(db_path) as conn:
        columnas = {row[1] for row in conn.execute("PRAGMA table_info(ordenes)")}
    return "canal_venta" if "canal_venta" in columnas else "metodo_pago"


@st.cache_data(ttl=300)
def cargar_metadata_filtros(db_path_str: str) -> dict[str, object]:
    """Obtiene fechas límite, canales y categorías disponibles desde SQLite."""
    db_path = Path(db_path_str)
    col_canal = obtener_columna_canal(db_path)
    with sqlite3.connect(db_path) as conn:
        min_fecha_str, max_fecha_str = conn.execute(
            "SELECT MIN(fecha_orden), MAX(fecha_orden) FROM ordenes"
        ).fetchone()
        canales = [
            row[0]
            for row in conn.execute(
                f"SELECT DISTINCT {col_canal} FROM ordenes ORDER BY {col_canal}"
            )
        ]
        categorias = [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT categoria FROM ordenes ORDER BY categoria"
            )
        ]

    return {
        "col_canal": col_canal,
        "min_fecha": date.fromisoformat(min_fecha_str),
        "max_fecha": date.fromisoformat(max_fecha_str),
        "canales": canales,
        "categorias": categorias,
    }


@st.cache_data(ttl=300)
def cargar_datos_filtrados(
    db_path_str: str,
    fecha_inicio: date,
    fecha_fin: date,
    col_canal: str,
    canales: tuple[str, ...],
    categorias: tuple[str, ...],
) -> pd.DataFrame:
    """Consulta las órdenes filtradas desde SQLite usando parámetros seguros."""
    if not canales or not categorias:
        return pd.DataFrame()

    placeholders_canal = ", ".join("?" for _ in canales)
    placeholders_cat = ", ".join("?" for _ in categorias)
    query = f"""
        SELECT
            orden_id,
            fecha_orden,
            cliente_id,
            ciudad,
            categoria,
            producto,
            cantidad,
            precio_unitario,
            descuento,
            costo_envio,
            ingreso_neto,
            margen_bruto,
            {col_canal} AS canal,
            metodo_pago,
            estado_orden,
            tiempo_entrega_min,
            repartidor_id,
            calificacion
        FROM ordenes
        WHERE fecha_orden BETWEEN ? AND ?
          AND {col_canal} IN ({placeholders_canal})
          AND categoria IN ({placeholders_cat})
    """
    params: list[object] = [
        fecha_inicio.isoformat(),
        fecha_fin.isoformat(),
        *canales,
        *categorias,
    ]
    with sqlite3.connect(db_path_str) as conn:
        df = pd.read_sql_query(query, conn, params=params)
    return df


def calcular_kpis(df: pd.DataFrame) -> dict[str, float | int]:
    """Calcula los KPIs ejecutivos sobre el subconjunto filtrado."""
    total_ordenes = len(df)
    if total_ordenes == 0:
        return {
            "total_ordenes": 0,
            "ordenes_canceladas": 0,
            "ingresos_totales": 0.0,
            "margen_bruto_total": 0.0,
            "margen_bruto_pct": 0.0,
            "ticket_promedio": 0.0,
            "tasa_cancelacion_pct": 0.0,
        }

    canceladas = int((df["estado_orden"] == "Cancelado").sum())
    tasa_cancelacion_pct = (canceladas / total_ordenes) * 100.0

    df_validas = df[~df["estado_orden"].isin(["Cancelado", "Devuelto"])]
    if df_validas.empty:
        return {
            "total_ordenes": total_ordenes,
            "ordenes_canceladas": canceladas,
            "ingresos_totales": 0.0,
            "margen_bruto_total": 0.0,
            "margen_bruto_pct": 0.0,
            "ticket_promedio": 0.0,
            "tasa_cancelacion_pct": tasa_cancelacion_pct,
        }

    ingresos_totales = float(df_validas["ingreso_neto"].sum())
    margen_bruto_total = float(df_validas["margen_bruto"].sum())
    margen_bruto_pct = (
        (margen_bruto_total / ingresos_totales) * 100.0 if ingresos_totales else 0.0
    )
    ticket_promedio = float(df_validas["ingreso_neto"].mean())

    return {
        "total_ordenes": total_ordenes,
        "ordenes_canceladas": canceladas,
        "ingresos_totales": ingresos_totales,
        "margen_bruto_total": margen_bruto_total,
        "margen_bruto_pct": margen_bruto_pct,
        "ticket_promedio": ticket_promedio,
        "tasa_cancelacion_pct": tasa_cancelacion_pct,
    }


def render_dashboard() -> None:
    """Construye la interfaz completa del dashboard en Streamlit."""
    st.set_page_config(
        page_title="Análisis de Ventas y Entregas",
        page_icon="📊",
        layout="wide",
    )

    st.title("Dashboard de Ventas y Entregas")
    st.caption(
        "Análisis comercial y operativo conectado a `data/ventas.db` "
        "(excluye órdenes canceladas y devueltas en ingresos, margen y AOV)."
    )

    if not DB_PATH.exists():
        st.error(
            "No se encontró `data/ventas.db`. Ejecuta primero `python3 src/etl.py`."
        )
        return

    meta = cargar_metadata_filtros(str(DB_PATH))
    col_canal = str(meta["col_canal"])
    min_fecha: date = meta["min_fecha"]  # type: ignore[assignment]
    max_fecha: date = meta["max_fecha"]  # type: ignore[assignment]
    canales_disp: list[str] = meta["canales"]  # type: ignore[assignment]
    categorias_disp: list[str] = meta["categorias"]  # type: ignore[assignment]

    # --- Barra lateral de filtros ---
    st.sidebar.header("Filtros")

    rango_fechas = st.sidebar.date_input(
        "Rango de fechas",
        value=(min_fecha, max_fecha),
        min_value=min_fecha,
        max_value=max_fecha,
    )
    if isinstance(rango_fechas, tuple) and len(rango_fechas) == 2:
        fecha_inicio, fecha_fin = rango_fechas
    elif isinstance(rango_fechas, tuple) and len(rango_fechas) == 1:
        fecha_inicio = fecha_fin = rango_fechas[0]
    else:
        fecha_inicio = fecha_fin = rango_fechas  # type: ignore[assignment]

    etiqueta_canal = (
        "Canal de venta"
        if col_canal == "canal_venta"
        else "Canal de venta (proxy: Método de pago)"
    )
    canales_sel = st.sidebar.multiselect(
        etiqueta_canal,
        options=canales_disp,
        default=canales_disp,
    )
    if col_canal != "canal_venta":
        st.sidebar.caption(
            "Nota: `ordenes` no incluye columna `canal_venta`; se filtra por `metodo_pago`."
        )

    categorias_sel = st.sidebar.multiselect(
        "Categoría",
        options=categorias_disp,
        default=categorias_disp,
    )

    df = cargar_datos_filtrados(
        str(DB_PATH),
        fecha_inicio,
        fecha_fin,
        col_canal,
        tuple(canales_sel),
        tuple(categorias_sel),
    )

    if df.empty:
        st.warning(
            "No hay registros para la combinación de filtros seleccionada. "
            "Ajusta los filtros en la barra lateral."
        )
        return

    # --- Tarjetas de KPI superiores ---
    kpis = calcular_kpis(df)
    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Ingresos Totales",
        f"${kpis['ingresos_totales']:,.2f}",
        help="Suma de ingreso_neto en órdenes no canceladas ni devueltas.",
    )
    col2.metric(
        "Margen Bruto (%)",
        f"{kpis['margen_bruto_pct']:.2f}%",
        delta=f"${kpis['margen_bruto_total']:,.2f} margen",
        delta_color="off",
    )
    col3.metric(
        "Ticket Promedio (AOV)",
        f"${kpis['ticket_promedio']:,.2f}",
    )
    col4.metric(
        "Tasa de Cancelación",
        f"{kpis['tasa_cancelacion_pct']:.2f}%",
        delta=f"{kpis['ordenes_canceladas']} / {kpis['total_ordenes']} órdenes",
        delta_color="off",
    )

    st.divider()

    # --- Gráficos principales ---
    df_validas = df[~df["estado_orden"].isin(["Cancelado", "Devuelto"])].copy()

    col_izq, col_der = st.columns(2)

    with col_izq:
        st.subheader("Tendencia Mensual de Ingresos")
        if df_validas.empty:
            st.info("Sin órdenes válidas para graficar tendencia mensual.")
        else:
            df_validas["mes"] = df_validas["fecha_orden"].str.slice(0, 7)
            mensual = (
                df_validas.groupby("mes", as_index=False)["ingreso_neto"]
                .sum()
                .sort_values("mes")
            )
            fig_linea = px.line(
                mensual,
                x="mes",
                y="ingreso_neto",
                markers=True,
                labels={"mes": "Mes", "ingreso_neto": "Ingresos Netos ($)"},
            )
            fig_linea.update_traces(
                line_color="#1f77b4",
                hovertemplate="Mes: %{x}<br>Ingresos: $%{y:,.2f}<extra></extra>",
            )
            fig_linea.update_layout(
                margin=dict(l=10, r=10, t=20, b=10),
                yaxis_tickprefix="$",
                yaxis_tickformat=",.0f",
            )
            st.plotly_chart(fig_linea, use_container_width=True)

    with col_der:
        st.subheader("Margen Bruto por Categoría")
        if df_validas.empty:
            st.info("Sin órdenes válidas para graficar margen por categoría.")
        else:
            por_cat = (
                df_validas.groupby("categoria", as_index=False)
                .agg(
                    margen_bruto=("margen_bruto", "sum"),
                    ingreso_neto=("ingreso_neto", "sum"),
                )
                .sort_values("margen_bruto", ascending=True)
            )
            por_cat["margen_pct"] = (
                por_cat["margen_bruto"] / por_cat["ingreso_neto"].replace(0, pd.NA)
            ) * 100.0
            fig_barras = px.bar(
                por_cat,
                x="margen_bruto",
                y="categoria",
                orientation="h",
                text=por_cat["margen_bruto"].map(lambda v: f"${v:,.0f}"),
                custom_data=["margen_pct"],
                labels={
                    "margen_bruto": "Margen Bruto Total ($)",
                    "categoria": "Categoría",
                },
                color="margen_bruto",
                color_continuous_scale="Teal",
            )
            fig_barras.update_traces(
                textposition="outside",
                hovertemplate=(
                    "Categoría: %{y}<br>"
                    "Margen Bruto: $%{x:,.2f}<br>"
                    "Margen %: %{customdata[0]:.2f}%<extra></extra>"
                ),
            )
            fig_barras.update_layout(
                margin=dict(l=10, r=40, t=20, b=10),
                coloraxis_showscale=False,
                xaxis_tickprefix="$",
                xaxis_tickformat=",.0f",
            )
            st.plotly_chart(fig_barras, use_container_width=True)

    st.divider()

    # --- Sección final: Hallazgos Clave ---
    st.header("Hallazgos Clave")
    st.markdown(
        """
1. **Proteger la rentabilidad en Supermercado y aprovechar el margen de Moda y Salud y Belleza:**
   En el catálogo completo (`4,835` órdenes limpias), **Moda** aporta el mayor margen bruto (`$544,529.88`, **37.68%**), mientras que **Electrónica** lidera en ingresos (`$2,156,820.87`) con un margen menor (**18.90%**). Por su parte, **Supermercado** presenta apenas **5.85%** de margen (`$18,899.17`) y concentra **242** de las 312 órdenes con margen negativo por tickets bajos combinados con descuentos (~15.1%) y costo de envío (~`$54`).
   *Recomendación:* Establecer un monto mínimo de compra para envío preferente y topar descuentos en **Supermercado**, e impulsar venta cruzada hacia **Moda** y **Salud y Belleza** (`33.23%` de margen).

2. **Reducir la tasa de cancelación en órdenes pagadas en Efectivo:**
   El método **Efectivo** registra la tasa de cancelación más alta (**18.34%**, `175` de `954` órdenes), frente a **Transferencia** (**14.23%**) y **Tarjetas Crédito/Débito** (**14.90%–14.98%**), aunque mantiene un ticket promedio competitivo (`$2,054.04`).
   *Recomendación:* Activar confirmación automática previa al despacho (WhatsApp/OTP) para pedidos en efectivo e incentivar la migración a **Tarjeta Crédito** (mayor AOV: `$2,110.84`) o **Transferencia**.

3. **Suavizar la estacionalidad en los valles de febrero y agosto:**
   La serie mensual muestra su pico de ingresos en **mayo 2026** (`$671,780.60`, `+21.63%` MoM), pero contracciones pronunciadas en **febrero 2026** (`$436,823.49`, `-19.13%` MoM) y **agosto 2026** (`$561,894.05`, `-12.77%` MoM), excluyendo los meses parciales de frontera (`2025-11` y `2026-11`).
   *Recomendación:* Desplegar campañas de retención y paquetes promocionales enfocados en categorías de alto margen (**Moda**, **Hogar**, **Salud y Belleza**) previo a febrero y agosto para estabilizar el ingreso sin sacrificar rentabilidad.
        """
    )


if __name__ == "__main__":
    render_dashboard()
