# traficFines

Paquete de Python para descargar, limpiar y analizar las multas de
circulación del Ayuntamiento de Madrid, a partir del
[portal de datos abiertos](https://datos.madrid.es/dataset/210104-0-multas-circulacion-detalle/downloads).

Trabajo final de *Programación avanzada en Python* (Máster Big Data & Data
Engineering, UCM).

## Contenido de la entrega

```
├── traficFines/                 proyecto del paquete
│   ├── pyproject.toml           configuración del paquete
│   ├── README.md                este fichero
│   ├── traficFines/             paquete que se distribuye
│   │   ├── __init__.py
│   │   ├── cache.py             CacheError, Cache, CacheURL
│   │   └── madridFines.py       RAIZ, MadridError, get_url, MadridFines
│   └── tests/                   tests (no se incluyen en el paquete)
│       ├── test_cache.py
│       ├── test_madridFines.py
│       └── data/                datos de prueba y carpeta de la caché
├── traficfines-0.1.0-py3-none-any.whl
├── enunciado.ipynb              Etapa 1: análisis exploratorio
└── ejemplos.ipynb               ejemplos de uso del paquete
```

## Instalación

Hace falta Python 3.10 o superior. Desde la carpeta donde está el `.whl`:

```bash
pip install traficfines-0.1.0-py3-none-any.whl
```

Se instalan también las dependencias: `pandas`, `requests`,
`beautifulsoup4` y `matplotlib`.

## Uso

```python
from traficFines import MadridFines

multas = MadridFines("multas", 7)    # nombre de la app y días de validez
multas.add(2024, 12)                  # diciembre de 2024
multas.add(2019, 5)                   # mayo de 2019

print(multas.loaded)                  # [(12, 2024), (5, 2019)]
print(multas.fines_calification())    # multas por calificación
print(multas.total_payment())         # importe máximo y mínimo
multas.fines_hour("evolucion_multas.png")

multas.clean_cache()                  # borra los ficheros descargados
```

- `add(year)` sin mes añade todos los meses publicados de ese año.
- Solo hay datos desde junio de 2017. Si un mes no existe se lanza
  `MadridError`.
- Los csv descargados se guardan en `~/.my_cache/<app_name>` y no se
  vuelven a descargar hasta que pasan `obsolescence` días.

La caché también se puede usar sola:

```python
from traficFines import CacheURL

cache = CacheURL("mi_app", 3)
texto = cache.get("https://datos.madrid.es/")
```

El cuaderno `ejemplos.ipynb` tiene más ejemplos, incluidas las excepciones.

## Tests

Los tests no acceden a internet (se simula con `unittest.mock`) y la caché
se guarda en `tests/data/cache`. Desde la carpeta del proyecto:

```bash
pip install pytest pytest-cov
python -m pytest --cov=traficFines
```

## Generar el `.whl`

Desde la carpeta del proyecto:

```bash
pip install build
python -m build --wheel
```

El fichero se crea en la carpeta `dist/`.

## Declaración de uso de herramientas de IA

He usado Claude (IA) como apoyo para escribir y corregir parte del código y los tests. He revisado, ejecutado y comprobado todo con los datos reales.