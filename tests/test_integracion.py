"""
Test de integración del pipeline: snapshot crudo → normalize → base → índice.

Corre el punto de entrada real (`normalize.normalizar`) sobre snapshots crudos de
ejemplo (dos cadenas, misma fecha) y verifica el flujo completo end-to-end:
matching por EAN, guard de promo absurdo, en_canasta, índice fuente-aware.

Ejecutar: pytest  (o: python -m unittest)
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pipeline import normalize
from scraper.config import CANASTA

# Dos EAN reales de la canasta + uno ajeno (sustituto)
_EAN_A, _EAN_B = [str(p["ean"]) for p in CANASTA if p.get("ean")][:2]
_EAN_SUBSTITUTO = "9999999999999"
FECHA = "2026-07-01"


def _producto(ean, nombre, precio, promo=None, categoria="almacen"):
    return {
        "nombre_original": nombre, "nombre_ref": nombre, "categoria": categoria,
        "ean": ean, "formato_qty": 1, "unidad_medida": "un", "formato": "",
        "precio_lista": precio, "precio_promo": promo, "precio_unitario": None,
    }


def _snapshot(fuente, productos):
    return {"fecha": FECHA, "fuente": fuente, "total_ok": len(productos),
            "total_errores": 0, "errores": [], "productos": productos}


class TestPipelineIntegracion(unittest.TestCase):

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        raw = self.dir / "raw"
        (raw / "coto").mkdir(parents=True)
        (raw / "dia").mkdir(parents=True)
        # Coto: A con promo absurdo (debe descartarse), B con promo válido, + un sustituto
        (raw / "coto" / f"{FECHA}.json").write_text(json.dumps(_snapshot("coto", [
            _producto(_EAN_A, "Producto A", 5000, promo=400000),   # promo > lista -> descartado
            _producto(_EAN_B, "Producto B", 1000, promo=800),      # promo válido
            _producto(_EAN_SUBSTITUTO, "Sustituto raro", 999),     # EAN ajeno -> en_canasta=0
        ])))
        # Día: mismo A por EAN (otro precio) -> debe compartir producto_id
        (raw / "dia" / f"{FECHA}.json").write_text(json.dumps(_snapshot("dia", [
            _producto(_EAN_A, "Producto A en Dia", 5500),
        ])))

        # Redirigir los paths del módulo a la base temporal
        self._orig_raw, self._orig_db = normalize.RAW_DIR, normalize.DB_PATH
        normalize.RAW_DIR = raw
        normalize.DB_PATH = self.dir / "atlas.db"

        normalize.normalizar(FECHA)   # ← corre el pipeline real
        self.con = sqlite3.connect(normalize.DB_PATH)
        self.con.row_factory = sqlite3.Row

    def tearDown(self):
        self.con.close()
        normalize.RAW_DIR, normalize.DB_PATH = self._orig_raw, self._orig_db

    def _precio(self, ean, fuente):
        return self.con.execute(
            "SELECT pr.precio_lista, pr.precio_promo FROM precios pr JOIN productos p ON p.id=pr.producto_id "
            "WHERE p.ean=? AND pr.fuente=?", (ean, fuente)).fetchone()

    def test_precios_cargados(self):
        self.assertEqual(self._precio(_EAN_A, "coto")["precio_lista"], 5000)
        self.assertEqual(self._precio(_EAN_B, "coto")["precio_lista"], 1000)

    def test_guard_promo_absurdo(self):
        # A: promo 400000 > lista 5000 -> descartado (NULL)
        self.assertIsNone(self._precio(_EAN_A, "coto")["precio_promo"])
        # B: promo 800 < lista 1000 -> se conserva
        self.assertEqual(self._precio(_EAN_B, "coto")["precio_promo"], 800)

    def test_en_canasta_solo_para_canasta(self):
        en_a = self.con.execute("SELECT en_canasta FROM productos WHERE ean=?", (_EAN_A,)).fetchone()[0]
        en_sub = self.con.execute("SELECT en_canasta FROM productos WHERE ean=?", (_EAN_SUBSTITUTO,)).fetchone()[0]
        self.assertEqual(en_a, 1)
        self.assertEqual(en_sub, 0)

    def test_matching_ean_cross_cadena(self):
        # El mismo EAN en coto y dia comparte producto_id
        ids = [r[0] for r in self.con.execute("SELECT DISTINCT producto_id FROM precios pr "
               "JOIN productos p ON p.id=pr.producto_id WHERE p.ean=?", (_EAN_A,)).fetchall()]
        self.assertEqual(len(ids), 1)
        self.assertEqual(self._precio(_EAN_A, "dia")["precio_lista"], 5500)

    def test_indice_fuente_aware(self):
        # coto: A(5000)+B(1000)=6000. dia: solo A(5500) -> índices distintos.
        self.assertEqual(normalize.calcular_indice(self.con, FECHA, "coto"), 6000)
        self.assertEqual(normalize.calcular_indice(self.con, FECHA, "dia"), 5500)


if __name__ == "__main__":
    unittest.main()
