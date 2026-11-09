"""Prueba del flujo del script semilla con un analizador falso (sin API)."""
import sys
from pathlib import Path

import almacenamiento as alm
import analisis as an

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sembrar_opiniones as sem  # noqa: E402


def falso(jugador, texto, cadena=None):
    # Solo para el test: reparte categorías por posición para comprobar el flujo.
    sent = ("positivo", "negativo", "neutro", "mixto")[len(texto) % 4]
    return an.AnalisisOpinion(es_pertinente=True, sentimiento=sent, razon="Prueba.")


def test_sembrar_guarda_16_y_es_idempotente(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "modelo-de-prueba")
    ruta = tmp_path / "opiniones.json"
    sem.sembrar(analizar=falso, ruta=ruta)
    sem.sembrar(analizar=falso, ruta=ruta)  # repetir no duplica
    regs = alm.cargar_opiniones(ruta)["opiniones"]
    assert len(regs) == 16
    assert len({r["jugador_id"] for r in regs}) == 4
