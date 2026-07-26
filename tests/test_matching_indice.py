"""
Tests del matching por EAN y del cálculo del índice.

- _upsert_producto: mismo EAN (aunque venga de otra cadena) = mismo producto_id.
- calcular_indice: filtra por `fuente` (no mezcla cadenas).
- _construir_indice (export): canasta fija (solo productos con serie completa).

Ejecutar: pytest  (o: python -m unittest)
"""

import sqlite3
import unittest

import pandas as pd

from pipeline import normalize
from pipeline.export import _construir_indice


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


class TestIndiceFuenteAware(unittest.TestCase):

    def _insertar_precio(self, con, pid, fecha, precio, fuente):
        con.execute(
            "INSERT INTO precios (producto_id, fecha, precio_lista, fuente) VALUES (?,?,?,?)",
            (pid, fecha, precio, fuente),
        )

    def test_indice_no_mezcla_cadenas(self):
        con = _db()
        pid = normalize._upsert_producto(con, _prod("779", "Producto"))
        self._insertar_precio(con, pid, "2026-07-25", 100.0, "coto")
        self._insertar_precio(con, pid, "2026-07-25", 250.0, "dia")
        con.commit()
        # El índice de 'coto' debe ver 100, no 250 ni 350
        self.assertEqual(normalize.calcular_indice(con, "2026-07-25", "coto"), 100.0)
        self.assertEqual(normalize.calcular_indice(con, "2026-07-25", "dia"), 250.0)
        con.close()


class TestCanastaFija(unittest.TestCase):
    """El índice del export usa solo productos con precio TODOS los días."""

    def test_producto_incompleto_no_mueve_el_indice(self):
        # A: presente los 2 días (100 -> 110). B: solo el día 2 (aparece).
        df = pd.DataFrame([
            {"fecha": "2026-07-01", "fuente": "coto", "categoria": "almacen", "ean": "1",
             "producto": "a", "precio_lista": 100.0},
            {"fecha": "2026-07-02", "fuente": "coto", "categoria": "almacen", "ean": "1",
             "producto": "a", "precio_lista": 110.0},
            {"fecha": "2026-07-02", "fuente": "coto", "categoria": "almacen", "ean": "2",
             "producto": "b", "precio_lista": 999.0},
        ])
        idx = _construir_indice(df)
        total = idx[idx["categoria"] == "TOTAL"].sort_values("fecha")
        # Solo A entra (serie completa) -> índice 100 y 110, sin salto por B
        self.assertEqual(list(total["indice_base100"]), [100.0, 110.0])

    def test_base_100_primer_dia(self):
        df = pd.DataFrame([
            {"fecha": "2026-07-01", "fuente": "coto", "categoria": "lacteos", "ean": "1",
             "producto": "a", "precio_lista": 50.0},
            {"fecha": "2026-07-02", "fuente": "coto", "categoria": "lacteos", "ean": "1",
             "producto": "a", "precio_lista": 75.0},
        ])
        idx = _construir_indice(df)
        total = idx[idx["categoria"] == "TOTAL"].sort_values("fecha")
        self.assertEqual(total["indice_base100"].iloc[0], 100.0)
        self.assertEqual(total["indice_base100"].iloc[1], 150.0)


if __name__ == "__main__":
    unittest.main()
