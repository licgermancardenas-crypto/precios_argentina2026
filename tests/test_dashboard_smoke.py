"""
Smoke test del dashboard: lo ejecuta de punta a punta contra los datos publicados
reales (data/public) y verifica que no lance ninguna excepción.

Se prueban los DOS entrypoints, y eso es lo importante:

  * dashboard/app.py   — el que usa Streamlit Cloud (main module del deploy).
    Al correrlo directo, sys.path[0] es dashboard/ y la raíz del repo NO queda
    importable. Un `import pipeline` sin el bootstrap de sys.path explota acá
    con ModuleNotFoundError... y anda perfecto por el otro entrypoint. Testear
    solo streamlit_app.py dejó pasar exactamente ese bug hasta producción.

  * streamlit_app.py   — el shim de la raíz, para correrlo local.

Streamlit en "bare mode" (sin servidor) ejecuta el script entero —incluidos
todos los tabs— y propaga las excepciones, que es justo lo que queremos.
"""

import subprocess
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# (ruta, cómo se ejecuta) — la primera réplica el deploy de Streamlit Cloud.
ENTRYPOINTS = [
    RAIZ / "dashboard" / "app.py",
    RAIZ / "streamlit_app.py",
]


class TestDashboardSmoke(unittest.TestCase):
    def test_el_dashboard_corre_sin_excepciones(self):
        try:
            import streamlit  # noqa: F401
        except ImportError:
            self.skipTest("streamlit no instalado")

        for entrypoint in ENTRYPOINTS:
            with self.subTest(entrypoint=entrypoint.relative_to(RAIZ).as_posix()):
                proc = subprocess.run(
                    [sys.executable, str(entrypoint)],
                    cwd=RAIZ, capture_output=True, text=True, timeout=300,
                )
                salida = proc.stdout + proc.stderr
                self.assertEqual(
                    proc.returncode, 0,
                    f"el dashboard falló al renderizar:\n{salida[-3000:]}",
                )
                self.assertNotIn("Traceback (most recent call last)", salida)


if __name__ == "__main__":
    unittest.main()
