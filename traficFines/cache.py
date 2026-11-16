"""Módulo cache: guarda en disco lo descargado para no repetir descargas."""

import hashlib
import shutil
import time
from pathlib import Path

import requests

CACHE_DIR = Path.home() / ".my_cache"
MS_PER_DAY = 24 * 60 * 60 * 1000


class CacheError(Exception):
    """Error del módulo cache."""


class Cache:
    """Guarda ficheros de texto en una subcarpeta de CACHE_DIR."""

    def __init__(self, app_name: str, obsolescence: int = 7) -> None:
        """app_name es la subcarpeta y obsolescence los días de validez."""
        if not isinstance(app_name, str) or not app_name.strip():
            raise CacheError("app_name debe ser un texto no vacío")
        if not isinstance(obsolescence, int) or obsolescence < 0:
            raise CacheError("obsolescence debe ser un entero >= 0")

        # privados, solo se leen con las property
        self._app_name = app_name
        self._obsolescence = obsolescence
        self._cache_dir = str(CACHE_DIR / app_name)

        try:
            Path(self._cache_dir).mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise CacheError(f"No se puede crear {self._cache_dir}") from error

    @property
    def app_name(self) -> str:
        """Nombre de la aplicación."""
        return self._app_name

    @property
    def cache_dir(self) -> str:
        """Ruta de la carpeta de la caché."""
        return self._cache_dir

    @property
    def obsolescence(self) -> int:
        """Días que valen los datos."""
        return self._obsolescence

    def _path(self, name: str) -> Path:
        """Ruta del fichero name."""
        return Path(self._cache_dir) / name

    def set(self, name: str, data: str) -> None:
        """Guarda data con el nombre name."""
        if not isinstance(data, str):
            raise CacheError("data debe ser un str")
        try:
            self._path(name).write_text(data, encoding="utf-8")
        except OSError as error:
            raise CacheError(f"No se puede guardar {name}") from error

    def exists(self, name: str) -> bool:
        """True si existe el fichero name."""
        return self._path(name).is_file()

    def load(self, name: str) -> str:
        """Devuelve lo guardado con el nombre name."""
        # no uso self.exists porque en CacheURL haria otra vez el hash
        if not self._path(name).is_file():
            raise CacheError(f"No hay datos con el nombre {name}")
        return self._path(name).read_text(encoding="utf-8")

    def how_old(self, name: str) -> float:
        """Edad del fichero name en milisegundos."""
        if not self._path(name).is_file():
            raise CacheError(f"No hay datos con el nombre {name}")
        modified = self._path(name).stat().st_mtime
        return (time.time() - modified) * 1000

    def delete(self, name: str) -> None:
        """Borra el fichero name, si no existe no pasa nada."""
        self._path(name).unlink(missing_ok=True)

    def clear(self) -> None:
        """Borra todo lo de la caché."""
        shutil.rmtree(self._cache_dir, ignore_errors=True)
        Path(self._cache_dir).mkdir(parents=True, exist_ok=True)


class CacheURL(Cache):
    """Caché para urls, el nombre del fichero es el md5 de la url."""

    @staticmethod
    def _hash(url: str, **kwargs) -> str:
        """md5 de la url con los parámetros."""
        key = url + str(sorted(kwargs.items()))
        return hashlib.md5(key.encode("utf-8")).hexdigest()

    @staticmethod
    def _encoding(content: bytes) -> str:
        """utf-8 si se puede leer así, si no latin1."""
        # los csv de multas vienen en latin1, las paginas en utf-8
        try:
            content.decode("utf-8")
            return "utf-8"
        except UnicodeDecodeError:
            return "latin1"

    def get(self, url: str, **kwargs) -> str:
        """Devuelve el texto de la url, de la caché o descargándolo."""
        max_age = self.obsolescence * MS_PER_DAY

        # si ya esta y no ha caducado lo leemos de la cache
        if self.exists(url, **kwargs):
            if self.how_old(url, **kwargs) <= max_age:
                return self.load(url, **kwargs)

        try:
            response = requests.get(url, **kwargs)
        except requests.RequestException as error:
            raise CacheError(f"Error al acceder a {url}") from error
        if response.status_code != 200:
            raise CacheError(f"{url} devuelve {response.status_code}")

        response.encoding = self._encoding(response.content)
        self.set(url, response.text, **kwargs)
        return response.text

    # estos reciben la url y llaman al padre con el hash
    def set(self, url: str, data: str, **kwargs) -> None:
        """Guarda data con el hash de la url."""
        super().set(self._hash(url, **kwargs), data)

    def exists(self, url: str, **kwargs) -> bool:
        """True si la url está guardada."""
        return super().exists(self._hash(url, **kwargs))

    def load(self, url: str, **kwargs) -> str:
        """Texto guardado de la url."""
        return super().load(self._hash(url, **kwargs))

    def how_old(self, name: str, **kwargs) -> float:
        """Edad en milisegundos de la url name."""
        return super().how_old(self._hash(name, **kwargs))

    def delete(self, name: str, **kwargs) -> None:
        """Borra la url name de la caché."""
        super().delete(self._hash(name, **kwargs))


# Modulo cache. La clase Cache guarda ficheros de texto en una carpeta
# dentro de ~/.my_cache (una subcarpeta por aplicacion) y permite
# guardarlos, leerlos, ver su edad en milisegundos, borrarlos o vaciar
# toda la cache. CacheURL hereda de Cache y sirve para urls: el nombre
# del fichero es el md5 de la url, y get solo descarga si no esta
# guardado o si ha pasado mas tiempo que obsolescence. clear() no se
# redefine porque se hereda de Cache. Cualquier error lanza CacheError.