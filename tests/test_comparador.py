"""
Tests del criterio de comparabilidad entre cadenas (pipeline/comparador.py).

El bug que cubren: una cadena que deja de listar un producto conserva su último
precio en la base, y ese precio viejo le ganaba la comparación a los precios de
hoy. El comparador publicaba como "más barato" un precio que ya no existe.

Ejecutar: pytest  (o: python -m unittest)
"""

import unittest

import pandas as pd

from pipeline.comparador import DIAS_COMPARABLES, ultimo_por_cadena


def _precios(filas):
    """filas: (producto_id, nombre, fuente, fecha, precio)"""
    return pd.DataFrame(
        filas, columns=["producto_id", "nombre_original", "fuente", "fecha", "precio_lista"]
    )


class TestUltimoPorCadena(unittest.TestCase):

    def test_se_queda_con_la_ultima_lectura_de_cada_cadena(self):
        df = _precios([
            (1, "Arroz", "dia", "2026-08-22", 1000.0),
            (1, "Arroz", "dia", "2026-08-23", 1079.0),
            (1, "Arroz", "coto", "2026-08-23", 1100.0),
        ])
        ult = ultimo_por_cadena(df)
        self.assertEqual(len(ult), 2)
        self.assertEqual(ult.set_index("fuente").loc["dia", "precio_lista"], 1079.0)

    def test_descarta_la_cadena_que_dejo_de_listar_el_producto(self):
        # El caso real: Carrefour a $1025 el 05-08 le ganaba a Día a $1079 hoy.
        df = _precios([
            (1, "Arroz", "carrefour", "2026-08-05", 1025.0),
            (1, "Arroz", "dia", "2026-08-23", 1079.0),
        ])
        ult = ultimo_por_cadena(df)
        self.assertEqual(list(ult["fuente"]), ["dia"])
        # Y por lo tanto el "más barato" ya no es el precio fantasma.
        self.assertEqual(ult["precio_lista"].min(), 1079.0)

    def test_tolera_el_desfasaje_normal_del_relevamiento(self):
        # Un día de diferencia entre cadenas es ruido del cron, no un precio viejo.
        df = _precios([
            (1, "Arroz", "carrefour", "2026-08-22", 1010.0),
            (1, "Arroz", "dia", "2026-08-23", 1079.0),
        ])
        self.assertEqual(len(ultimo_por_cadena(df)), 2)

    def test_el_limite_de_tolerancia_es_inclusivo(self):
        borde = pd.Timestamp("2026-08-23") - pd.Timedelta(days=DIAS_COMPARABLES)
        df = _precios([
            (1, "Arroz", "carrefour", borde.strftime("%Y-%m-%d"), 1010.0),
            (1, "Arroz", "dia", "2026-08-23", 1079.0),
        ])
        self.assertEqual(len(ultimo_por_cadena(df)), 2)

    def test_un_producto_viejo_en_todas_las_cadenas_no_desaparece(self):
        # La referencia es el propio producto, no el relevamiento global: si
        # nadie lo releva hace un mes, se sigue mostrando (con su fecha).
        df = _precios([
            (1, "Arroz", "dia", "2026-08-23", 1079.0),
            (2, "Queso rallado", "carrefour", "2026-07-29", 2300.0),
            (2, "Queso rallado", "jumbo", "2026-07-28", 2350.0),
        ])
        ult = ultimo_por_cadena(df)
        self.assertEqual(set(ult["producto_id"]), {1, 2})
        self.assertEqual(len(ult[ult["producto_id"] == 2]), 2)

    def test_arrastra_las_columnas_extra(self):
        df = _precios([(1, "Arroz", "dia", "2026-08-23", 1079.0)])
        df["categoria"] = "almacen"
        ult = ultimo_por_cadena(df, extra=("categoria",))
        self.assertEqual(ult.iloc[0]["categoria"], "almacen")

    def test_dataframe_vacio(self):
        self.assertTrue(ultimo_por_cadena(_precios([])).empty)


if __name__ == "__main__":
    unittest.main()
