"""
Tests de los hallazgos publicables (pipeline/hallazgos.py).

Verifica el cálculo de dispersión de precios entre cadenas.

Ejecutar: pytest  (o: python -m unittest)
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pipeline import hallazgos, normalize


class TestDispersion(unittest.TestCase):

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.db = self.dir / "atlas.db"
        self.out = self.dir / "hallazgos.json"
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        normalize._crear_schema(con)
        con.execute("INSERT INTO productos (id, nombre_normalizado, nombre_original, categoria, en_canasta, activo) "
                    "VALUES (1,'a','Prod A','almacen',1,1)")
        con.execute("INSERT INTO productos (id, nombre_normalizado, nombre_original, categoria, en_canasta, activo) "
                    "VALUES (2,'b','Prod B','bebidas',1,1)")
        # Prod A: coto 100, dia 150 (dispersión 50%). Prod B: solo coto (se excluye).
        for pid, fuente, precio in [(1, "coto", 100.0), (1, "dia", 150.0), (2, "coto", 80.0)]:
            con.execute("INSERT INTO precios (producto_id, fecha, precio_lista, fuente) "
                        "VALUES (?, '2026-07-25', ?, ?)", (pid, precio, fuente))
        con.commit()
        con.close()

    def _generar(self):
        hallazgos.generar(db_path=self.db, out_path=self.out)
        return json.loads(self.out.read_text())

    def test_solo_productos_en_2_o_mas_cadenas(self):
        disp = self._generar()["dispersion"]
        self.assertEqual(disp["n_productos"], 1)  # Prod B (1 cadena) excluido

    def test_dispersion_calculada(self):
        disp = self._generar()["dispersion"]
        top = disp["top"][0]
        self.assertEqual(top["producto"], "Prod A")
        self.assertAlmostEqual(top["dispersion_pct"], 50.0, places=1)
        self.assertEqual(top["mas_barata"], "coto")
        self.assertEqual(top["mas_cara"], "dia")
        self.assertEqual(top["precio_min"], 100.0)
        self.assertEqual(top["precio_max"], 150.0)


if __name__ == "__main__":
    unittest.main()
