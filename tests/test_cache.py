"""
Tests del módulo traficFines.cache

Las descargas de internet se simulan con unittest.mock y los ficheros de
la caché se guardan en tests/data/cache.
"""

import os
import shutil
import time
import unittest
from pathlib import Path
from unittest import mock

import requests

from traficFines import cache
from traficFines.cache import Cache, CacheError, CacheURL

DATA_DIR = Path(__file__).parent / "data"
TEST_CACHE_DIR = DATA_DIR / "cache"

URL = "https://datos.madrid.es/prueba.csv"


def fake_response(content: bytes, status: int = 200) -> requests.Response:
    """Crea una respuesta de requests falsa (sin ir a internet)."""
    response = requests.Response()
    response.status_code = status
    response._content = content
    return response


def make_old(path: Path, days: int) -> None:
    """Cambia la fecha del fichero para que parezca de hace days días."""
    old = time.time() - days * 24 * 60 * 60
    os.utime(path, (old, old))


class CacheTestCase(unittest.TestCase):
    """Base: la caché se guarda en tests/data/cache y se borra al final."""

    def setUp(self):
        patcher = mock.patch.object(cache, "CACHE_DIR", TEST_CACHE_DIR)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(TEST_CACHE_DIR, ignore_errors=True)


class TestCache(CacheTestCase):

    def test_init_crea_carpeta(self):
        c = Cache("app", 3)
        self.assertEqual(c.app_name, "app")
        self.assertEqual(c.obsolescence, 3)
        self.assertEqual(c.cache_dir, str(TEST_CACHE_DIR / "app"))
        self.assertTrue(Path(c.cache_dir).is_dir())

    def test_obsolescence_por_defecto(self):
        self.assertEqual(Cache("app").obsolescence, 7)

    def test_init_parametros_incorrectos(self):
        with self.assertRaises(CacheError):
            Cache("")
        with self.assertRaises(CacheError):
            Cache(123)
        with self.assertRaises(CacheError):
            Cache("app", -1)
        with self.assertRaises(CacheError):
            Cache("app", "7")

    def test_init_no_puede_crear_carpeta(self):
        with mock.patch.object(Path, "mkdir", side_effect=OSError):
            with self.assertRaises(CacheError):
                Cache("app")

    def test_atributos_solo_lectura(self):
        c = Cache("app")
        with self.assertRaises(AttributeError):
            c.app_name = "otra"
        with self.assertRaises(AttributeError):
            c.cache_dir = "/tmp"
        with self.assertRaises(AttributeError):
            c.obsolescence = 10

    def test_set_y_load(self):
        c = Cache("app")
        c.set("saludo", "hola ñ")
        self.assertTrue(c.exists("saludo"))
        self.assertEqual(c.load("saludo"), "hola ñ")

    def test_set_data_no_es_str(self):
        with self.assertRaises(CacheError):
            Cache("app").set("numero", 5)

    def test_set_no_puede_escribir(self):
        c = Cache("app")
        with mock.patch.object(Path, "write_text", side_effect=OSError):
            with self.assertRaises(CacheError):
                c.set("saludo", "hola")

    def test_exists_false(self):
        self.assertFalse(Cache("app").exists("no_existe"))

    def test_load_no_existe(self):
        with self.assertRaises(CacheError):
            Cache("app").load("no_existe")

    def test_how_old(self):
        c = Cache("app")
        c.set("saludo", "hola")
        self.assertLess(c.how_old("saludo"), 1000)

        make_old(Path(c.cache_dir) / "saludo", 2)
        dos_dias = 2 * 24 * 60 * 60 * 1000
        self.assertAlmostEqual(c.how_old("saludo"), dos_dias, delta=1000)

    def test_how_old_no_existe(self):
        with self.assertRaises(CacheError):
            Cache("app").how_old("no_existe")

    def test_delete(self):
        c = Cache("app")
        c.set("saludo", "hola")
        c.delete("saludo")
        self.assertFalse(c.exists("saludo"))
        # si no existe no da error
        c.delete("saludo")

    def test_clear(self):
        c = Cache("app")
        c.set("a", "1")
        c.set("b", "2")
        c.clear()
        self.assertEqual(os.listdir(c.cache_dir), [])

    def test_apps_separadas(self):
        a = Cache("app_a")
        b = Cache("app_b")
        a.set("dato", "a")
        self.assertFalse(b.exists("dato"))


class TestCacheURL(CacheTestCase):

    def test_get_descarga_y_guarda(self):
        response = fake_response("hola".encode("utf-8"))
        with mock.patch("requests.get", return_value=response) as get:
            c = CacheURL("web", 3)
            self.assertEqual(c.get(URL), "hola")
            get.assert_called_once_with(URL)
        self.assertTrue(c.exists(URL))
        self.assertEqual(c.load(URL), "hola")

    def test_get_usa_la_cache(self):
        response = fake_response(b"hola")
        with mock.patch("requests.get", return_value=response) as get:
            c = CacheURL("web", 3)
            c.get(URL)
            c.get(URL)
            self.assertEqual(get.call_count, 1)

    def test_get_descarga_otra_vez_si_caduca(self):
        with mock.patch("requests.get",
                        return_value=fake_response(b"viejo")) as get:
            c = CacheURL("web", 3)
            c.get(URL)
            hash_name = Path(c.cache_dir) / c._hash(URL)
            make_old(hash_name, 4)

            get.return_value = fake_response(b"nuevo")
            self.assertEqual(c.get(URL), "nuevo")
            self.assertEqual(get.call_count, 2)

    def test_get_no_caducado(self):
        with mock.patch("requests.get",
                        return_value=fake_response(b"hola")) as get:
            c = CacheURL("web", 3)
            c.get(URL)
            make_old(Path(c.cache_dir) / c._hash(URL), 2)
            c.get(URL)
            self.assertEqual(get.call_count, 1)

    def test_get_latin1(self):
        texto = "AUTORIZACIÓN NO VÁLIDA"
        response = fake_response(texto.encode("latin1"))
        with mock.patch("requests.get", return_value=response):
            self.assertEqual(CacheURL("web").get(URL), texto)

    def test_get_con_parametros(self):
        with mock.patch("requests.get",
                        return_value=fake_response(b"hola")) as get:
            c = CacheURL("web")
            c.get(URL, timeout=5)
            get.assert_called_once_with(URL, timeout=5)
        self.assertTrue(c.exists(URL, timeout=5))
        self.assertFalse(c.exists(URL))

    def test_get_status_error(self):
        response = fake_response(b"", status=404)
        with mock.patch("requests.get", return_value=response):
            with self.assertRaises(CacheError):
                CacheURL("web").get(URL)

    def test_get_error_conexion(self):
        error = requests.ConnectionError("sin internet")
        with mock.patch("requests.get", side_effect=error):
            with self.assertRaises(CacheError):
                CacheURL("web").get(URL)

    def test_nombre_es_hash(self):
        c = CacheURL("web")
        c.set(URL, "hola")
        nombre = os.listdir(c.cache_dir)[0]
        self.assertEqual(len(nombre), 32)
        self.assertNotIn("/", nombre)

    def test_how_old_y_delete(self):
        c = CacheURL("web")
        c.set(URL, "hola")
        self.assertLess(c.how_old(URL), 1000)
        c.delete(URL)
        self.assertFalse(c.exists(URL))
        with self.assertRaises(CacheError):
            c.load(URL)

    def test_clear_heredado(self):
        c = CacheURL("web")
        c.set(URL, "hola")
        c.clear()
        self.assertFalse(c.exists(URL))


if __name__ == "__main__":
    unittest.main()
