"""
Tests del módulo traficFines.madridFines

No se accede a internet: requests.get se sustituye por fake_get, que
devuelve los ficheros de tests/data (un trozo de la página de descargas
y dos csv pequeños). La caché se guarda en tests/data/cache.
"""

import shutil
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
import requests

from traficFines import cache
from traficFines.cache import CacheURL
from traficFines.madridFines import RAIZ, MadridError, MadridFines, get_url

DATA_DIR = Path(__file__).parent / "data"
TEST_CACHE_DIR = DATA_DIR / "cache"

HTML = (DATA_DIR / "downloads.html").read_bytes()
CSV_2024_12 = (DATA_DIR / "multas_2024_12.csv").read_bytes()
CSV_2019_05 = (DATA_DIR / "multas_2019_05.csv").read_bytes()

# id del recurso "Detalle" de cada mes en la página
ID_2024_12 = "210104-15-"
ID_2019_05 = "210104-91-"
ID_2019_11 = "210104-284-"


def fake_response(content: bytes, status: int = 200) -> requests.Response:
    """Crea una respuesta de requests falsa."""
    response = requests.Response()
    response.status_code = status
    response._content = content
    return response


def fake_get(url: str, **kwargs) -> requests.Response:
    """Sustituye a requests.get: devuelve los ficheros de tests/data."""
    if url.endswith("downloads"):
        return fake_response(HTML)
    if ID_2024_12 in url:
        return fake_response(CSV_2024_12)
    if ID_2019_05 in url:
        return fake_response(CSV_2019_05)
    return fake_response(b"", status=404)


class MadridTestCase(unittest.TestCase):
    """Base: simula internet y usa tests/data/cache como caché."""

    def setUp(self):
        patchers = [
            mock.patch.object(cache, "CACHE_DIR", TEST_CACHE_DIR),
            mock.patch("requests.get", side_effect=fake_get),
        ]
        self.get = [p.start() for p in patchers][1]
        list(map(lambda p: self.addCleanup(p.stop), patchers))

    def tearDown(self):
        shutil.rmtree(TEST_CACHE_DIR, ignore_errors=True)


class TestGetUrl(MadridTestCase):

    def test_diciembre_2024(self):
        url = get_url(2024, 12)
        self.assertTrue(url.startswith(RAIZ))
        self.assertTrue(url.endswith(".csv"))
        self.assertIn(ID_2024_12, url)

    def test_coge_detalle_y_no_agrupadas(self):
        # mayo 2019 tiene dos csv: Detalle (91) y Agrupadas-excluidas (92)
        self.assertIn(ID_2019_05, get_url(2019, 5))

    def test_titulo_con_espacio_delante(self):
        # en la página el título es " Detalle. Noviembre 2019"
        self.assertIn(ID_2019_11, get_url(2019, 11))

    def test_mes_no_publicado(self):
        with self.assertRaises(MadridError):
            get_url(2025, 3)

    def test_antes_de_junio_2017(self):
        with self.assertRaises(MadridError):
            get_url(2017, 5)

    def test_mes_incorrecto(self):
        with self.assertRaises(MadridError):
            get_url(2024, 0)
        with self.assertRaises(MadridError):
            get_url(2024, 13)

    def test_tipos_incorrectos(self):
        with self.assertRaises(MadridError):
            get_url("2024", 12)
        with self.assertRaises(MadridError):
            get_url(2024, 12.0)

    def test_portal_status_error(self):
        self.get.side_effect = None
        self.get.return_value = fake_response(b"", status=500)
        with self.assertRaises(MadridError):
            get_url(2024, 12)

    def test_portal_sin_conexion(self):
        self.get.side_effect = requests.ConnectionError("sin internet")
        with self.assertRaises(MadridError):
            get_url(2024, 12)


class TestLoadYClean(MadridTestCase):

    def test_load(self):
        df = MadridFines.load(2024, 12, CacheURL("test"))
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 4)

    def test_load_error_descarga(self):
        # la página tiene el enlace pero el csv da 404
        with self.assertRaises(MadridError):
            MadridFines.load(2019, 11, CacheURL("test"))

    def test_clean_formato_nuevo(self):
        df = MadridFines.load(2024, 12, CacheURL("test"))
        resultado = MadridFines.clean(df)
        self.assertIsNone(resultado)

        columnas = ["CALIFICACION", "LUGAR", "MES", "ANIO", "HORA",
                    "IMP_BOL", "DESCUENTO", "PUNTOS", "DENUNCIANTE",
                    "HECHO-BOL", "VEL_LIMITE", "VEL_CIRCULA",
                    "COORDENADA-X", "COORDENADA-Y", "fecha"]
        self.assertEqual(list(df.columns), columnas)

        self.assertEqual(set(df["CALIFICACION"]),
                         {"LEVE", "GRAVE", "MUY GRAVE"})
        self.assertEqual(df["HECHO-BOL"].iloc[0],
                         "ESTACIONAR CON AUTORIZACIÓN NO VÁLIDA.")

        self.assertTrue(pd.api.types.is_float_dtype(df["VEL_CIRCULA"]))
        self.assertEqual(df["VEL_CIRCULA"].notna().sum(), 1)
        self.assertEqual(df["COORDENADA-Y"].iloc[2], 4475000.2)

        self.assertEqual(df["fecha"].iloc[0],
                         pd.Timestamp("2024-12-01 20:23:00"))

    def test_clean_formato_viejo(self):
        # en mayo 2019 las columnas son COORDENADA_X y COORDENADA_Y
        df = MadridFines.load(2019, 5, CacheURL("test"))
        self.assertIn("COORDENADA_X", df.columns)
        MadridFines.clean(df)
        self.assertIn("COORDENADA-X", df.columns)
        self.assertEqual(df["COORDENADA-X"].iloc[2], 440000.0)
        self.assertEqual(df["fecha"].iloc[0],
                         pd.Timestamp("2019-05-01 10:42:00"))


    def test_clean_columna_texto_vacia(self):
        # si una columna de texto viene vacía pandas la lee como número
        df = MadridFines.load(2019, 5, CacheURL("test"))
        df["DENUNCIANTE"] = float("nan")
        MadridFines.clean(df)
        self.assertTrue(df["DENUNCIANTE"].isna().all())


class TestMadridFines(MadridTestCase):

    def test_init(self):
        fines = MadridFines("test", 3)
        self.assertIsInstance(fines.cacheurl, CacheURL)
        self.assertEqual(fines.cacheurl.obsolescence, 3)
        self.assertTrue(fines.data.empty)
        self.assertEqual(fines.loaded, [])

    def test_add(self):
        fines = MadridFines("test")
        fines.add(2024, 12)
        self.assertEqual(fines.loaded, [(12, 2024)])
        self.assertEqual(len(fines.data), 4)

    def test_add_no_duplica(self):
        fines = MadridFines("test")
        fines.add(2024, 12)
        fines.add(2024, 12)
        self.assertEqual(fines.loaded, [(12, 2024)])
        self.assertEqual(len(fines.data), 4)

    def test_add_varios_meses(self):
        fines = MadridFines("test")
        fines.add(2024, 12)
        fines.add(2019, 5)
        self.assertEqual(fines.loaded, [(12, 2024), (5, 2019)])
        self.assertEqual(len(fines.data), 7)

    def test_add_year_completo(self):
        # en los datos de prueba de 2019 solo se puede descargar mayo
        fines = MadridFines("test")
        fines.add(2019)
        self.assertEqual(fines.loaded, [(5, 2019)])

    def test_add_mes_no_publicado(self):
        fines = MadridFines("test")
        with self.assertRaises(MadridError):
            fines.add(2025, 3)
        self.assertEqual(fines.loaded, [])

    def test_data_y_loaded_no_se_cambian_desde_fuera(self):
        fines = MadridFines("test")
        fines.add(2024, 12)
        fines.loaded.append((1, 2000))
        del fines.data["MES"]
        self.assertEqual(fines.loaded, [(12, 2024)])
        self.assertIn("MES", fines.data.columns)
        with self.assertRaises(AttributeError):
            fines.data = pd.DataFrame()
        with self.assertRaises(AttributeError):
            fines.loaded = []

    def test_add_usa_la_cache(self):
        fines = MadridFines("test")
        fines.add(2024, 12)
        otra = MadridFines("test")
        otra.add(2024, 12)
        csv_calls = [c for c in self.get.call_args_list
                     if ID_2024_12 in c.args[0]]
        self.assertEqual(len(csv_calls), 1)

    def test_clean_cache(self):
        fines = MadridFines("test")
        fines.add(2024, 12)
        url = get_url(2024, 12)
        self.assertTrue(fines.cacheurl.exists(url))
        fines.clean_cache()
        self.assertFalse(fines.cacheurl.exists(url))

    def test_sin_datos(self):
        fines = MadridFines("test")
        with self.assertRaises(MadridError):
            fines.fines_calification()
        with self.assertRaises(MadridError):
            fines.total_payment()
        with self.assertRaises(MadridError):
            fines.fines_hour(str(TEST_CACHE_DIR / "grafico.png"))

    def test_fines_calification(self):
        fines = MadridFines("test")
        fines.add(2024, 12)
        fines.add(2019, 5)
        result = fines.fines_calification()
        self.assertEqual(result.index.names, ["MES", "ANIO"])
        self.assertEqual(list(result.columns),
                         ["GRAVE", "LEVE", "MUY GRAVE"])
        self.assertEqual(result.loc[(12, 2024)].tolist(), [2, 1, 1])
        self.assertEqual(result.loc[(5, 2019)].tolist(), [2, 1, 0])

    def test_total_payment(self):
        fines = MadridFines("test")
        fines.add(2019, 5)
        result = fines.total_payment()
        # 90 (SI) + 200 (NO) + 100 (SI)
        self.assertEqual(result.loc[(5, 2019), "max"], 390)
        self.assertEqual(result.loc[(5, 2019), "min"], 45 + 200 + 50)

    def test_fines_hour(self):
        fines = MadridFines("test")
        fines.add(2024, 12)
        fines.add(2019, 5)
        fig_name = TEST_CACHE_DIR / "evolucion_multas.png"
        fines.fines_hour(str(fig_name))
        self.assertTrue(fig_name.is_file())
        self.assertGreater(fig_name.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()