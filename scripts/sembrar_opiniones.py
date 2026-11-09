"""Siembra opiniones ficticias en datos/opiniones.json.

Cada opinión pasa por el MISMO analizar_opinion y el MISMO guardar_opinion que
usa la app: las clasificaciones las produce el modelo, no se escriben a mano.
Si al final falta una categoría, se ajusta el TEXTO de la opinión, no la etiqueta.

Uso (desde cualquier carpeta):  python scripts/sembrar_opiniones.py
Requiere OPENAI_API_KEY y OPENAI_MODEL en .env.

Es seguro repetirlo: el id de cada registro se deriva del jugador y el texto
(uuid5), así que guardar_opinion ignora los que ya existen.
"""

import sys
import uuid
from collections import Counter
from pathlib import Path

# Permite importar los módulos del proyecto aunque se ejecute desde otra carpeta.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import almacenamiento as alm  # noqa: E402
import analisis as an  # noqa: E402

# 4 jugadores x 4 opiniones, pensadas para provocar las 4 categorías.
OPINIONES = {
    "j001": [  # Lionel Messi
        "Su visión de juego y sus pases son extraordinarios",
        "Su rendimiento en ese partido fue decepcionante y se vio desconectado",
        "Es un delantero argentino que usa la camiseta número diez",
        "Tiene una técnica admirable, pero su actitud cuando pierde me decepciona",
    ],
    "j002": [  # Cristiano Ronaldo
        "Su disciplina y su capacidad goleadora son admirables",
        "Se la pasa quejándose y su egoísmo perjudica al equipo",
        "Es un futbolista portugués que ha jugado en varios países",
        "Es un goleador implacable, aunque su ego a veces incomoda a sus compañeros",
    ],
    "j013": [  # Luis Díaz
        "Su velocidad y su desborde por la banda son geniales",
        "Falló todas las ocasiones claras, fue un partido muy flojo",
        "Es un extremo colombiano que juega por la banda",
        "Su velocidad es espectacular, pero toma malas decisiones en el último pase",
    ],
    "j017": [  # Diego Maradona
        "Su talento y su creatividad con el balón fueron únicos",
        "Sus polémicas fuera de la cancha me parecen lamentables",
        "Fue un futbolista argentino que vistió la camiseta número diez",
        "Dentro de la cancha era un genio, pero su comportamiento fuera de ella me decepciona",
    ],
}


def sembrar(analizar=an.analizar_opinion, cadena=None, ruta=alm.RUTA_OPINIONES,
            opiniones=OPINIONES, jugadores=None):
    """Devuelve el conteo de sentimientos de lo procesado. Los parámetros
    inyectables permiten probar la función sin API ni tocar datos reales."""
    jugadores = {j["id"]: j for j in (jugadores or alm.cargar_jugadores())}
    modelo = an.nombre_modelo()
    conteo = Counter()
    for jugador_id, textos in opiniones.items():
        jugador = jugadores[jugador_id]
        for texto in textos:
            analisis = analizar(jugador, texto, cadena)
            if not analisis.es_pertinente:
                print(f"  [no pertinente, omitida] {texto!r}")
                continue
            registro = alm.crear_registro(
                jugador, texto, analisis, modelo, version_prompt=an.VERSION_PROMPT,
                registro_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"tribuna-global/{jugador_id}/{texto}")),
            )
            nuevo = alm.guardar_opinion(ruta, registro)
            conteo[analisis.sentimiento] += 1
            print(f"  {'+' if nuevo else '='} {jugador['nombre']:<20} {analisis.sentimiento:<9} {texto}")
    return conteo


def main():
    try:
        cadena = an.construir_cadena()
    except an.ErrorAPI as e:
        print(f"No se puede sembrar sin la API: {e}\nConfigura .env (ver .env.example) y repite.")
        return 2
    print("Sembrando opiniones (+ nueva, = ya existía):")
    try:
        conteo = sembrar(cadena=cadena)
    except an.ErrorAnalisis as e:
        print(f"Error al clasificar: {e}")
        return 1
    except alm.ErrorTribuna as e:
        print(f"Error de almacenamiento: {e}")
        return 1

    faltan = [s for s in alm.SENTIMIENTOS if conteo[s] == 0]
    print(f"\nResumen: {dict(conteo)}")
    if faltan:
        print(f"Faltan categorías: {faltan}. Ajusta el TEXTO de las opiniones en OPINIONES "
              "(no la etiqueta) y vuelve a ejecutar.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
