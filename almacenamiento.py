"""Lectura, escritura y consulta de los archivos JSON de Tribuna Global.

Este módulo NO sabe nada de Streamlit ni del modelo de lenguaje: solo maneja
archivos y listas de diccionarios. Así se puede probar sin interfaz y sin API.
"""

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Rutas calculadas desde la ubicación de este archivo, no desde el directorio
# actual: la app funciona igual si se lanza `streamlit run` desde otra carpeta.
RAIZ = Path(__file__).resolve().parent
RUTA_JUGADORES = RAIZ / "datos" / "jugadores.json"
RUTA_OPINIONES = RAIZ / "datos" / "opiniones.json"

SENTIMIENTOS = ("positivo", "negativo", "neutro", "mixto")

# Campos que debe tener todo registro persistido (sección 7 del enunciado).
CAMPOS_REGISTRO = (
    "id", "fecha_utc", "jugador_id", "jugador_nombre", "opinion_original",
    "sentimiento", "razon", "modelo", "version_prompt",
)


# --------------------------------------------------------------------------
# Excepciones propias: la interfaz las usa para mostrar un mensaje distinto
# según el tipo de fallo (catálogo, archivo de opiniones o escritura).
# --------------------------------------------------------------------------
class ErrorTribuna(Exception):
    """Base común de los errores de almacenamiento."""


class ErrorCatalogo(ErrorTribuna):
    """El catálogo de jugadores no existe, está dañado o tiene ids repetidos."""


class ErrorArchivoOpiniones(ErrorTribuna):
    """El archivo de opiniones existe pero es JSON inválido o tiene otro esquema."""


class ErrorEscritura(ErrorTribuna):
    """No se pudo escribir el archivo de opiniones."""


# --------------------------------------------------------------------------
# Lectura
# --------------------------------------------------------------------------
def cargar_jugadores(ruta=RUTA_JUGADORES):
    """Lee y valida el catálogo. Devuelve la lista de jugadores.

    Se comprueba la estructura y que no haya identificadores repetidos, porque
    el id es el valor interno del selector y la clave de cada registro.
    """
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ErrorCatalogo(f"No se encontró el catálogo: {ruta}") from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ErrorCatalogo(f"El catálogo no es un JSON válido: {e}") from e

    if not isinstance(datos, dict) or not isinstance(datos.get("jugadores"), list):
        raise ErrorCatalogo("El catálogo debe ser un objeto con la lista 'jugadores'.")

    vistos = set()
    for j in datos["jugadores"]:
        if not isinstance(j, dict) or not all(
            isinstance(j.get(k), str) and j.get(k).strip() for k in ("id", "nombre", "pais")
        ):
            raise ErrorCatalogo(f"Jugador con estructura inválida: {j!r}")
        if j["id"] in vistos:
            raise ErrorCatalogo(f"Identificador de jugador repetido: {j['id']}")
        vistos.add(j["id"])
    return datos["jugadores"]


def _estructura_vacia():
    return {"version": 1, "opiniones": []}


def cargar_opiniones(ruta=RUTA_OPINIONES):
    """Lee el diccionario persistente {'version', 'opiniones'}.

    - Si el archivo no existe: devuelve la estructura vacía (sin crearlo).
    - Si existe pero está dañado o tiene otro esquema: lanza ErrorArchivoOpiniones.
      Jamás se reemplaza por una lista vacía, porque se perderían datos reales.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        return _estructura_vacia()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ErrorArchivoOpiniones(f"El archivo de opiniones no es un JSON válido: {e}") from e

    if (
        not isinstance(datos, dict)
        or datos.get("version") != 1
        or not isinstance(datos.get("opiniones"), list)
    ):
        raise ErrorArchivoOpiniones(
            "Esquema inesperado: se esperaba {'version': 1, 'opiniones': [...]}."
        )
    if not all(isinstance(r, dict) for r in datos["opiniones"]):
        raise ErrorArchivoOpiniones("Todas las opiniones deben ser objetos JSON.")
    return datos


# --------------------------------------------------------------------------
# Creación y guardado de registros
# --------------------------------------------------------------------------
def crear_registro(jugador, texto, analisis, modelo, *, version_prompt,
                   registro_id=None, fecha_utc=None):
    """Arma el registro final. El programa pone id, fecha, jugador y metadatos;
    el modelo solo aporta sentimiento y razón (sección 7).

    `registro_id` permite que la interfaz genere el UUID ANTES de analizar y lo
    reutilice en los reintentos (así guardar es idempotente).
    """
    return {
        "id": registro_id or str(uuid.uuid4()),
        "fecha_utc": fecha_utc or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "jugador_id": jugador["id"],
        "jugador_nombre": jugador["nombre"],
        # Se guarda el texto original (ya sin espacios exteriores), nunca una versión del modelo.
        "opinion_original": texto,
        "sentimiento": analisis.sentimiento,
        "razon": analisis.razon,
        "modelo": modelo,
        "version_prompt": version_prompt,
    }


def _validar_registro(registro):
    faltan = [c for c in CAMPOS_REGISTRO if c not in registro]
    if faltan:
        raise ValueError(f"Al registro le faltan campos: {faltan}")
    if registro["sentimiento"] not in SENTIMIENTOS:
        raise ValueError(f"Sentimiento inválido: {registro['sentimiento']!r}")


def guardar_opinion(ruta, registro):
    """Añade `registro` al archivo sin perder los anteriores.

    Devuelve True si se escribió y False si ya existía un registro con ese id
    (idempotencia: un reintento o rerun no duplica). Cualquier fallo de lectura
    o escritura sube como excepción; nunca se silencia, para que la interfaz no
    confirme un guardado que no ocurrió.
    """
    _validar_registro(registro)
    ruta = Path(ruta)
    # Lee el estado actual. Si el archivo está dañado, lanza ErrorArchivoOpiniones
    # y NO se toca el archivo.
    datos = cargar_opiniones(ruta)

    if any(r.get("id") == registro["id"] for r in datos["opiniones"]):
        return False

    datos["opiniones"].append(registro)

    # Escritura atómica: se escribe un temporal en el MISMO directorio (mismo
    # sistema de archivos) y se reemplaza con os.replace. Si el programa se
    # interrumpe a mitad, el archivo original queda intacto, no a medias.
    tmp_nombre = None
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=ruta.parent, prefix=ruta.name + ".",
            suffix=".tmp", delete=False,
        ) as tmp:
            tmp_nombre = tmp.name
            json.dump(datos, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())  # fuerza el volcado a disco antes del reemplazo
        os.replace(tmp_nombre, ruta)
    except OSError as e:
        if tmp_nombre and os.path.exists(tmp_nombre):
            try:
                os.unlink(tmp_nombre)
            except OSError:
                pass
        raise ErrorEscritura(f"No se pudo escribir {ruta}: {e}") from e
    return True


# --------------------------------------------------------------------------
# Consulta (función pura: no toca disco ni modelo)
# --------------------------------------------------------------------------
def consultar_opiniones(registros, jugador_id=None, sentimiento=None):
    """Filtra la lista de registros. `None` significa 'todos'.

    Los filtros se combinan con AND. Tabla y recuentos de la interfaz usan el
    resultado de esta misma llamada, así siempre coinciden.
    """
    return [
        r for r in registros
        if (jugador_id is None or r.get("jugador_id") == jugador_id)
        and (sentimiento is None or r.get("sentimiento") == sentimiento)
    ]
