"""
Tests del guard de SOLO LECTURA del agente (agent/preguntar.py).

La tool `consultar_sql` no debe permitir ninguna operación de escritura ni
inyección. No requiere el SDK de Anthropic (probamos solo _consultar_sql_impl).

Ejecutar: pytest  (o: python -m unittest)
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from agent import preguntar


class TestSQLReadOnly(unittest.TestCase):

    def setUp(self):
        # Base temporal con una tabla y una fila
        self.tmp = Path(tempfile.mkdtemp()) / "test.db"
        con = sqlite3.connect(self.tmp)
        con.execute("CREATE TABLE t (id INTEGER, v TEXT)")
        con.execute("INSERT INTO t VALUES (1, 'hola')")
        con.commit()
        con.close()
        self._orig = preguntar.DB_PATH
        preguntar.DB_PATH = self.tmp

    def tearDown(self):
        preguntar.DB_PATH = self._orig

    def test_select_valido(self):
        r = preguntar._consultar_sql_impl("SELECT v FROM t WHERE id = 1")
        self.assertIn("hola", r)

    def test_with_valido(self):
        r = preguntar._consultar_sql_impl("WITH x AS (SELECT 1 AS n) SELECT n FROM x")
        self.assertIn("1", r)

    def test_rechaza_escrituras(self):
        for sql in ("DELETE FROM t", "DROP TABLE t", "UPDATE t SET v='x'",
                    "INSERT INTO t VALUES (2,'y')", "ALTER TABLE t ADD COLUMN z INT",
                    "CREATE TABLE u (a INT)", "PRAGMA table_info(t)"):
            with self.subTest(sql=sql):
                self.assertTrue(preguntar._consultar_sql_impl(sql).startswith("ERROR"))

    def test_rechaza_inyeccion_con_punto_y_coma(self):
        r = preguntar._consultar_sql_impl("SELECT 1; DROP TABLE t")
        self.assertTrue(r.startswith("ERROR"))

    def test_la_tabla_sigue_intacta_tras_intentos(self):
        # Aunque el guard fallara, el modo ro bloquearía la escritura.
        preguntar._consultar_sql_impl("DELETE FROM t")
        con = sqlite3.connect(self.tmp)
        n = con.execute("SELECT COUNT(*) FROM t").fetchone()[0]
        con.close()
        self.assertEqual(n, 1)


if __name__ == "__main__":
    unittest.main()
