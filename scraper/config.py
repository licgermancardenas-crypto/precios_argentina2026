"""
URLs de categorías y definición de la Canasta Atlas (26 productos, 6 categorías).
El EAN se congela en el primer scraping y no se modifica manualmente.
"""

# Categorías a scrapear en Coto Digital
CATEGORIAS_COTO: list[dict] = [
    {"nombre": "lacteos",     "url": "https://www.cotodigital3.com.ar/sitios/cdigi/browse/lacteos-y-huevos/_/N-1500000156"},
    {"nombre": "almacen",     "url": "https://www.cotodigital3.com.ar/sitios/cdigi/browse/almacen/_/N-1500000109"},
    {"nombre": "panificados", "url": "https://www.cotodigital3.com.ar/sitios/cdigi/browse/panaderia-y-reposteria/_/N-1500000130"},
    {"nombre": "carnes",      "url": "https://www.cotodigital3.com.ar/sitios/cdigi/browse/carnes/_/N-1500000118"},
    {"nombre": "bebidas",     "url": "https://www.cotodigital3.com.ar/sitios/cdigi/browse/bebidas/_/N-1500000113"},
    {"nombre": "limpieza",    "url": "https://www.cotodigital3.com.ar/sitios/cdigi/browse/limpieza-del-hogar/_/N-1500000126"},
]

# Canasta Atlas — 26 productos de referencia
# El EAN se completa en el primer scraping (campo "ean" queda None hasta entonces)
CANASTA: list[dict] = [
    # --- Lácteos y huevos ---
    {"id": 1,  "categoria": "lacteos",     "nombre_ref": "Leche entera La Serenísima",          "presentacion": "1 L",           "ean": None},
    {"id": 2,  "categoria": "lacteos",     "nombre_ref": "Yogur bebible Ser o SanCor frutilla", "presentacion": "900 g / 1 L",   "ean": None},
    {"id": 3,  "categoria": "lacteos",     "nombre_ref": "Queso cremoso La Paulina",             "presentacion": "por kg",        "ean": None},
    {"id": 4,  "categoria": "lacteos",     "nombre_ref": "Manteca La Serenísima",               "presentacion": "200 g",         "ean": None},
    {"id": 5,  "categoria": "lacteos",     "nombre_ref": "Huevos blancos",                      "presentacion": "maple x 12",    "ean": None},
    # --- Almacén ---
    {"id": 6,  "categoria": "almacen",     "nombre_ref": "Aceite de girasol Natura o Cocinero", "presentacion": "1.5 L",         "ean": None},
    {"id": 7,  "categoria": "almacen",     "nombre_ref": "Arroz largo fino Gallo o Molinos Ala","presentacion": "1 kg",          "ean": None},
    {"id": 8,  "categoria": "almacen",     "nombre_ref": "Fideos secos Matarazzo o Lucchetti",  "presentacion": "500 g",         "ean": None},
    {"id": 9,  "categoria": "almacen",     "nombre_ref": "Harina de trigo 000 Morixe",          "presentacion": "1 kg",          "ean": None},
    {"id": 10, "categoria": "almacen",     "nombre_ref": "Azúcar Ledesma",                      "presentacion": "1 kg",          "ean": None},
    {"id": 11, "categoria": "almacen",     "nombre_ref": "Yerba mate Playadito o Taragüí",      "presentacion": "1 kg",          "ean": None},
    {"id": 12, "categoria": "almacen",     "nombre_ref": "Café molido La Virginia o Cabrales",  "presentacion": "250 g",         "ean": None},
    {"id": 13, "categoria": "almacen",     "nombre_ref": "Puré de tomate Arcor o Cica",         "presentacion": "520 g",         "ean": None},
    {"id": 14, "categoria": "almacen",     "nombre_ref": "Sal fina Celusal",                    "presentacion": "500 g",         "ean": None},
    # --- Panificados ---
    {"id": 15, "categoria": "panificados", "nombre_ref": "Pan lactal Bimbo o Fargo",            "presentacion": "460 g",         "ean": None},
    {"id": 16, "categoria": "panificados", "nombre_ref": "Galletitas Criollitas o Traviata",    "presentacion": "pack 3 u.",     "ean": None},
    # --- Carnes y frescos ---
    {"id": 17, "categoria": "carnes",      "nombre_ref": "Carne picada común",                  "presentacion": "por kg",        "ean": None},
    {"id": 18, "categoria": "carnes",      "nombre_ref": "Pollo entero",                        "presentacion": "por kg",        "ean": None},
    {"id": 19, "categoria": "carnes",      "nombre_ref": "Paleta cocida fiambre",               "presentacion": "por kg",        "ean": None},
    # --- Bebidas ---
    {"id": 20, "categoria": "bebidas",     "nombre_ref": "Coca-Cola",                           "presentacion": "2.25 L",        "ean": None},
    {"id": 21, "categoria": "bebidas",     "nombre_ref": "Agua sin gas Villavicencio",          "presentacion": "2 L",           "ean": None},
    {"id": 22, "categoria": "bebidas",     "nombre_ref": "Cerveza Quilmes",                     "presentacion": "1 L retornable","ean": None},
    # --- Limpieza e higiene ---
    {"id": 23, "categoria": "limpieza",    "nombre_ref": "Detergente Magistral",                "presentacion": "500 ml",        "ean": None},
    {"id": 24, "categoria": "limpieza",    "nombre_ref": "Lavandina Ayudín",                    "presentacion": "1 L",           "ean": None},
    {"id": 25, "categoria": "limpieza",    "nombre_ref": "Papel higiénico Higienol o Elite",   "presentacion": "pack 4 u.",     "ean": None},
    {"id": 26, "categoria": "limpieza",    "nombre_ref": "Jabón en polvo Skip o Ala",           "presentacion": "800 g / 900 ml","ean": None},
]

# Parámetros de scraping
DELAY_MIN_SEG: float = 2.0
DELAY_MAX_SEG: float = 4.0
MAX_REINTENTOS: int = 3
USER_AGENT: str = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
