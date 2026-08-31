"""
Tests de los guards de sanidad de precios — el corazón de la corrección del pipeline.

Cubren los dos bugs reales que inflaban el índice:
  - Coto: precio_promo corrupto (>lista) desde la API Constructor.io
  - Jumbo: ListPrice VTEX corrupto (~80x el precio real)

Ejecutar: pytest  (o: python -m unittest)
"""

import unittest

from scraper.coto import _extraer_precio_promo
from scraper.vtex import _parsear_producto, _precio_regular


class TestPromoGuardCoto(unittest.TestCase):
    """_extraer_precio_promo descarta cualquier promo que no sea 0 < promo < lista."""

    def _descuento(self, precio_str):
        return [{"discountText": "25%Dto", "discountPrice": precio_str}]

    def test_promo_valido_menor_a_lista(self):
        # Promo real: $800 sobre lista $1000
        promo = _extraer_precio_promo(self._descuento("$800"), precio_lista=1000.0)
        self.assertEqual(promo, 800.0)

    def test_promo_absurdo_mayor_a_lista_se_descarta(self):
        # El bug histórico: discountPrice inflado (1.407.680 vs lista 17.596)
        promo = _extraer_precio_promo(self._descuento("$1.407.680"), precio_lista=17596.0)
        self.assertIsNone(promo)

    def test_promo_igual_a_lista_se_descarta(self):
        promo = _extraer_precio_promo(self._descuento("$1000"), precio_lista=1000.0)
        self.assertIsNone(promo)

    def test_sin_descuento_directo(self):
        # Promo condicional (no "Dto") se ignora
        promo = _extraer_precio_promo(
            [{"discountText": "2do al 70%", "discountPrice": "$500"}], precio_lista=1000.0
        )
        self.assertIsNone(promo)

    def test_lista_none_no_rompe(self):
        self.assertIsNone(_extraer_precio_promo(self._descuento("$800"), precio_lista=None))


def _producto_vtex(list_price, price, price_without_discount=None):
    """Arma un producto VTEX mínimo con la estructura que lee _parsear_producto."""
    offer = {"ListPrice": list_price, "Price": price}
    if price_without_discount is not None:
        offer["PriceWithoutDiscount"] = price_without_discount
    return {
        "productName": "Producto Test",
        "brand": "MarcaTest",
        "link": "http://x",
        "items": [{
            "ean": "7790000000001",
            "itemId": "123",
            "name": "1 Lt",
            "unitMultiplier": 1.0,
            "measurementUnit": "un",
            "images": [],
            "sellers": [{"commertialOffer": offer}],
        }],
    }


class TestPrecioGuardVTEX(unittest.TestCase):
    """_parsear_producto usa ListPrice salvo cuando es implausible (>3x Price)."""

    def _parse(self, **kw):
        return _parsear_producto(_producto_vtex(**kw), "almacen", "ref")

    def test_dia_sin_promo(self):
        # Día: Price == ListPrice == PriceWithoutDiscount
        p = self._parse(list_price=2805.0, price=2805.0, price_without_discount=2805.0)
        self.assertEqual(p["precio_lista"], 2805.0)
        self.assertIsNone(p["precio_promo"])

    def test_carrefour_lista_valida_con_promo(self):
        # Carrefour: ListPrice 2670 (regular) > Price 2099 (promo) — ListPrice se conserva
        p = self._parse(list_price=2670.0, price=2099.0, price_without_discount=2099.0)
        self.assertEqual(p["precio_lista"], 2670.0)
        self.assertEqual(p["precio_promo"], 2099.0)

    def test_jumbo_listprice_corrupto_cae_a_price(self):
        # Jumbo: ListPrice 231322 basura (>3x), Price 2799 real -> usa PriceWithoutDiscount
        p = self._parse(list_price=231322.0, price=2799.0, price_without_discount=2799.0)
        self.assertEqual(p["precio_lista"], 2799.0)
        self.assertIsNone(p["precio_promo"])

    def test_sin_price_retorna_none(self):
        self.assertIsNone(self._parse(list_price=1000.0, price=None))


if __name__ == "__main__":
    unittest.main()


class TestPrecioRegularVTEX(unittest.TestCase):
    """
    _precio_regular NO decodifica el ListPrice de Jumbo, a propósito.

    Jumbo lo publica neto de IVA y en centavos (de ahí el ×80 que parecía
    corrupción), pero la alícuota varía por producto —21% general, 10,5% en
    canasta básica— así que decodificar todo al 21% inventa un descuento del
    8,68% en los productos al 10,5%. Se probó en producción: 21 promos falsas
    por día sobre 45 productos. Los 39 productos sondeados decodifican exacto al
    precio efectivo con su alícuota: Jumbo no tiene promos que estemos perdiendo.
    """

    def test_el_listprice_neto_de_iva_no_se_toma_como_regular(self):
        # 231322/100*1.21 == 2799: mismo precio, otra unidad. No hay descuento.
        oferta = {"ListPrice": 231322.0, "PriceWithoutDiscount": 2799.0}
        self.assertAlmostEqual(_precio_regular(oferta, 2799.0), 2799.0, places=2)

    def test_no_inventa_promo_con_alicuota_reducida(self):
        # Harina Morixe, IVA 10,5%: 104072/100*1.105 == 1150. Decodificar al 21%
        # daba 1259,27 y un "descuento" del 8,68% inexistente.
        oferta = {"ListPrice": 104072.0, "PriceWithoutDiscount": 1150.0}
        self.assertAlmostEqual(_precio_regular(oferta, 1150.0), 1150.0, places=2)

    def test_no_deja_ruido_de_punto_flotante_en_el_precio(self):
        # La decodificación dejaba precio_lista en 7463.0017 contra un promo de
        # 7463.0, y eso se publicaba como una promo del 0,00002%.
        oferta = {"ListPrice": 616777.0, "PriceWithoutDiscount": 7463.0}
        self.assertEqual(_precio_regular(oferta, 7463.0), 7463.0)

    def test_jumbo_con_listprice_ya_en_pesos(self):
        oferta = {"ListPrice": 112.39, "PriceWithoutDiscount": 112.39}
        self.assertAlmostEqual(_precio_regular(oferta, 112.39), 112.39, places=2)

    def test_dia_detecta_la_promo_real(self):
        # Donde el ListPrice viene en pesos, un valor mayor al efectivo sí es
        # descuento y hay que conservarlo.
        oferta = {"ListPrice": 4280.0, "PriceWithoutDiscount": 3200.0}
        self.assertAlmostEqual(_precio_regular(oferta, 3200.0), 4280.0, places=2)

    def test_sin_listprice_cae_a_price_without_discount(self):
        self.assertAlmostEqual(_precio_regular({"PriceWithoutDiscount": 500.0}, 500.0), 500.0)

    def test_sin_ninguna_lectura_creible_usa_el_efectivo(self):
        self.assertAlmostEqual(_precio_regular({"ListPrice": 7.0}, 900.0), 900.0)

    def test_descarta_un_regular_desmedido(self):
        # 10x el efectivo es un error de unidad, no una rebaja del 90%.
        self.assertAlmostEqual(_precio_regular({"ListPrice": 9000.0}, 900.0), 900.0)

    def test_jumbo_no_genera_promo(self):
        prod = _producto_vtex(list_price=104072.0, price=1150.0, price_without_discount=1150.0)
        parseado = _parsear_producto(prod, "almacen", "ref")
        self.assertAlmostEqual(parseado["precio_lista"], 1150.0, places=2)
        self.assertIsNone(parseado["precio_promo"])
