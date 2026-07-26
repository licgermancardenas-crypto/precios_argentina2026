"""
Tests de la comparativa Índice Canasta vs IPC oficial (pipeline/comparativa_ipc.py).

Verifica el nowcast del mes en curso y el histórico mensual (MoM canasta vs IPC).

Ejecutar: pytest  (o: python -m unittest)
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pipeline import comparativa_ipc, normalize


class TestComparativaIPC(unittest.TestCase):

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.db = self.dir / "atlas.db"
        self.out = self.dir / "comparativa.json"
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        normalize._crear_schema(con)
        # Un producto de canasta con precios en 4 fechas (may, jun, y 2 días de jul)
        con.execute("INSERT INTO productos (id, nombre_normalizado, categoria, en_canasta, activo) "
                    "VALUES (1,'prod','almacen',1,1)")
        for fecha, precio in [("2026-05-31", 100.0), ("2026-06-30", 110.0),
                              ("2026-07-10", 115.0), ("2026-07-20", 121.0)]:
            con.execute("INSERT INTO precios (producto_id, fecha, precio_lista, fuente) "
                        "VALUES (1, ?, ?, 'coto')", (fecha, precio))
        # IPC: mayo 200 -> junio 210 (var junio = +5%)
        for fecha, valor in [("2026-05-01", 200.0), ("2026-06-01", 210.0)]:
            con.execute("INSERT INTO regresores (fecha, serie, valor) VALUES (?, 'ipc', ?)", (fecha, valor))
        con.commit()
        con.close()

    def _generar(self):
        comparativa_ipc.generar(db_path=self.db, out_path=self.out)
        return json.loads(self.out.read_text())

    def test_nowcast_mes_en_curso(self):
        r = self._generar()
        mec = r["mes_en_curso"]
        self.assertEqual(mec["mes"], "2026-07")
        self.assertEqual(mec["dias_observados"], 2)
        # 121/115 - 1 = +5.22%
        self.assertAlmostEqual(mec["var_canasta_pct"], 5.22, places=1)

    def test_ipc_ultimo(self):
        r = self._generar()
        self.assertEqual(r["ipc_ultimo"]["mes"], "2026-06")
        self.assertAlmostEqual(r["ipc_ultimo"]["var_pct"], 5.0, places=1)

    def test_mensual_junio_cerrado(self):
        r = self._generar()
        junio = [m for m in r["mensual"] if m["mes"] == "2026-06"]
        self.assertEqual(len(junio), 1)
        # Canasta junio MoM = 110/100 - 1 = +10%; IPC junio = +5%
        self.assertAlmostEqual(junio[0]["var_canasta_pct"], 10.0, places=1)
        self.assertAlmostEqual(junio[0]["var_ipc_pct"], 5.0, places=1)

    def test_mes_en_curso_no_esta_en_mensual(self):
        r = self._generar()
        self.assertFalse(any(m["mes"] == "2026-07" for m in r["mensual"]))


if __name__ == "__main__":
    unittest.main()
