"""
Smoke test del dashboard: ejecuta `streamlit_app.py` de punta a punta contra los
datos publicados reales (data/public) y verifica que no lance ninguna excepción.

Existe porque el resto de la suite testea el pipeline, no el render: un bug que
solo aparece cuando la serie crece (ej. una fila de pandas usada como booleano,
que recién explota al haber ≥30 días de historia) pasaba todos los tests y
tiraba abajo el deploy. Este test corre el mismo camino que Streamlit Cloud.

Streamlit en "bare mode" (sin servidor) ejecuta el script completo —incluidos
todos los tabs— y propaga las excepciones, que es justo lo que queremos.
"""

import subprocess
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ENTRYPOINT = RAIZ / "streamlit_app.py"


class TestDashboardSmoke(unittest.TestCase):
    def test_el_dashboard_corre_sin_excepciones(self):
        try:
            import streamlit  # noqa: F401
        except ImportError:
            self.skipTest("streamlit no instalado")

        proc = subprocess.run(
            [sys.executable, str(ENTRYPOINT)],
            cwd=RAIZ, capture_output=True, text=True, timeout=300,
        )

        # El traceback puede venir por stderr o stdout según cómo falle el script.
        salida = proc.stdout + proc.stderr
        self.assertEqual(
            proc.returncode, 0,
            f"el dashboard falló al renderizar:\n{salida[-3000:]}",
        )
        self.assertNotIn("Traceback (most recent call last)", salida)


if __name__ == "__main__":
    unittest.main()
