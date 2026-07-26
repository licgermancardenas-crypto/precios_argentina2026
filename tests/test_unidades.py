"""
Tests del parser de presentación y del precio por unidad (pipeline/unidades.py).

Ejecutar: pytest  (o: python -m unittest)
"""

import unittest

from pipeline import unidades
from pipeline.unidades import parse_presentacion, precio_por_unidad
from scraper.config import CANASTA


class TestParsePresentacion(unittest.TestCase):

    def test_gramos_a_kg(self):
        self.assertEqual(parse_presentacion("250 g"), (0.25, "kg"))
        self.assertEqual(parse_presentacion("500 g"), (0.5, "kg"))

    def test_kg(self):
        self.assertEqual(parse_presentacion("1 kg"), (1.0, "kg"))

    def test_litros(self):
        self.assertEqual(parse_presentacion("2.25 L"), (2.25, "L"))
        self.assertEqual(parse_presentacion("1 L retornable"), (1.0, "L"))

    def test_ml_y_cc_a_litro(self):
        self.assertEqual(parse_presentacion("500 ml"), (0.5, "L"))
        self.assertEqual(parse_presentacion("200 cc"), (0.2, "L"))

    def test_por_kg_frescos(self):
        self.assertEqual(parse_presentacion("por kg"), (1.0, "kg"))

    def test_unidades(self):
        self.assertEqual(parse_presentacion("maple x 12"), (12.0, "un"))
        self.assertEqual(parse_presentacion("pack 4 u."), (4.0, "un"))

    def test_coma_decimal(self):
        self.assertEqual(parse_presentacion("1,5 L"), (1.5, "L"))

    def test_vacio(self):
        self.assertEqual(parse_presentacion(None), (1.0, "un"))

    def test_toda_la_canasta_parsea(self):
        # Ningún producto de canasta debe romper el parser
        for p in CANASTA:
            cant, base = parse_presentacion(p["presentacion"])
            self.assertGreater(cant, 0)
            self.assertIn(base, ("kg", "L", "un"))


class TestPrecioPorUnidad(unittest.TestCase):

    def test_calculo(self):
        # Café 250 g a $8000 -> $32000/kg
        ean = next(e for e, pres in unidades.PRESENTACION_POR_EAN.items() if pres == "250 g")
        pu = precio_por_unidad(8000.0, ean)
        self.assertIsNotNone(pu)
        self.assertAlmostEqual(pu[0], 32000.0, places=0)
        self.assertEqual(pu[1], "kg")

    def test_ean_desconocido(self):
        self.assertIsNone(precio_por_unidad(1000.0, "0000000000000"))

    def test_precio_cero(self):
        ean = next(iter(unidades.PRESENTACION_POR_EAN))
        self.assertIsNone(precio_por_unidad(0, ean))


if __name__ == "__main__":
    unittest.main()
