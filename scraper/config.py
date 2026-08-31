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

# Canasta Atlas — 45 productos. El EAN se congela desde el primer scraping.
# Es la clave de matching cross-cadena: todas buscan el mismo producto por EAN.
# Los frescos de balanza usan el EAN interno de Coto (prefijo "2..."): NO
# cross-matchean con otras cadenas (código propio de Coto), pero fijarlos evita
# que la búsqueda por nombre devuelva un producto equivocado. Quedan fuera del
# comparador entre cadenas, a propósito.
CANASTA: list[dict] = [
    # --- Lácteos y huevos ---
    {"id": 1,  "categoria": "lacteos",     "nombre_ref": "Leche entera La Serenísima",          "presentacion": "1 L",           "ean": "7790742363008"},
    {"id": 2,  "categoria": "lacteos",     "nombre_ref": "Yogur bebible Ser o SanCor frutilla", "presentacion": "900 g / 1 L",   "ean": "7798321152333"},
    {"id": 3,  "categoria": "lacteos",     "nombre_ref": "Queso cremoso La Paulina",             "presentacion": "por kg",        "ean": "2000199000001"},
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
    {"id": 17, "categoria": "carnes",      "nombre_ref": "Picada especial vacuna",             "presentacion": "por kg",        "ean": "2069607000002"},
    {"id": 18, "categoria": "carnes",      "nombre_ref": "Pollo entero",                        "presentacion": "por kg",        "ean": "2000000127910"},
    {"id": 19, "categoria": "carnes",      "nombre_ref": "Paleta cocida fiambre",               "presentacion": "por kg",        "ean": "2003836100003"},
    # --- Bebidas ---
    {"id": 20, "categoria": "bebidas",     "nombre_ref": "Coca-Cola Original 2.25L",            "presentacion": "2.25 L",        "ean": "7790895000997"},
    {"id": 21, "categoria": "bebidas",     "nombre_ref": "Agua sin gas Villavicencio",          "presentacion": "2 L",           "ean": "7799155000197"},
    {"id": 22, "categoria": "bebidas",     "nombre_ref": "Cerveza Quilmes",                     "presentacion": "1 L retornable","ean": "7792798007387"},
    # --- Limpieza e higiene ---
    {"id": 23, "categoria": "limpieza",    "nombre_ref": "Detergente Magistral",                "presentacion": "500 ml",        "ean": "7790990003039"},
    {"id": 24, "categoria": "limpieza",    "nombre_ref": "Lavandina Ayudín",                    "presentacion": "1 L",           "ean": "7793253006709"},
    {"id": 25, "categoria": "limpieza",    "nombre_ref": "Papel higiénico Higienol o Elite",   "presentacion": "pack 4 u.",     "ean": "7790250026075"},
    {"id": 26, "categoria": "limpieza",    "nombre_ref": "Jabon en polvo Ala 800g",             "presentacion": "800 g / 900 ml","ean": "7791290796829"},
    # === Ampliación: canasta extendida a 45 productos (EAN verificado en Coto) ===
    # --- Lácteos y huevos ---
    {"id": 27, "categoria": "lacteos",     "nombre_ref": "Dulce de leche La Serenisima 400g",   "presentacion": "400 g",         "ean": "7790742625205"},
    {"id": 28, "categoria": "lacteos",     "nombre_ref": "Crema de leche La Serenisima",         "presentacion": "200 ml",        "ean": "7790742014122"},
    {"id": 29, "categoria": "lacteos",     "nombre_ref": "Queso rallado 150g",                  "presentacion": "150 g",         "ean": "7790080014198"},
    # --- Almacén ---
    {"id": 30, "categoria": "almacen",     "nombre_ref": "Mermelada Arcor durazno 390g",        "presentacion": "390 g",         "ean": "7790580132224"},
    {"id": 31, "categoria": "almacen",     "nombre_ref": "Arvejas La Campagnola lata",           "presentacion": "lata 350 g",    "ean": "7793360982309"},
    {"id": 32, "categoria": "almacen",     "nombre_ref": "Atun La Campagnola aceite lata",       "presentacion": "lata",          "ean": "7790580138769"},
    {"id": 33, "categoria": "almacen",     "nombre_ref": "Mayonesa Hellmanns 475g",             "presentacion": "475 g",         "ean": "7794000007109"},
    {"id": 34, "categoria": "almacen",     "nombre_ref": "Polenta Presto Pronta",               "presentacion": "490 g",         "ean": "7790580138738"},
    {"id": 35, "categoria": "almacen",     "nombre_ref": "Avena tradicional Quaker 400g",        "presentacion": "550 g",         "ean": "7792170555543"},
    {"id": 36, "categoria": "almacen",     "nombre_ref": "Papas fritas Lays clasicas",           "presentacion": "330 g",         "ean": "7790310985588"},
    # --- Panificados ---
    {"id": 37, "categoria": "panificados", "nombre_ref": "Galletitas dulces Oreo",               "presentacion": "pack",          "ean": "7622201735258"},
    {"id": 38, "categoria": "panificados", "nombre_ref": "Bizcochos 9 de Oro",                   "presentacion": "200 g",         "ean": "7792200000159"},
    # --- Bebidas ---
    {"id": 39, "categoria": "bebidas",     "nombre_ref": "Vino tinto Toro 1L",                   "presentacion": "1.125 L",       "ean": "7790314074219"},
    {"id": 40, "categoria": "bebidas",     "nombre_ref": "Jugo en polvo Tang naranja",           "presentacion": "sobre 15 g",    "ean": "7622201735340"},
    {"id": 41, "categoria": "bebidas",     "nombre_ref": "Gaseosa Sprite 2.25L",                 "presentacion": "2.25 L",        "ean": "7790895064166"},
    # --- Limpieza e higiene ---
    {"id": 42, "categoria": "limpieza",    "nombre_ref": "Shampoo Sedal 190ml",                 "presentacion": "190 ml",        "ean": "7791293045658"},
    {"id": 43, "categoria": "limpieza",    "nombre_ref": "Pasta dental Colgate 90g",            "presentacion": "90 g",          "ean": "7891024135020"},
    {"id": 44, "categoria": "limpieza",    "nombre_ref": "Jabon de tocador Dove",               "presentacion": "pack",          "ean": "7891150046481"},
    {"id": 45, "categoria": "limpieza",    "nombre_ref": "Rollo de cocina Elite",               "presentacion": "un.",           "ean": "7790250022053"},
]

# Frescos de balanza: el precio publicado es el de UNA pieza, cuyo peso varía
# entre relevamientos, así que sus saltos no son inflación (la paleta cocida
# pasó de $14.559 a $24.265 y volvió a $14.999 sin que cambiara el $/kg).
# Se siguen relevando y publicando en precios.csv, pero quedan FUERA del índice:
# un solo producto de estos movía el índice ±8% y hacía que el forecast
# extrapolara el artefacto. Ver pipeline/indice.py.
PESO_VARIABLE_EANS: set[str] = {
    str(p["ean"]) for p in CANASTA if p.get("presentacion") == "por kg" and p.get("ean")
}

# Descuento mínimo, en %, para que una promo se registre como tal.
#
# Un "descuento" del 0,00002% no es un descuento: es ruido de punto flotante. Un
# bug del parser de Jumbo publicó 21 promos falsas por día durante 4 días con
# precios como 7463.0017 contra 7463.0, y nada lo detectó porque el único guard
# que había era `promo < lista`, que esos valores cumplen. Las promos reales
# observadas arrancan en 6,5% (Día) y 10% (Carrefour), así que 0,5% deja pasar
# cualquier oferta legítima y corta el ruido numérico.
DESCUENTO_MINIMO_PCT: float = 0.5

def es_promo_valida(promo: float | None, lista: float | None) -> bool:
    """
    Un promo es válido si es positivo, menor a la lista, y el descuento supera
    DESCUENTO_MINIMO_PCT. Único criterio, usado por los scrapers y el pipeline.
    """
    if promo is None or lista is None or not (0 < promo < lista):
        return False
    return (1 - promo / lista) * 100 >= DESCUENTO_MINIMO_PCT


# Parámetros de scraping
DELAY_MIN_SEG: float = 2.0
DELAY_MAX_SEG: float = 4.0
MAX_REINTENTOS: int = 3
USER_AGENT: str = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
