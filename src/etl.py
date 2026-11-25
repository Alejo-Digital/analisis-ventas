"""Pipeline ETL para limpieza de órdenes de venta y carga en SQLite.

Lee data/raw/ordenes_raw.csv, estandariza fechas/textos/categorías, separa
duplicados y registros inválidos en data/processed/auditoria_errores.csv,
imputa nulos de forma justificada, calcula ingreso_neto y margen_bruto, y
persiste los resultados en data/processed/ordenes_limpias.csv y data/ventas.db.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import statistics
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

RAW_PATH_DEFAULT = Path("data/raw/ordenes_raw.csv")
CLEAN_PATH_DEFAULT = Path("data/processed/ordenes_limpias.csv")
AUDIT_PATH_DEFAULT = Path("data/processed/auditoria_errores.csv")
DB_PATH_DEFAULT = Path("data/ventas.db")

CATEGORIAS_CANONICAS: dict[str, str] = {
    "electronica": "Electrónica",
    "hogar": "Hogar",
    "moda": "Moda",
    "supermercado": "Supermercado",
    "salud y belleza": "Salud y Belleza",
    "deportes": "Deportes",
}

# El dataset crudo no incluye costo_unitario; se modela el COGS estimado como
# proporción del ingreso bruto por categoría (estándar retail/e-commerce).
COGS_RATIO_POR_CATEGORIA: dict[str, float] = {
    "Electrónica": 0.72,
    "Hogar": 0.65,
    "Moda": 0.55,
    "Supermercado": 0.78,
    "Salud y Belleza": 0.58,
    "Deportes": 0.62,
}
COGS_RATIO_DEFAULT = 0.65

CLEAN_FIELDNAMES = [
    "orden_id",
    "fecha_orden",
    "cliente_id",
    "ciudad",
    "categoria",
    "producto",
    "cantidad",
    "precio_unitario",
    "descuento",
    "costo_envio",
    "ingreso_neto",
    "margen_bruto",
    "metodo_pago",
    "estado_orden",
    "tiempo_entrega_min",
    "repartidor_id",
    "calificacion",
]


def _limpiar_texto(valor: str) -> str:
    """Elimina espacios iniciales/finales y colapsa espacios internos múltiples."""
    return " ".join(valor.strip().split())


def _quitar_acentos(texto: str) -> str:
    """Normaliza caracteres acentuados para comparación robusta de categorías."""
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(ch for ch in normalizado if not unicodedata.combining(ch))


def estandarizar_categoria(valor: str) -> str:
    """Convierte variantes sucias de categoría a su nombre canónico."""
    limpio = _limpiar_texto(valor).lower()
    clave = _quitar_acentos(limpio)
    if clave in CATEGORIAS_CANONICAS:
        return CATEGORIAS_CANONICAS[clave]
    return _limpiar_texto(valor).title()


def estandarizar_fecha(valor: str) -> str | None:
    """Parsea fechas en formato YYYY-MM-DD o DD/MM/YYYY y devuelve YYYY-MM-DD."""
    texto = _limpiar_texto(valor)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _motivo_invalidez(cantidad: int, precio_unitario: float, fecha_iso: str | None) -> str | None:
    """Devuelve el motivo de descarte si el registro viola reglas de validez."""
    motivos: list[str] = []
    if fecha_iso is None:
        motivos.append("fecha_invalida")
    if cantidad <= 0:
        motivos.append("cantidad_no_positiva")
    if precio_unitario <= 0:
        motivos.append("precio_unitario_no_positivo")
    return "|".join(motivos) if motivos else None


def ejecutar_etl(
    raw_path: Path = RAW_PATH_DEFAULT,
    clean_path: Path = CLEAN_PATH_DEFAULT,
    audit_path: Path = AUDIT_PATH_DEFAULT,
    db_path: Path = DB_PATH_DEFAULT,
) -> dict[str, int]:
    """Ejecuta el pipeline completo de extracción, limpieza, auditoría y carga."""
    with raw_path.open("r", newline="", encoding="utf-8") as archivo:
        reader = csv.DictReader(archivo)
        raw_fieldnames = list(reader.fieldnames or [])
        raw_rows = list(reader)

    vistos_exactos: set[tuple[tuple[str, str], ...]] = set()
    auditoria: list[dict[str, str]] = []
    pre_limpios: list[dict[str, object]] = []
    tiempos_por_ciudad: dict[str, list[int]] = defaultdict(list)
    todos_los_tiempos: list[int] = []

    duplicados_eliminados = 0
    invalidos_eliminados = 0

    for row in raw_rows:
        firma = tuple(row.items())
        if firma in vistos_exactos:
            duplicados_eliminados += 1
            fila_audit = dict(row)
            fila_audit["motivo_descarte"] = "fila_duplicada"
            auditoria.append(fila_audit)
            continue
        vistos_exactos.add(firma)

        fecha_iso = estandarizar_fecha(row["fecha_orden"])
        try:
            cantidad = int(_limpiar_texto(row["cantidad"]))
            precio_unitario = float(_limpiar_texto(row["precio_unitario"]))
        except ValueError:
            invalidos_eliminados += 1
            fila_audit = dict(row)
            fila_audit["motivo_descarte"] = "tipo_numerico_invalido"
            auditoria.append(fila_audit)
            continue

        motivo = _motivo_invalidez(cantidad, precio_unitario, fecha_iso)
        if motivo is not None:
            invalidos_eliminados += 1
            fila_audit = dict(row)
            fila_audit["motivo_descarte"] = motivo
            auditoria.append(fila_audit)
            continue

        ciudad = _limpiar_texto(row["ciudad"])
        categoria = estandarizar_categoria(row["categoria"])
        tiempo_raw = _limpiar_texto(row["tiempo_entrega_min"])
        tiempo_val: int | None = int(tiempo_raw) if tiempo_raw != "" else None
        if tiempo_val is not None:
            tiempos_por_ciudad[ciudad].append(tiempo_val)
            todos_los_tiempos.append(tiempo_val)

        descuento_raw = _limpiar_texto(row["descuento"])
        # Justificación descuento nulo: ausencia de cupón/promoción equivale a 0.0.
        descuento_imputado = descuento_raw == ""
        descuento = float(descuento_raw) if not descuento_imputado else 0.0
        costo_envio = float(_limpiar_texto(row["costo_envio"]))

        calif_raw = _limpiar_texto(row["calificacion"])
        calificacion: int | None = int(calif_raw) if calif_raw != "" else None

        pre_limpios.append(
            {
                "orden_id": _limpiar_texto(row["orden_id"]),
                "fecha_orden": fecha_iso,
                "cliente_id": _limpiar_texto(row["cliente_id"]),
                "ciudad": ciudad,
                "categoria": categoria,
                "producto": _limpiar_texto(row["producto"]),
                "cantidad": cantidad,
                "precio_unitario": round(precio_unitario, 2),
                "descuento": round(descuento, 4),
                "_descuento_imputado": descuento_imputado,
                "costo_envio": round(costo_envio, 2),
                "metodo_pago": _limpiar_texto(row["metodo_pago"]),
                "estado_orden": _limpiar_texto(row["estado_orden"]),
                "tiempo_entrega_min": tiempo_val,
                "repartidor_id": _limpiar_texto(row["repartidor_id"]),
                "calificacion": calificacion,
            }
        )

    mediana_global = round(statistics.median(todos_los_tiempos)) if todos_los_tiempos else 0
    mediana_ciudad = {
        ciudad: round(statistics.median(vals))
        for ciudad, vals in tiempos_por_ciudad.items()
    }

    descuentos_imputados = 0
    tiempos_imputados = 0

    registros_limpios: list[dict[str, object]] = []
    for item in pre_limpios:
        if item.pop("_descuento_imputado"):
            descuentos_imputados += 1
        if item["tiempo_entrega_min"] is None:
            # Justificación tiempo_entrega_min nulo: imputación por mediana de la ciudad
            # para evitar sesgo por valores extremos y respetar tiempos logísticos locales.
            ciudad = str(item["ciudad"])
            item["tiempo_entrega_min"] = mediana_ciudad.get(ciudad, mediana_global)
            tiempos_imputados += 1

        cantidad = int(item["cantidad"])  # type: ignore[arg-type]
        precio_unitario = float(item["precio_unitario"])  # type: ignore[arg-type]
        descuento = float(item["descuento"])  # type: ignore[arg-type]
        costo_envio = float(item["costo_envio"])  # type: ignore[arg-type]
        categoria = str(item["categoria"])

        ingreso_bruto = cantidad * precio_unitario
        ingreso_neto = round(ingreso_bruto * (1.0 - descuento), 2)
        cogs_ratio = COGS_RATIO_POR_CATEGORIA.get(categoria, COGS_RATIO_DEFAULT)
        costo_producto_est = ingreso_bruto * cogs_ratio
        margen_bruto = round(ingreso_neto - costo_producto_est - costo_envio, 2)

        item["ingreso_neto"] = ingreso_neto
        item["margen_bruto"] = margen_bruto
        registros_limpios.append(item)

    registros_limpios.sort(key=lambda r: (str(r["fecha_orden"]), str(r["orden_id"])))

    _escribir_csv(clean_path, CLEAN_FIELDNAMES, registros_limpios)
    _escribir_csv(audit_path, raw_fieldnames + ["motivo_descarte"], auditoria)
    _cargar_sqlite(db_path, registros_limpios)

    return {
        "leidos": len(raw_rows),
        "duplicados_eliminados": duplicados_eliminados,
        "invalidos_eliminados": invalidos_eliminados,
        "auditoria_total": len(auditoria),
        "limpios_total": len(registros_limpios),
        "descuentos_imputados": descuentos_imputados,
        "tiempos_imputados": tiempos_imputados,
    }


def _escribir_csv(
    ruta: Path, fieldnames: list[str], rows: list[dict[str, object]] | list[dict[str, str]]
) -> None:
    """Guarda filas en CSV asegurando que el directorio destino exista."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", newline="", encoding="utf-8") as archivo:
        writer = csv.DictWriter(archivo, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            serializable = {k: ("" if v is None else v) for k, v in row.items()}
            writer.writerow(serializable)


def _cargar_sqlite(db_path: Path, registros: list[dict[str, object]]) -> None:
    """Crea o reemplaza la tabla `ordenes` en SQLite con índices analíticos."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE IF EXISTS ordenes")
        conn.execute(
            """
            CREATE TABLE ordenes (
                orden_id TEXT PRIMARY KEY,
                fecha_orden TEXT NOT NULL,
                cliente_id TEXT NOT NULL,
                ciudad TEXT NOT NULL,
                categoria TEXT NOT NULL,
                producto TEXT NOT NULL,
                cantidad INTEGER NOT NULL CHECK (cantidad > 0),
                precio_unitario REAL NOT NULL CHECK (precio_unitario > 0),
                descuento REAL NOT NULL CHECK (descuento >= 0 AND descuento <= 1),
                costo_envio REAL NOT NULL CHECK (costo_envio >= 0),
                ingreso_neto REAL NOT NULL,
                margen_bruto REAL NOT NULL,
                metodo_pago TEXT NOT NULL,
                estado_orden TEXT NOT NULL,
                tiempo_entrega_min INTEGER NOT NULL,
                repartidor_id TEXT NOT NULL,
                calificacion INTEGER
            )
            """
        )
        columnas_sql = ", ".join(CLEAN_FIELDNAMES)
        placeholders = ", ".join(f":{col}" for col in CLEAN_FIELDNAMES)
        conn.executemany(
            f"INSERT INTO ordenes ({columnas_sql}) VALUES ({placeholders})",
            registros,
        )
        conn.execute("CREATE INDEX idx_ordenes_fecha ON ordenes(fecha_orden)")
        conn.execute("CREATE INDEX idx_ordenes_categoria ON ordenes(categoria)")
        conn.execute("CREATE INDEX idx_ordenes_estado ON ordenes(estado_orden)")
        conn.execute("CREATE INDEX idx_ordenes_metodo_pago ON ordenes(metodo_pago)")
        conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline ETL de órdenes de venta.")
    parser.add_argument("--raw", type=Path, default=RAW_PATH_DEFAULT)
    parser.add_argument("--clean", type=Path, default=CLEAN_PATH_DEFAULT)
    parser.add_argument("--audit", type=Path, default=AUDIT_PATH_DEFAULT)
    parser.add_argument("--db", type=Path, default=DB_PATH_DEFAULT)
    args = parser.parse_args()

    resumen = ejecutar_etl(
        raw_path=args.raw,
        clean_path=args.clean,
        audit_path=args.audit,
        db_path=args.db,
    )
    print("ETL completado:")
    for clave, valor in resumen.items():
        print(f"  - {clave}: {valor}")


if __name__ == "__main__":
    main()
