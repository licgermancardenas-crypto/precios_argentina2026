"""
Tests del matching por EAN y del cálculo del índice.

- _upsert_producto: mismo EAN (aunque venga de otra cadena) = mismo producto_id.
- calcular_indice: filtra por `fuente` (no mezcla cadenas).
- _construir_indice (export): índice encadenado, sin frescos de balanza.

Ejecutar: pytest  (o: python -m unittest)
"""

import sqlite3
import unittest

import pandas as pd

from pipeline import normalize
from pipeline.export import _construir_indice
from pipeline.indice import indice_encadenado


def _db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    normalize._crear_schema(con)
    return con


def _prod(ean, nombre, categoria="almacen", qty=1.0, unidad="un", formato=""):
    return {"ean": ean, "nombre_original": nombre, "categoria": categoria,
            "formato_qty": qty, "unidad_medida": unidad, "formato": formato}


class TestMatchingEAN(unittest.TestCase):

    def test_mismo_ean_mismo_id(self):
        con = _db()
        # "coto" ve el producto con un nombre; "dia" lo ve con otro nombre pero mismo EAN
        id1 = normalize._upsert_producto(con, _prod("779123", "Leche La Serenisima 1L Coto"))
        id2 = normalize._upsert_producto(con, _prod("779123", "Leche Entera La Sere 1 Lt Dia"))
        self.assertEqual(id1, id2)
        con.close()

    def test_ean_distinto_id_distinto(self):
        con = _db()
        id1 = normalize._upsert_producto(con, _prod("111", "Producto A"))
        id2 = normalize._upsert_producto(con, _prod("222", "Producto B"))
        self.assertNotEqual(id1, id2)
        con.close()

    def test_fallback_por_nombre_sin_ean(self):
        con = _db()
        # Frescos sin EAN: matchea por nombre normalizado
        id1 = normalize._upsert_producto(con, _prod(None, "Pollo Entero"))
        id2 = normalize._upsert_producto(con, _prod(None, "Pollo Entero"))
        self.assertEqual(id1, id2)
        con.close()


class TestEnCanasta(unittest.TestCase):
    """Solo los productos con EAN de la canasta se marcan en_canasta=1."""

    def test_ean_de_canasta_marca_1(self):
        con = _db()
        ean_real = next(iter(normalize.CANASTA_EANS))  # un EAN real de la canasta
        pid = normalize._upsert_producto(con, _prod(ean_real, "Producto canasta"))
        en = con.execute("SELECT en_canasta FROM productos WHERE id=?", (pid,)).fetchone()[0]
        self.assertEqual(en, 1)
        con.close()

    def test_sustituto_con_ean_ajeno_marca_0(self):
        con = _db()
        # Un EAN que NO está en la canasta (sustituto que devolvió una cadena)
        pid = normalize._upsert_producto(con, _prod("9999999999999", "Sustituto random"))
        en = con.execute("SELECT en_canasta FROM productos WHERE id=?", (pid,)).fetchone()[0]
        self.assertEqual(en, 0)
        con.close()


class TestIndiceFuenteAware(unittest.TestCase):

    def _insertar_precio(self, con, pid, fecha, precio, fuente):
        con.execute(
            "INSERT INTO precios (producto_id, fecha, precio_lista, fuente) VALUES (?,?,?,?)",
            (pid, fecha, precio, fuente),
        )

    def test_indice_no_mezcla_cadenas(self):
        con = _db()
        # EAN real de canasta para que el producto quede en_canasta=1
        ean = next(iter(normalize.CANASTA_EANS))
        pid = normalize._upsert_producto(con, _prod(ean, "Producto"))
        self._insertar_precio(con, pid, "2026-07-25", 100.0, "coto")
        self._insertar_precio(con, pid, "2026-07-25", 250.0, "dia")
        con.commit()
        # El índice de 'coto' debe ver 100, no 250 ni 350
        self.assertEqual(normalize.calcular_indice(con, "2026-07-25", "coto"), 100.0)
        self.assertEqual(normalize.calcular_indice(con, "2026-07-25", "dia"), 250.0)
        con.close()


def _fila(fecha, producto, precio, *, categoria="almacen", ean="1", peso_variable=0):
    return {"fecha": fecha, "fuente": "coto", "categoria": categoria, "ean": ean,
            "producto": producto, "precio_lista": precio, "peso_variable": peso_variable}


class TestIndiceEncadenado(unittest.TestCase):
    """El índice del export encadena ratios sobre los productos pareados."""

    def test_alta_de_producto_no_mueve_el_indice(self):
        # A: presente los 2 días (100 -> 110). B: aparece recién el día 2.
        df = pd.DataFrame([
            _fila("2026-07-01", "a", 100.0),
            _fila("2026-07-02", "a", 110.0),
            _fila("2026-07-02", "b", 999.0, ean="2"),
        ])
        total = _construir_indice(df).query("categoria == 'TOTAL'").sort_values("fecha")
        # B no tiene par el 01, así que no entra al ratio: +10%, no un salto por composición.
        self.assertEqual(list(total["indice_base100"]), [100.0, 110.0])

    def test_base_100_primer_dia(self):
        df = pd.DataFrame([
            _fila("2026-07-01", "a", 50.0, categoria="lacteos"),
            _fila("2026-07-02", "a", 75.0, categoria="lacteos"),
        ])
        total = _construir_indice(df).query("categoria == 'TOTAL'").sort_values("fecha")
        self.assertEqual(total["indice_base100"].iloc[0], 100.0)
        self.assertEqual(total["indice_base100"].iloc[1], 150.0)

    def test_producto_tardio_aporta_desde_que_tiene_par(self):
        """
        Lo que la suma simple sobre serie completa no hacía: B entra el día 2 y
        desde el día 3 su variación cuenta. Antes quedaba excluido para siempre.
        """
        df = pd.DataFrame([
            _fila("2026-07-01", "a", 100.0),
            _fila("2026-07-02", "a", 100.0),
            _fila("2026-07-02", "b", 100.0, ean="2"),
            _fila("2026-07-03", "a", 100.0),
            _fila("2026-07-03", "b", 200.0, ean="2"),   # B duplica: 200/100 sobre el par {a,b}
        ])
        total = _construir_indice(df).query("categoria == 'TOTAL'").sort_values("fecha")
        # día 3: (100+200)/(100+100) = 1.5 -> 150
        self.assertEqual(list(total["indice_base100"]), [100.0, 100.0, 150.0])

    def test_peso_variable_queda_fuera_del_indice(self):
        """Los frescos de balanza se relevan pero no mueven el índice."""
        df = pd.DataFrame([
            _fila("2026-07-01", "a", 100.0),
            _fila("2026-07-01", "paleta", 10000.0, ean="2", peso_variable=1),
            _fila("2026-07-02", "a", 100.0),
            _fila("2026-07-02", "paleta", 20000.0, ean="2", peso_variable=1),  # pieza más pesada
        ])
        total = _construir_indice(df).query("categoria == 'TOTAL'").sort_values("fecha")
        self.assertEqual(list(total["indice_base100"]), [100.0, 100.0])

    def test_costo_y_indice_son_consistentes(self):
        """En el CSV público, costo_t/costo_s tiene que dar igual que indice_t/indice_s."""
        df = pd.DataFrame([
            _fila("2026-07-01", "a", 100.0),
            _fila("2026-07-02", "a", 125.0),
        ])
        total = _construir_indice(df).query("categoria == 'TOTAL'").sort_values("fecha")
        razon_costo = total["costo_canasta"].iloc[1] / total["costo_canasta"].iloc[0]
        razon_indice = total["indice_base100"].iloc[1] / total["indice_base100"].iloc[0]
        self.assertAlmostEqual(razon_costo, razon_indice, places=4)
        # El ancla es el último día: el costo publicado hoy es el de la góndola.
        self.assertAlmostEqual(total["costo_canasta"].iloc[-1], 125.0, places=2)


class TestIndiceBordes(unittest.TestCase):

    def test_dia_sin_productos_pareados_sostiene_el_indice(self):
        """
        Si un día no comparte ningún producto con el anterior no hay variación
        medible: el índice se sostiene en vez de saltar por el cambio de canasta.
        """
        df = pd.DataFrame([
            {"fecha": "2026-07-01", "producto": "a", "precio_lista": 100.0},
            {"fecha": "2026-07-02", "producto": "b", "precio_lista": 5000.0},
            {"fecha": "2026-07-03", "producto": "b", "precio_lista": 5500.0},
        ])
        self.assertEqual(list(indice_encadenado(df)), [100.0, 100.0, 110.0])

    def test_df_vacio_no_explota(self):
        vacio = pd.DataFrame(columns=["fecha", "producto", "precio_lista"])
        self.assertTrue(indice_encadenado(vacio).empty)


class TestMigracionImagenes(unittest.TestCase):
    """La tabla imagenes llega a bases ya creadas y guarda una foto por cadena."""

    def test_migracion_crea_la_tabla_en_una_base_vieja(self):
        con = _db()
        con.execute("DROP TABLE imagenes")            # base anterior a v5
        for _ in range(2):                            # idempotente
            normalize._migrar_schema(con)
        tablas = {r["name"] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("imagenes", tablas)

    def test_una_foto_por_producto_y_cadena_y_se_actualiza(self):
        con = _db()
        con.execute("INSERT INTO productos (id, nombre_normalizado, categoria) "
                    "VALUES (1, 'leche', 'lacteos')")
        def guardar(fuente, url, fecha):
            con.execute(
                """INSERT INTO imagenes (producto_id, fuente, url, actualizado)
                   VALUES (1, ?, ?, ?)
                   ON CONFLICT (producto_id, fuente)
                   DO UPDATE SET url = excluded.url, actualizado = excluded.actualizado""",
                (fuente, url, fecha))
        guardar("coto", "http://a/1.jpg", "2026-08-19")
        guardar("dia", "http://b/1.jpg", "2026-08-19")
        # Las URLs de VTEX rotan al recargar el catálogo: la última vista gana.
        guardar("coto", "http://a/2.jpg", "2026-08-20")

        filas = dict(con.execute("SELECT fuente, url FROM imagenes").fetchall())
        self.assertEqual(filas, {"coto": "http://a/2.jpg", "dia": "http://b/1.jpg"})


class TestMigracionPesoVariable(unittest.TestCase):
    """La columna peso_variable llega a bases ya creadas y se re-sincroniza sola."""

    def test_migracion_es_idempotente(self):
        con = _db()
        con.execute("ALTER TABLE productos DROP COLUMN peso_variable")   # base "vieja"
        for _ in range(2):
            normalize._migrar_schema(con)
        cols = {r["name"] for r in con.execute("PRAGMA table_info(productos)")}
        self.assertIn("peso_variable", cols)

    def test_marca_los_frescos_de_balanza_de_la_config(self):
        from scraper.config import PESO_VARIABLE_EANS
        ean = next(iter(PESO_VARIABLE_EANS))
        con = _db()
        con.execute(
            "INSERT INTO productos (ean, nombre_normalizado, categoria, en_canasta) "
            "VALUES (?, 'x', 'carnes', 1)", (ean,),
        )
        normalize._migrar_schema(con)
        marcado = con.execute("SELECT peso_variable FROM productos WHERE ean=?", (ean,)).fetchone()[0]
        self.assertEqual(marcado, 1)


if __name__ == "__main__":
    unittest.main()
