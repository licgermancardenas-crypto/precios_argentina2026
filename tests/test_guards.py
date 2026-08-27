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
    _precio_regular decodifica las dos codificaciones de ListPrice de VTEX.

    Jumbo publica ListPrice neto de IVA y en centavos (factor 82.645). Leerlo
    como corrupción y caer a PriceWithoutDiscount —que en Jumbo replica el
    precio efectivo— registraba el precio CON descuento como precio de lista,
    que es justo lo que el índice evita al no usar nunca el promo.
    """

    def test_jumbo_sin_promo_devuelve_el_efectivo(self):
        # ListPrice 231322 decodifica exacto al Price: no hay descuento.
        oferta = {"ListPrice": 231322.0, "PriceWithoutDiscount": 2799.0}
        self.assertAlmostEqual(_precio_regular(oferta, 2799.0), 2799.0, places=2)

    def test_jumbo_con_promo_recupera_el_regular(self):
        # Caso real, EAN 7790199000013: regular $1259,27 vendido a $1150.
        oferta = {"ListPrice": 104072.0, "PriceWithoutDiscount": 1150.0}
        self.assertAlmostEqual(_precio_regular(oferta, 1150.0), 1259.27, places=2)

    def test_jumbo_con_listprice_ya_en_pesos(self):
        # Mismo retailer, otra codificación. Decodificar acá daría $1,36.
        oferta = {"ListPrice": 112.39, "PriceWithoutDiscount": 112.39}
        self.assertAlmostEqual(_precio_regular(oferta, 112.39), 112.39, places=2)

    def test_dia_conserva_la_lectura_directa(self):
        # No debe haber regresión en las cadenas que ya funcionaban.
        oferta = {"ListPrice": 4280.0, "PriceWithoutDiscount": 3200.0}
        self.assertAlmostEqual(_precio_regular(oferta, 3200.0), 4280.0, places=2)

    def test_sin_listprice_cae_a_price_without_discount(self):
        self.assertAlmostEqual(_precio_regular({"PriceWithoutDiscount": 500.0}, 500.0), 500.0)

    def test_sin_ninguna_lectura_creible_usa_el_efectivo(self):
        # Antes que inventar un regular, se asume que no hay descuento.
        self.assertAlmostEqual(_precio_regular({"ListPrice": 7.0}, 900.0), 900.0)

    def test_descarta_un_regular_desmedido(self):
        # 10x el efectivo es un error de unidad, no una rebaja del 90%.
        self.assertAlmostEqual(_precio_regular({"ListPrice": 9000.0}, 900.0), 900.0)

    def test_el_promo_sale_de_la_diferencia(self):
        # Integración con el parser: la promo oculta de Jumbo aparece.
        prod = _producto_vtex(list_price=104072.0, price=1150.0, price_without_discount=1150.0)
        parseado = _parsear_producto(prod, "almacen", "ref")
        self.assertAlmostEqual(parseado["precio_lista"], 1259.27, places=2)
        self.assertAlmostEqual(parseado["precio_promo"], 1150.0, places=2)
