#!/usr/bin/env python3
"""Genera db/init.sql: esquema de la base de datos de TecnoStore y 500 productos de ejemplo.

Las marcas y los modelos son ficticios. La semilla aleatoria es fija, así que
cada ejecución produce exactamente el mismo archivo.
Uso: python3 db/generar_datos.py > db/init.sql
"""
import random

random.seed(2026)

CATEGORIAS = [
    # slug, nombre, icono, precio mínimo, precio máximo (COP), modelos
    ("portatiles", "Portátiles", "💻", 1_800_000, 9_500_000,
     ["Air 13", "Pro 14", "Pro 16", "Book 15", "Ultra 14", "Studio 16", "Go 11", "Flex 14"]),
    ("celulares", "Celulares", "📱", 450_000, 6_200_000,
     ["S", "Lite", "Max", "Plus", "Mini", "Pro", "Edge", "Neo"]),
    ("audio", "Audio", "🎧", 60_000, 1_600_000,
     ["Buds", "Wave", "Bass", "Studio", "Pods", "Beat", "Echo", "Sound"]),
    ("monitores", "Monitores", "🖥️", 450_000, 4_800_000,
     ["View 24", "View 27", "Curve 32", "Pro 27", "Gamer 25", "Wide 34", "Office 22", "Color 27"]),
    ("perifericos", "Periféricos", "⌨️", 35_000, 750_000,
     ["Teclado K", "Mouse M", "Combo C", "Teclado Mecánico", "Mouse Vertical", "Pad XL", "Webcam W", "Hub USB"]),
    ("gaming", "Gaming", "🎮", 120_000, 3_900_000,
     ["Control X", "Silla Pro", "Headset G", "Mouse Gamer", "Teclado RGB", "Volante R", "Consola Mini", "Stream Kit"]),
    ("almacenamiento", "Almacenamiento", "💾", 40_000, 1_300_000,
     ["SSD 512", "SSD 1TB", "SSD 2TB", "Disco 2TB", "Disco 4TB", "USB 64", "USB 128", "MicroSD 256"]),
    ("redes", "Redes", "📡", 70_000, 1_400_000,
     ["Router AX", "Router Mesh", "Switch 8", "Switch 16", "Repetidor R", "Antena W", "Adaptador USB", "Access Point"]),
]

MARCAS = ["Nexa", "Voltix", "Orbit", "Kairo", "Lumen", "Zentra", "Pixa", "Vortek"]
VARIANTES = ["", " 2025", " 2026", " SE", " Plus", " Pro", " X", " Air"]

DESCRIPCIONES = {
    "portatiles": "Portátil {marca} {modelo} con pantalla de alta resolución, batería para todo el día y diseño liviano para estudiar o trabajar.",
    "celulares": "Celular {marca} {modelo} con cámara de alta definición, carga rápida y pantalla de gran tamaño.",
    "audio": "Audio {marca} {modelo} con sonido envolvente, cancelación de ruido y conexión Bluetooth.",
    "monitores": "Monitor {marca} {modelo} con colores precisos, bordes delgados y bajo tiempo de respuesta.",
    "perifericos": "Accesorio {modelo} de {marca}, cómodo y resistente para largas jornadas frente al computador.",
    "gaming": "{modelo} de {marca} pensado para jugadores exigentes, con respuesta rápida e iluminación RGB.",
    "almacenamiento": "{modelo} de {marca} con altas velocidades de lectura y escritura para tus archivos.",
    "redes": "{modelo} de {marca} para una conexión estable y con buena cobertura en toda la casa u oficina.",
}


def sql(texto):
    return "'" + texto.replace("\\", "\\\\").replace("'", "''") + "'"


print("""-- Base de datos de TecnoStore (generada con db/generar_datos.py)
SET NAMES utf8mb4;
CREATE DATABASE IF NOT EXISTS techstore CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE techstore;

CREATE TABLE categorias (
    id      INT AUTO_INCREMENT PRIMARY KEY,
    slug    VARCHAR(40)  NOT NULL UNIQUE,
    nombre  VARCHAR(60)  NOT NULL,
    icono   VARCHAR(8)   NOT NULL
);

CREATE TABLE productos (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    categoria_id  INT           NOT NULL,
    nombre        VARCHAR(120)  NOT NULL,
    marca         VARCHAR(40)   NOT NULL,
    descripcion   VARCHAR(400)  NOT NULL,
    precio        DECIMAL(12,2) NOT NULL,
    stock         INT           NOT NULL,
    calificacion  DECIMAL(2,1)  NOT NULL,
    FOREIGN KEY (categoria_id) REFERENCES categorias(id),
    INDEX idx_categoria_calificacion (categoria_id, calificacion),
    INDEX idx_precio (precio)
);

-- Carrito guardado en la base de datos (modo CART_STORAGE=db)
CREATE TABLE carrito_items (
    carrito_id   CHAR(36) NOT NULL,
    producto_id  INT      NOT NULL,
    cantidad     INT      NOT NULL,
    actualizado  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (carrito_id, producto_id),
    FOREIGN KEY (producto_id) REFERENCES productos(id)
);

CREATE TABLE pedidos (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    carrito_id  CHAR(36)      NOT NULL,
    total       DECIMAL(14,2) NOT NULL,
    unidades    INT           NOT NULL,
    backend     VARCHAR(40)   NOT NULL,
    creado      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pedido_items (
    pedido_id        INT           NOT NULL,
    producto_id      INT           NOT NULL,
    cantidad         INT           NOT NULL,
    precio_unitario  DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (pedido_id, producto_id),
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id),
    FOREIGN KEY (producto_id) REFERENCES productos(id)
);
""")

print("INSERT INTO categorias (slug, nombre, icono) VALUES")
print(",\n".join(f"    ({sql(s)}, {sql(n)}, {sql(i)})" for s, n, i, *_ in CATEGORIAS) + ";\n")

filas = []
usados = set()
total = 500
for n in range(total):
    cat_index = n % len(CATEGORIAS)
    slug, _, _, pmin, pmax, modelos = CATEGORIAS[cat_index]
    while True:
        marca = random.choice(MARCAS)
        modelo = random.choice(modelos) + random.choice(VARIANTES)
        nombre = f"{marca} {modelo}"
        if nombre not in usados:
            usados.add(nombre)
            break
    precio = round(random.uniform(pmin, pmax) / 1000) * 1000 - 100   # precios terminados en 900
    calificacion = round(random.uniform(3.5, 5.0), 1)
    descripcion = DESCRIPCIONES[slug].format(marca=marca, modelo=modelo)
    filas.append(f"    ({cat_index + 1}, {sql(nombre)}, {sql(marca)}, {sql(descripcion)}, "
                 f"{precio:.2f}, 5000, {calificacion})")

print("INSERT INTO productos (categoria_id, nombre, marca, descripcion, precio, stock, calificacion) VALUES")
print(",\n".join(filas) + ";")
