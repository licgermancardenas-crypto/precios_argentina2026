"""
Tests de los guards de sanidad de precios — el corazón de la corrección del pipeline.

Cubren los dos bugs reales que inflaban el índice:
  - Coto: precio_promo corrupto (>lista) desde la API Constructor.io
  - Jumbo: ListPrice VTEX corrupto (~80x el precio real)

Ejecutar: pytest  (o: python -m unittest)
"""

import unittest

from scraper.config import DESCUENTO_MINIMO_PCT, es_promo_valida
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


class TestDescuentoMinimo(unittest.TestCase):
    """
    es_promo_valida corta los "descuentos" que son ruido numérico.

    El guard anterior era solo `0 < promo < lista`, que un promo de 7463.0
    contra una lista de 7463.0017 cumple. Así se publicaron 21 promos falsas por
    día durante 4 días sin que nada las marcara.
    """

    def test_rechaza_ruido_de_punto_flotante(self):
        # El caso real: descuento del 0,00002%.
        self.assertFalse(es_promo_valida(7463.0, 7463.0017))

    def test_acepta_una_promo_real_chica(self):
        # La más chica observada en producción: 6,5% en Día.
        self.assertTrue(es_promo_valida(3200.0, 3423.0))

    def test_acepta_una_promo_grande(self):
        self.assertTrue(es_promo_valida(3200.0, 4280.0))

    def test_el_umbral_es_inclusivo(self):
        lista = 1000.0
        justo = lista * (1 - DESCUENTO_MINIMO_PCT / 100)
        self.assertTrue(es_promo_valida(justo, lista))
        self.assertFalse(es_promo_valida(justo + 0.01, lista))

    def test_rechaza_promo_mayor_o_igual_a_la_lista(self):
        self.assertFalse(es_promo_valida(1200.0, 1000.0))
        self.assertFalse(es_promo_valida(1000.0, 1000.0))

    def test_rechaza_promo_no_positivo(self):
        self.assertFalse(es_promo_valida(0.0, 1000.0))
        self.assertFalse(es_promo_valida(-50.0, 1000.0))

    def test_tolera_nulos(self):
        self.assertFalse(es_promo_valida(None, 1000.0))
        self.assertFalse(es_promo_valida(500.0, None))


class TestCrudoPrecioArchivado(unittest.TestCase):
    """
    El snapshot archiva los campos de precio sin interpretar.

    Sin esto no se pudo auditar el ListPrice de Jumbo: el crudo guardaba solo el
    dict ya parseado y hubo que re-sondear la API en vivo, días después.
    """

    def test_el_parser_vtex_archiva_los_campos_de_precio(self):
        prod = _producto_vtex(list_price=104072.0, price=1150.0, price_without_discount=1150.0)
        crudo = _parsear_producto(prod, "almacen", "ref")["crudo_precio"]
        self.assertEqual(crudo["ListPrice"], 104072.0)
        self.assertEqual(crudo["Price"], 1150.0)

    def test_la_alicuota_se_deduce_del_snapshot(self):
        # Es la auditoría que antes exigía volver a la API: 1/1,105 = IVA 10,5%.
        prod = _producto_vtex(list_price=104072.0, price=1150.0, price_without_discount=1150.0)
        crudo = _parsear_producto(prod, "almacen", "ref")["crudo_precio"]
        self.assertAlmostEqual(crudo["ListPrice"] / 100 / crudo["Price"], 1 / 1.105, places=3)

    def test_no_archiva_tokens_de_request(self):
        # Cambian en cada llamada: ensuciarían el diff a diario sin aportar nada.
        prod = _producto_vtex(list_price=100.0, price=100.0)
        oferta = prod["items"][0]["sellers"][0]["commertialOffer"]
        oferta["PriceToken"] = "abc123"
        oferta["CacheVersionUsedToCallCheckout"] = "v9"
        crudo = _parsear_producto(prod, "almacen", "ref")["crudo_precio"]
        self.assertNotIn("PriceToken", crudo)
        self.assertNotIn("CacheVersionUsedToCallCheckout", crudo)
