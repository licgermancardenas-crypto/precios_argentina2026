"""
Tests de pipeline/imagenes.py — derivación de miniaturas y ruteo de CDNs.

Son reglas de string puras (no pegan a la red): lo que se verifica es que la
URL que se le pide a cada CDN sea la correcta, no que la CDN responda.
"""

import unittest

from pipeline.imagenes import como_data_uri, miniatura, requiere_proxy


class TestMiniatura(unittest.TestCase):

    def test_coto_pide_la_carpeta_medium(self):
        u = "https://static.cotodigital3.com.ar/sitios/fotos/large/00014000/00014076.jpg"
        self.assertEqual(
            miniatura(u),
            "https://static.cotodigital3.com.ar/sitios/fotos/medium/00014000/00014076.jpg",
        )

    def test_vtex_inserta_el_tamano_en_el_id(self):
        u = "https://jumboargentina.vteximg.com.br/arquivos/ids/427751/Aceite.jpg?v=636495154762100000"
        self.assertEqual(
            miniatura(u, 200),
            "https://jumboargentina.vteximg.com.br/arquivos/ids/427751-200-200/Aceite.jpg?v=636495154762100000",
        )

    def test_vtex_respeta_el_tamano_pedido(self):
        u = "https://ardiaprod.vteximg.com.br/arquivos/ids/339807/Aceite.jpg"
        self.assertIn("/arquivos/ids/339807-80-80/", miniatura(u, 80))

    def test_vtex_no_toca_otros_numeros_de_la_url(self):
        """El -W-H va sólo en el id, no en cualquier número que aparezca después."""
        u = "https://carrefourar.vteximg.com.br/arquivos/ids/884093/7790272001029_02.jpg?v=639159347212200000"
        out = miniatura(u, 200)
        self.assertIn("/ids/884093-200-200/", out)
        self.assertIn("7790272001029_02.jpg", out)   # el EAN del nombre queda intacto
        self.assertEqual(out.count("-200-200"), 1)

    def test_cdn_desconocida_devuelve_el_original(self):
        """Ante un formato inesperado: peor rendimiento, nunca una imagen rota."""
        u = "https://otra-cadena.example/fotos/leche.jpg"
        self.assertEqual(miniatura(u), u)

    def test_none_no_explota(self):
        self.assertIsNone(miniatura(None))


class TestRuteoDeCDN(unittest.TestCase):
    """
    Coto manda Content-Type webp con bytes jpeg y Chrome la bloquea por ORB,
    así que esas fotos van por el servidor. Las VTEX se enlazan directo.
    """

    def test_coto_requiere_proxy(self):
        self.assertTrue(requiere_proxy("https://static.cotodigital3.com.ar/sitios/fotos/medium/a/b.jpg"))

    def test_vtex_se_enlaza_directo(self):
        for host in ("jumboargentina", "ardiaprod", "carrefourar"):
            self.assertFalse(requiere_proxy(f"https://{host}.vteximg.com.br/arquivos/ids/1/x.jpg"))

    def test_sin_url_no_requiere_proxy(self):
        self.assertFalse(requiere_proxy(None))
        self.assertFalse(requiere_proxy(""))

    def test_descarga_fallida_devuelve_none(self):
        """Una foto es decorativa: nunca puede tumbar el dashboard."""
        self.assertIsNone(como_data_uri("https://localhost:1/no-existe.jpg", timeout=1))


if __name__ == "__main__":
    unittest.main()
