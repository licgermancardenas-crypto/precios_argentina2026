"""
URLs de categorías y definición de la Canasta Atlas (26 productos, 6 categorías).
El EAN se congela en el primer scraping y no se modifica manualmente.
"""

# Registro de cadenas. Cada cadena define su motor de scraping y (si es VTEX) su dominio.
# 'coto' usa Constructor.io; el resto usa la API pública de VTEX (misma clase, distinto dominio).
CADENAS: list[dict] = [
    {"fuente": "coto",      "motor": "coto"},
    {"fuente": "dia",       "motor": "vtex", "dominio": "https://diaonline.supermercadosdia.com.ar"},
    {"fuente": "carrefour", "motor": "vtex", "dominio": "https://www.carrefour.com.ar"},
    {"fuente": "jumbo",     "motor": "vtex", "dominio": "https://www.jumbo.com.ar"},
]

# Cadena de referencia para el Índice Canasta Atlas y las vistas históricas del dashboard.
FUENTE_REFERENCIA: str = "coto"

# Categorías a scrapear en Coto Digital
CATEGORIAS_COTO: list[dict] = [
    {"nombre": "lacteos",     "url": "https://www.cotodigital3.com.ar/sitios/cdigi/browse/lacteos-y-huevos/_/N-1500000156"},
    {"nombre": "almacen",     "url": "https://www.cotodigital3.com.ar/sitios/cdigi/browse/almacen/_/N-1500000109"},
    {"nombre": "panificados", "url": "https://www.cotodigital3.com.ar/sitios/cdigi/browse/panaderia-y-reposteria/_/N-1500000130"},
    {"nombre": "carnes",      "url": "https://www.cotodigital3.com.ar/sitios/cdigi/browse/carnes/_/N-1500000118"},
    {"nombre": "bebidas",     "url": "https://www.cotodigital3.com.ar/sitios/cdigi/browse/bebidas/_/N-1500000113"},
    {"nombre": "limpieza",    "url": "https://www.cotodigital3.com.ar/sitios/cdigi/browse/limpieza-del-hogar/_/N-1500000126"},
]

# Canasta Atlas — 26 productos de referencia.
# El EAN se congeló desde el primer scraping de Coto. Es la clave de matching
# cross-cadena: ambas cadenas buscan el mismo producto exacto por EAN.
# Los frescos de balanza (EAN interno con prefijo "2...") no cross-matchean:
# quedan en None y caen al fallback por nombre (solo comparables dentro de Coto).
CANASTA: list[dict] = [
    # --- Lácteos y huevos ---
    {"id": 1,  "categoria": "lacteos",     "nombre_ref": "Leche entera La Serenísima",          "presentacion": "1 L",           "ean": "7790742363008"},
    {"id": 2,  "categoria": "lacteos",     "nombre_ref": "Yogur bebible Ser o SanCor frutilla", "presentacion": "900 g / 1 L",   "ean": "7798321152333"},
    {"id": 3,  "categoria": "lacteos",     "nombre_ref": "Queso cremoso La Paulina",             "presentacion": "por kg",        "ean": None},
    {"id": 4,  "categoria": "lacteos",     "nombre_ref": "Manteca La Serenísima",               "presentacion": "200 g",         "ean": "7793940054006"},
    {"id": 5,  "categoria": "lacteos",     "nombre_ref": "Huevo blanco maple 12",              "presentacion": "maple x 12",    "ean": "7798092353120"},
    # --- Almacén ---
    {"id": 6,  "categoria": "almacen",     "nombre_ref": "Aceite girasol Natura 1.5 litros",  "presentacion": "1.5 L",         "ean": "7790272001029"},
    {"id": 7,  "categoria": "almacen",     "nombre_ref": "Arroz largo fino Molinos Ala 1kg",     "presentacion": "1 kg",          "ean": "7791120100857"},
    {"id": 8,  "categoria": "almacen",     "nombre_ref": "Fideos tallarines Matarazzo 500g",     "presentacion": "500 g",         "ean": "7790070336316"},
    {"id": 9,  "categoria": "almacen",     "nombre_ref": "Harina de trigo 000 Morixe 1kg",       "presentacion": "1 kg",          "ean": "7790199000013"},
    {"id": 10, "categoria": "almacen",     "nombre_ref": "Azúcar Ledesma 1kg",                   "presentacion": "1 kg",          "ean": "7792540250450"},
    {"id": 11, "categoria": "almacen",     "nombre_ref": "Yerba mate Taragui 1kg",               "presentacion": "1 kg",          "ean": "7790387120349"},
    {"id": 12, "categoria": "almacen",     "nombre_ref": "Cafe molido La Virginia 250g",         "presentacion": "250 g",         "ean": "7790150007501"},
    {"id": 13, "categoria": "almacen",     "nombre_ref": "Pure de tomate Arcor 520g",            "presentacion": "520 g",         "ean": "7790580146115"},
    {"id": 14, "categoria": "almacen",     "nombre_ref": "Sal fina Celusal",                    "presentacion": "500 g",         "ean": "7790072001014"},
    # --- Panificados ---
    {"id": 15, "categoria": "panificados", "nombre_ref": "Pan lactal blanco Bimbo",             "presentacion": "400 g",         "ean": "7793890261233"},
    {"id": 16, "categoria": "panificados", "nombre_ref": "Galletitas Criollitas Traviata",      "presentacion": "pack 3 u.",     "ean": "7790040143937"},
    # --- Carnes y frescos ---
    {"id": 17, "categoria": "carnes",      "nombre_ref": "Picada especial vacuna",             "presentacion": "por kg",        "ean": None},
    {"id": 18, "categoria": "carnes",      "nombre_ref": "Pollo entero",                        "presentacion": "por kg",        "ean": None},
    {"id": 19, "categoria": "carnes",      "nombre_ref": "Paleta cocida fiambre",               "presentacion": "por kg",        "ean": None},
    # --- Bebidas ---
    {"id": 20, "categoria": "bebidas",     "nombre_ref": "Coca-Cola Original 2.25L",            "presentacion": "2.25 L",        "ean": "7790895000997"},
    {"id": 21, "categoria": "bebidas",     "nombre_ref": "Agua sin gas Villavicencio",          "presentacion": "2 L",           "ean": "7799155000197"},
    {"id": 22, "categoria": "bebidas",     "nombre_ref": "Cerveza Quilmes",                     "presentacion": "1 L retornable","ean": "7792798007387"},
    # --- Limpieza e higiene ---
    {"id": 23, "categoria": "limpieza",    "nombre_ref": "Detergente Magistral",                "presentacion": "500 ml",        "ean": "7790990003039"},
    {"id": 24, "categoria": "limpieza",    "nombre_ref": "Lavandina Ayudín",                    "presentacion": "1 L",           "ean": "7793253006709"},
    {"id": 25, "categoria": "limpieza",    "nombre_ref": "Papel higiénico Higienol o Elite",   "presentacion": "pack 4 u.",     "ean": "7790250026075"},
    {"id": 26, "categoria": "limpieza",    "nombre_ref": "Jabon en polvo Ala 800g",             "presentacion": "800 g / 900 ml","ean": "7791290796829"},
]

# Parámetros de scraping
DELAY_MIN_SEG: float = 2.0
DELAY_MAX_SEG: float = 4.0
MAX_REINTENTOS: int = 3
USER_AGENT: str = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
