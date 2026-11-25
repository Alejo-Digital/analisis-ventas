"""Generador de datos sintéticos con problemas intencionales de calidad.

Crea un archivo CSV con 5,000 registros de ventas de una plataforma de comercio
y entregas durante los últimos 12 meses para prácticas de limpieza y análisis.
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

BASE_RECORDS = 4_850
DUPLICATE_RECORDS = 150  # 150 / 5000 = 3.0% exacto
NEGATIVE_RECORDS = 15

FIELDNAMES = [
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
    "metodo_pago",
    "estado_orden",
    "tiempo_entrega_min",
    "repartidor_id",
    "calificacion",
]

CATALOGO: dict[str, dict[str, object]] = {
    "Electrónica": {
        "variantes_sucias": [
            " Electrónica",
            "electronica",
            "ELECTRÓNICA ",
            "  electrónica  ",
            "Electronica",
        ],
        "productos": [
            ("Audífonos Bluetooth", 450.0, 1800.0),
            ("Cargador Rápido USB-C", 220.0, 650.0),
            ("Mouse Inalámbrico", 280.0, 950.0),
            ("Teclado Mecánico", 850.0, 2400.0),
            ("Smartwatch Deportivo", 1100.0, 3800.0),
        ],
    },
    "Hogar": {
        "variantes_sucias": [" hogar", "HOGAR", "Hogar ", "  hogar ", "hOgAr"],
        "productos": [
            ("Cafetera de Goteo", 550.0, 1600.0),
            ("Juego de Sábanas", 420.0, 1200.0),
            ("Lámpara LED Escritorio", 290.0, 820.0),
            ("Licuadora 600W", 680.0, 1950.0),
            ("Set de Contenedores", 180.0, 520.0),
        ],
    },
    "Moda": {
        "variantes_sucias": [" moda", "MODA ", "moda", " Moda ", "MoDa"],
        "productos": [
            ("Playera Básica Algodón", 190.0, 480.0),
            ("Tenis Urbanos", 790.0, 2300.0),
            ("Sudadera con Capucha", 480.0, 1250.0),
            ("Mochila Impermeable", 450.0, 1350.0),
            ("Gorra Deportiva", 160.0, 420.0),
        ],
    },
    "Supermercado": {
        "variantes_sucias": [
            " supermercado",
            "SUPERMERCADO",
            "Supermercado ",
            "  supermercado ",
        ],
        "productos": [
            ("Café Molido 500g", 110.0, 240.0),
            ("Aceite de Oliva 750ml", 160.0, 340.0),
            ("Pack Agua Mineral 12u", 95.0, 190.0),
            ("Cereal Integral 600g", 65.0, 135.0),
            ("Detergente Líquido 3L", 130.0, 270.0),
        ],
    },
    "Salud y Belleza": {
        "variantes_sucias": [
            " salud y belleza",
            "Salud y belleza ",
            "SALUD Y BELLEZA",
            "salud y belleza",
        ],
        "productos": [
            ("Protector Solar FPS 50", 240.0, 520.0),
            ("Crema Hidratante Facial", 210.0, 620.0),
            ("Shampoo Reparador 400ml", 120.0, 290.0),
            ("Vitaminas Complejo B", 180.0, 450.0),
            ("Cepillo Eléctrico", 490.0, 1400.0),
        ],
    },
    "Deportes": {
        "variantes_sucias": [" deportes", "DEPORTES ", "deportes", " Deportes "],
        "productos": [
            ("Tapete de Yoga", 260.0, 720.0),
            ("Botella Térmica 1L", 220.0, 580.0),
            ("Bandas de Resistencia", 190.0, 490.0),
            ("Balón de Fútbol", 320.0, 890.0),
            ("Cuerda para Saltar", 140.0, 360.0),
        ],
    },
}

CIUDADES = [
    "Ciudad de México",
    "Guadalajara",
    "Monterrey",
    "Puebla",
    "Querétaro",
    "Tijuana",
    "Mérida",
    "León",
]

METODOS_PAGO = [
    "Tarjeta Crédito",
    "Tarjeta Débito",
    "Efectivo",
    "Transferencia",
    "Billetera Digital",
]

ESTADOS_ORDEN = ["Entregado", "Entregado", "Entregado", "Entregado", "En camino", "Cancelado", "Devuelto"]


def _formatear_fecha(fecha: date, rng: random.Random) -> str:
    """Devuelve la fecha en formato YYYY-MM-DD o DD/MM/YYYY mezclados."""
    if rng.random() < 0.25:
        return fecha.strftime("%d/%m/%Y")
    return fecha.strftime("%Y-%m-%d")


def _elegir_categoria(categoria_canonica: str, rng: random.Random) -> str:
    """Introduce espacios extra y mayúsculas inconsistentes en ~30% de los casos."""
    if rng.random() < 0.30:
        variantes = CATALOGO[categoria_canonica]["variantes_sucias"]
        return rng.choice(variantes)  # type: ignore[arg-type]
    return categoria_canonica


def generar_ordenes(seed: int = 42, fecha_fin: date | None = None) -> list[dict[str, object]]:
    """Genera 5,000 registros de órdenes con problemas intencionales de calidad."""
    rng = random.Random(seed)
    hoy = fecha_fin or date.today()
    fecha_inicio = hoy - timedelta(days=364)
    categorias = list(CATALOGO.keys())

    # Seleccionar exactamente 15 índices base que tendrán precio o cantidad negativa
    # y reservar el resto como candidatos válidos para duplicación exacta.
    indices_negativos = set(rng.sample(range(BASE_RECORDS), NEGATIVE_RECORDS))
    candidatos_duplicado = [i for i in range(BASE_RECORDS) if i not in indices_negativos]
    indices_a_duplicar = rng.sample(candidatos_duplicado, DUPLICATE_RECORDS)

    registros_base: list[dict[str, object]] = []

    for idx in range(BASE_RECORDS):
        categoria_canonica = rng.choice(categorias)
        productos = CATALOGO[categoria_canonica]["productos"]
        producto, min_precio, max_precio = rng.choice(productos)  # type: ignore[misc]

        dias_offset = rng.randint(0, 364)
        fecha_orden = _formatear_fecha(fecha_inicio + timedelta(days=dias_offset), rng)

        cantidad = rng.randint(1, 6)
        precio_unitario = round(rng.uniform(min_precio, max_precio), 2)

        if idx in indices_negativos:
            # Alternar entre cantidad negativa, precio negativo o ambos
            modo = idx % 3
            if modo == 0:
                cantidad = -cantidad
            elif modo == 1:
                precio_unitario = -precio_unitario
            else:
                cantidad = -cantidad
                precio_unitario = -precio_unitario

        # ~10% de valores nulos en descuento
        if rng.random() < 0.10:
            descuento: object = ""
        else:
            descuento = rng.choice([0.0, 0.0, 0.05, 0.10, 0.15, 0.20, 0.25])

        estado = rng.choice(ESTADOS_ORDEN)

        # ~8% de valores nulos en tiempo_entrega_min (más frecuente en cancelados)
        if rng.random() < 0.08 or (estado == "Cancelado" and rng.random() < 0.50):
            tiempo_entrega: object = ""
        else:
            tiempo_entrega = rng.randint(18, 115)

        calificacion: object = rng.randint(1, 5) if estado == "Entregado" else ""

        registros_base.append(
            {
                "orden_id": f"ORD-{idx + 1:06d}",
                "fecha_orden": fecha_orden,
                "cliente_id": f"CLI-{rng.randint(1, 1500):04d}",
                "ciudad": rng.choice(CIUDADES),
                "categoria": _elegir_categoria(categoria_canonica, rng),
                "producto": producto,
                "cantidad": cantidad,
                "precio_unitario": f"{precio_unitario:.2f}",
                "descuento": descuento,
                "costo_envio": f"{rng.choice([0.0, 29.0, 45.0, 59.0, 79.0]):.2f}",
                "metodo_pago": rng.choice(METODOS_PAGO),
                "estado_orden": estado,
                "tiempo_entrega_min": tiempo_entrega,
                "repartidor_id": f"REP-{rng.randint(1, 180):03d}",
                "calificacion": calificacion,
            }
        )

    duplicados = [dict(registros_base[i]) for i in indices_a_duplicar]
    todos = registros_base + duplicados
    rng.shuffle(todos)
    return todos


def guardar_csv(registros: list[dict[str, object]], ruta_salida: Path) -> None:
    """Escribe los registros en el archivo CSV creando directorios si faltan."""
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    with ruta_salida.open("w", newline="", encoding="utf-8") as archivo:
        writer = csv.DictWriter(archivo, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(registros)


def imprimir_resumen(registros: list[dict[str, object]], ruta_salida: Path) -> None:
    """Imprime un resumen de verificación sobre los datos generados."""
    vistos: set[tuple[tuple[str, object], ...]] = set()
    duplicados = 0
    nulos_descuento = 0
    nulos_tiempo = 0
    fechas_iso = 0
    fechas_latam = 0
    categorias_sucias = 0
    negativos = 0

    for fila in registros:
        clave = tuple(fila.items())
        if clave in vistos:
            duplicados += 1
        else:
            vistos.add(clave)

        if fila["descuento"] == "":
            nulos_descuento += 1
        if fila["tiempo_entrega_min"] == "":
            nulos_tiempo += 1

        fecha = str(fila["fecha_orden"])
        if "/" in fecha:
            fechas_latam += 1
        else:
            fechas_iso += 1

        cat = str(fila["categoria"])
        if cat not in CATALOGO:
            categorias_sucias += 1

        if int(fila["cantidad"]) < 0 or float(fila["precio_unitario"]) < 0:
            negativos += 1

    total = len(registros)
    print(f"Archivo generado: {ruta_salida}")
    print(f"Total de registros: {total}")
    print(f"Filas duplicadas exactas: {duplicados} ({duplicados / total:.2%})")
    print(f"Nulos en 'descuento': {nulos_descuento} ({nulos_descuento / total:.2%})")
    print(f"Nulos en 'tiempo_entrega_min': {nulos_tiempo} ({nulos_tiempo / total:.2%})")
    print(f"Fechas YYYY-MM-DD: {fechas_iso} | Fechas DD/MM/YYYY: {fechas_latam}")
    print(f"Categorías con formato inconsistente: {categorias_sucias} ({categorias_sucias / total:.2%})")
    print(f"Registros con precio o cantidad negativa: {negativos}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera datos sintéticos de ventas en CSV.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/ordenes_raw.csv"),
        help="Ruta del archivo CSV de salida.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Semilla aleatoria.")
    args = parser.parse_args()

    registros = generar_ordenes(seed=args.seed)
    guardar_csv(registros, args.output)
    imprimir_resumen(registros, args.output)


if __name__ == "__main__":
    main()
