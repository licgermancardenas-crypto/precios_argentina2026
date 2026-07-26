"""
Tests del control de calidad diario (pipeline/qc.py).

Verifica la clasificación de estado (ok / warning / critical) según cuántos
productos devolvió el scraper de cada cadena.

Ejecutar: pytest  (o: python -m unittest)
"""

import json
import tempfile
import unittest
from pathlib import Path

from pipeline import qc


class TestQC(unittest.TestCase):

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.raw = self.dir / "raw"
        self.out = self.dir / "qc.json"
        self._orig_raw = qc.RAW_DIR
        qc.RAW_DIR = self.raw

    def tearDown(self):
        qc.RAW_DIR = self._orig_raw

    def _snapshot(self, fuente, fecha, total_ok):
        d = self.raw / fuente
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{fecha}.json").write_text(json.dumps({"total_ok": total_ok, "productos": []}))

    def _fuentes(self):
        return [c["fuente"] for c in qc.CADENAS]

    def test_todas_completas_ok(self):
        for f in self._fuentes():
            self._snapshot(f, "2026-07-26", qc.ESPERADO)
        r = qc.generar(out_path=self.out)
        self.assertEqual(r["estado_global"], "ok")

    def test_cobertura_baja_warning(self):
        fuentes = self._fuentes()
        self._snapshot(fuentes[0], "2026-07-26", qc.ESPERADO)
        # el resto con cobertura ~50% -> warning
        for f in fuentes[1:]:
            self._snapshot(f, "2026-07-26", qc.ESPERADO // 2)
        r = qc.generar(out_path=self.out)
        self.assertEqual(r["estado_global"], "warning")

    def test_cadena_sin_snapshot_critical(self):
        fuentes = self._fuentes()
        # Todas menos una relevan bien; una no tiene snapshot -> critical
        for f in fuentes[:-1]:
            self._snapshot(f, "2026-07-26", qc.ESPERADO)
        r = qc.generar(out_path=self.out)
        self.assertEqual(r["estado_global"], "critical")
        self.assertEqual(r["cadenas"][fuentes[-1]]["estado"], "critical")

    def test_sin_datos_critical(self):
        r = qc.generar(out_path=self.out)
        self.assertEqual(r["estado_global"], "critical")


if __name__ == "__main__":
    unittest.main()
