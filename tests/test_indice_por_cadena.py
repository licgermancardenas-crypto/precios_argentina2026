"""
Tests de la comparación de inflación entre cadenas (pipeline/indice.py).

El bug que cubren no es de código sino de método: un índice por cadena sobre la
canasta propia de cada una mide composición, no precios. Con datos reales
Carrefour aparecía BAJANDO 1.27% y sobre los productos comunes es el que más
aumenta (+1.83%) — el signo se da vuelta. Estos tests fijan ese control.

Ejecutar: pytest  (o: python -m unittest)
"""

import unittest

import pandas as pd

from pipeline.indice import (
    canasta_comun,
    contraste_composicion,
    indices_por_cadena,
)


def _df(filas):
    """filas: (fecha, fuente, producto, precio_lista)"""
    return pd.DataFrame(filas, columns=["fecha", "fuente", "producto", "precio_lista"])


class TestCanastaComun(unittest.TestCase):

    def test_se_queda_con_los_productos_de_todas_las_cadenas(self):
        df = _df([
            ("2026-08-01", "coto", "arroz", 100.0),
            ("2026-08-01", "coto", "yerba", 200.0),
            ("2026-08-01", "dia", "arroz", 110.0),
        ])
        self.assertEqual(set(canasta_comun(df)["producto"]), {"arroz"})

    def test_se_queda_con_los_dias_de_todas_las_cadenas(self):
        df = _df([
            ("2026-08-01", "coto", "arroz", 100.0),
            ("2026-08-02", "coto", "arroz", 105.0),
            ("2026-08-02", "dia", "arroz", 110.0),
        ])
        self.assertEqual(set(canasta_comun(df)["fecha"]), {"2026-08-02"})

    def test_con_una_sola_cadena_no_hay_nada_que_intersecar(self):
        df = _df([("2026-08-01", "coto", "arroz", 100.0)])
        self.assertEqual(len(canasta_comun(df)), 1)

    def test_vacio(self):
        self.assertTrue(canasta_comun(_df([])).empty)


class TestContrasteComposicion(unittest.TestCase):

    def test_la_canasta_propia_puede_dar_vuelta_el_signo(self):
        # Reproduce el caso real en chico. Las dos cadenas tienen el arroz, que
        # sube 10%. Coto además tiene la yerba, que se desploma: sobre canasta
        # propia Coto "baja", pero sobre el producto común sube igual que Día.
        df = _df([
            ("2026-08-01", "coto", "arroz", 100.0),
            ("2026-08-02", "coto", "arroz", 110.0),
            ("2026-08-01", "coto", "yerba", 100.0),
            ("2026-08-02", "coto", "yerba", 40.0),
            ("2026-08-01", "dia", "arroz", 100.0),
            ("2026-08-02", "dia", "arroz", 110.0),
        ])
        t = contraste_composicion(df).set_index("fuente")
        self.assertLess(t.loc["coto", "var_propia"], 0)      # parece bajar
        self.assertGreater(t.loc["coto", "var_comun"], 0)    # y en realidad sube
        # Controlado, las dos cadenas se movieron igual: la brecha era composición.
        self.assertAlmostEqual(t.loc["coto", "var_comun"], t.loc["dia", "var_comun"])

    def test_informa_cuantos_productos_sostienen_cada_columna(self):
        df = _df([
            ("2026-08-01", "coto", "arroz", 100.0),
            ("2026-08-01", "coto", "yerba", 100.0),
            ("2026-08-01", "dia", "arroz", 100.0),
        ])
        t = contraste_composicion(df).set_index("fuente")
        self.assertEqual(t.loc["coto", "productos_propios"], 2)
        self.assertEqual(t.loc["coto", "productos_comunes"], 1)

    def test_ambas_columnas_se_miden_en_la_misma_ventana(self):
        # Coto arranca un día antes. Ese día extra no puede colarse en var_propia
        # o la diferencia entre columnas dejaría de ser solo composición.
        df = _df([
            ("2026-08-01", "coto", "arroz", 100.0),   # solo coto
            ("2026-08-02", "coto", "arroz", 200.0),
            ("2026-08-03", "coto", "arroz", 220.0),
            ("2026-08-02", "dia", "arroz", 100.0),
            ("2026-08-03", "dia", "arroz", 110.0),
        ])
        t = contraste_composicion(df).set_index("fuente")
        # Del 02 al 03 el arroz de Coto sube 10%, no 120% (que sería desde el 01).
        self.assertAlmostEqual(t.loc["coto", "var_propia"], 10.0)

    def test_vacio(self):
        self.assertTrue(contraste_composicion(_df([])).empty)


class TestIndicesPorCadena(unittest.TestCase):

    def test_una_serie_base_100_por_cadena(self):
        df = _df([
            ("2026-08-01", "coto", "arroz", 100.0),
            ("2026-08-02", "coto", "arroz", 110.0),
            ("2026-08-01", "dia", "arroz", 200.0),
            ("2026-08-02", "dia", "arroz", 210.0),
        ])
        idc = indices_por_cadena(df)
        self.assertEqual(set(idc["fuente"]), {"coto", "dia"})
        primeros = idc.groupby("fuente")["indice"].first()
        self.assertTrue((primeros == 100.0).all())
        # Base 100 neutraliza el nivel: se comparan variaciones, no precios.
        self.assertAlmostEqual(idc[idc.fuente == "coto"]["indice"].iloc[-1], 110.0)
        self.assertAlmostEqual(idc[idc.fuente == "dia"]["indice"].iloc[-1], 105.0)

    def test_corre_sobre_la_canasta_comun(self):
        df = _df([
            ("2026-08-01", "coto", "arroz", 100.0),
            ("2026-08-02", "coto", "arroz", 110.0),
            ("2026-08-01", "coto", "yerba", 100.0),
            ("2026-08-02", "coto", "yerba", 10.0),
            ("2026-08-01", "dia", "arroz", 100.0),
            ("2026-08-02", "dia", "arroz", 110.0),
        ])
        idc = indices_por_cadena(df)
        # La yerba queda afuera, así que Coto marca el +10% del arroz.
        self.assertAlmostEqual(idc[idc.fuente == "coto"]["indice"].iloc[-1], 110.0)

    def test_vacio(self):
        self.assertTrue(indices_por_cadena(_df([])).empty)


if __name__ == "__main__":
    unittest.main()
