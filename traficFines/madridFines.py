"""Módulo madridFines: descarga, limpia y analiza las multas de Madrid."""

import io

import matplotlib.pyplot as plt
import pandas as pd
import requests
from bs4 import BeautifulSoup

from traficFines.cache import CacheError, CacheURL

RAIZ = "https://datos.madrid.es/"
URL_DESCARGAS = RAIZ + "dataset/210104-0-multas-circulacion-detalle/downloads"

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# solo usamos datos desde junio 2017
PRIMER_MES = (2017, 6)

TEXT_COLS = ["CALIFICACION", "LUGAR", "DESCUENTO", "DENUNCIANTE",
             "HECHO-BOL"]
NUM_COLS = ["MES", "ANIO", "HORA", "IMP_BOL", "PUNTOS", "VEL_LIMITE",
            "VEL_CIRCULA", "COORDENADA-X", "COORDENADA-Y"]


class MadridError(Exception):
    """Error del módulo madridFines."""


def get_url(year: int, month: int) -> str:
    """Devuelve la url del csv de multas de ese mes."""
    if not isinstance(year, int) or not isinstance(month, int):
        raise MadridError("year y month deben ser enteros")
    if month < 1 or month > 12:
        raise MadridError("month debe estar entre 1 y 12")
    if (year, month) < PRIMER_MES:
        raise MadridError("Solo hay datos desde junio de 2017")

    try:
        response = requests.get(URL_DESCARGAS)
    except requests.RequestException as error:
        raise MadridError("No se puede acceder al portal") from error
    if response.status_code != 200:
        raise MadridError(f"El portal devuelve {response.status_code}")

    soup = BeautifulSoup(response.text, "html.parser")
    title = f"Detalle. {MESES[month - 1]} {year}"
    resources = soup.find_all("div", class_="tracked-resource-item")

    # cada mes tiene "Detalle" y "Agrupadas-excluidas", queremos Detalle
    # (el titulo de noviembre 2019 lleva un espacio delante)
    def is_detail(div) -> bool:
        link = div.find("a", title=lambda t: t and t.strip() == title)
        return link is not None

    def csv_link(div):
        return div.find("a", href=lambda h: h and h.endswith(".csv"))

    found = next(filter(lambda div: is_detail(div) and csv_link(div),
                        resources), None)
    if found is None:
        raise MadridError(f"No hay datos de {MESES[month - 1]} {year}")

    return RAIZ + csv_link(found)["href"].lstrip("/")


class MadridFines:
    """Carga multas de uno o varios meses y saca resúmenes y gráficos."""

    def __init__(self, app_name: str = "madrid_fines",
                 obsolescence: int = 7) -> None:
        """app_name y obsolescence son para la CacheURL."""
        self._cacheurl = CacheURL(app_name, obsolescence)
        self._data = pd.DataFrame()
        self._loaded = []

    @property
    def cacheurl(self) -> CacheURL:
        """CacheURL que se usa para descargar."""
        return self._cacheurl

    # data y loaded devuelven copias para que no se cambien desde fuera
    @property
    def data(self) -> pd.DataFrame:
        """Copia de los datos cargados."""
        return self._data.copy()

    @property
    def loaded(self) -> list[tuple[int, int]]:
        """Copia de los meses cargados, tuplas (month, year)."""
        return list(self._loaded)

    @staticmethod
    def load(year: int, month: int, cacheurl: CacheURL) -> pd.DataFrame:
        """DataFrame con las multas del mes, sin limpiar."""
        url = get_url(year, month)
        try:
            text = cacheurl.get(url)
        except CacheError as error:
            raise MadridError(f"No se pueden descargar {url}") from error
        return pd.read_csv(io.StringIO(text), sep=";", low_memory=False)

    def clean_cache(self) -> None:
        """Borra la caché (clear viene de Cache)."""
        self._cacheurl.clear()

    @staticmethod
    def _clean_name(col: str) -> str:
        """Limpia el nombre de una columna."""
        # en mayo 2019 las columnas son COORDENADA_X y COORDENADA_Y
        return col.strip(" \x00").replace("COORDENADA_", "COORDENADA-")

    @staticmethod
    def _strip_text(col: pd.Series) -> pd.Series:
        """Quita espacios si la columna es de texto."""
        if pd.api.types.is_string_dtype(col):
            return col.str.strip()
        return col

    @staticmethod
    def _to_number(col: pd.Series) -> pd.Series:
        """Pasa la columna a número, lo que no se puede queda NaN."""
        return pd.to_numeric(col.astype(str).str.strip(" \x00"),
                             errors="coerce")

    @staticmethod
    def clean(df: pd.DataFrame) -> None:
        """Limpia df como en la Etapa 1 y añade la columna fecha."""
        df.columns = df.columns.map(MadridFines._clean_name)

        text_cols = df.columns.intersection(TEXT_COLS)
        df[text_cols] = df[text_cols].apply(MadridFines._strip_text)

        num_cols = df.columns.intersection(NUM_COLS)
        df[num_cols] = df[num_cols].apply(MadridFines._to_number)

        # HORA viene como 10.42 -> 10:42
        hour = df["HORA"].fillna(0).astype(int)
        minute = ((df["HORA"].fillna(0) - hour) * 100).round().astype(int)

        date_parts = pd.DataFrame({
            "year": df["ANIO"],
            "month": df["MES"],
            "day": 1,
            "hour": hour,
            "minute": minute,
        })
        df["fecha"] = pd.to_datetime(date_parts, errors="coerce")

    def add(self, year: int, month: int | None = None) -> None:
        """Añade un mes a data. Si month es None añade todo el año."""
        if month is None:
            months = filter(lambda m: (year, m) >= PRIMER_MES, range(1, 13))
            list(map(lambda m: self._add_if_available(year, m), months))
            return

        if (month, year) in self._loaded:
            return

        df = self.load(year, month, self._cacheurl)
        self.clean(df)
        self._data = pd.concat([self._data, df], ignore_index=True)
        self._loaded.append((month, year))

    def _add_if_available(self, year: int, month: int) -> None:
        """Como add pero si el mes no está publicado lo salta."""
        try:
            self.add(year, month)
        except MadridError:
            pass

    def _check_data(self) -> None:
        """MadridError si no hay datos cargados."""
        if self._data.empty:
            raise MadridError("No hay datos, usa antes el método add")

    def fines_hour(self, fig_name: str) -> None:
        """Gráfico de multas por hora (una línea por mes) en fig_name."""
        self._check_data()

        hours = self._data["fecha"].dt.hour.rename("HORA")
        table = (self._data.groupby([hours, "ANIO", "MES"]).size()
                 .unstack(["ANIO", "MES"], fill_value=0))
        table.columns = table.columns.map(lambda col: f"{col[0]}-{col[1]}")

        ax = table.plot(marker="o", figsize=(10, 5))
        ax.set_title("Sanciones por hora")
        ax.set_xlabel("Hora")
        ax.set_ylabel("Número de sanciones")
        plt.savefig(fig_name)
        plt.close()

    def fines_calification(self) -> pd.DataFrame:
        """Número de multas por calificación, mes y año."""
        self._check_data()
        return (self._data.groupby(["MES", "ANIO", "CALIFICACION"]).size()
                .unstack("CALIFICACION", fill_value=0))

    def total_payment(self) -> pd.DataFrame:
        """Importe total máximo y mínimo por mes y año."""
        self._check_data()

        # max: nadie paga con descuento, min: todos pagan con el 50%
        importe = self._data["IMP_BOL"]
        con_descuento = self._data["DESCUENTO"] == "SI"
        importe_min = importe.where(~con_descuento, importe / 2)

        payments = pd.DataFrame({
            "MES": self._data["MES"],
            "ANIO": self._data["ANIO"],
            "max": importe,
            "min": importe_min,
        })
        return payments.groupby(["MES", "ANIO"]).sum()


# Modulo madridFines. get_url hace scraping de la pagina de descargas del
# portal con requests y BeautifulSoup y devuelve la url del csv "Detalle"
# del mes pedido (MadridError si no existe o es antes de junio 2017).
# MadridFines usa una CacheURL para descargar los csv, los limpia con
# clean (lo mismo que en la Etapa 1, tambien para el formato de mayo 2019)
# y los va juntando en data, apuntando los meses en loaded. Con los datos
# cargados se puede sacar el grafico de multas por hora (fines_hour), las
# multas por calificacion (fines_calification) y el importe maximo y
# minimo recaudado (total_payment).