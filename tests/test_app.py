"""Pruebas de la interfaz con streamlit.testing (AppTest). No usan la API real:
`analizar_opinion` se sustituye por un modelo falso."""
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import almacenamiento as alm
import analisis as an

APP = str(Path(__file__).resolve().parent.parent / "app.py")


class Falso:
    """Sustituye a analizar_opinion y registra cuántas veces se llamó."""

    def __init__(self, resultado=None, error=None):
        self.resultado, self.error, self.llamadas = resultado, error, []

    def __call__(self, jugador, texto, cadena=None):
        self.llamadas.append((jugador["id"], texto))
        if self.error:
            raise self.error
        return self.resultado


def positivo():
    return an.AnalisisOpinion(es_pertinente=True, sentimiento="positivo", razon="Admira su juego.")


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    ruta = tmp_path / "opiniones.json"
    monkeypatch.setattr(alm, "RUTA_OPINIONES", ruta)
    monkeypatch.setenv("OPENAI_MODEL", "modelo-de-prueba")
    return ruta


def registros(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))["opiniones"]


def abrir():
    at = AppTest.from_file(APP, default_timeout=15)
    at.run()
    assert not at.exception
    return at


def enviar(at, texto):
    at.chat_input[0].set_value(texto).run()
    assert not at.exception
    return at


def test_guardado_muestra_confirmacion_solo_tras_escribir(entorno, monkeypatch):
    monkeypatch.setattr(an, "analizar_opinion", Falso(positivo()))
    at = enviar(abrir(), "Su visión de juego es extraordinaria")
    assert [s.value for s in at.success] == ["Guardado"]
    r = registros(entorno)
    assert len(r) == 1 and r[0]["jugador_id"] == "j001" and r[0]["sentimiento"] == "positivo"
    assert r[0]["version_prompt"] == an.VERSION_PROMPT and r[0]["modelo"] == "modelo-de-prueba"


@pytest.mark.parametrize("texto", ["     ", "abc", "x" * 1001])
def test_entrada_invalida_no_llama_al_modelo_ni_guarda(entorno, monkeypatch, texto):
    falso = Falso(positivo())
    monkeypatch.setattr(an, "analizar_opinion", falso)
    at = enviar(abrir(), texto)
    assert falso.llamadas == [] and not entorno.exists()
    assert any("Entrada no válida" in e.value for e in at.error)
    assert not at.success


def test_no_pertinente_es_aviso_y_no_se_guarda(entorno, monkeypatch):
    nulo = an.AnalisisOpinion(es_pertinente=False, sentimiento=None, razon="Habla de geografía.")
    monkeypatch.setattr(an, "analizar_opinion", Falso(nulo))
    at = enviar(abrir(), "La capital de Francia es París")
    assert len(at.warning) == 1 and not at.success and not entorno.exists()


def test_error_de_api_no_guarda_y_el_reintento_no_duplica(entorno, monkeypatch):
    falso = Falso(error=an.ErrorAPI("sin red"))
    monkeypatch.setattr(an, "analizar_opinion", falso)
    at = enviar(abrir(), "Su rendimiento fue decepcionante")
    assert any("Error de clasificación" in e.value for e in at.error)
    assert not entorno.exists() and not at.success
    # La opinión sigue visible y hay botón para reintentar.
    assert any("decepcionante" in m.value for m in at.chat_message[0].markdown)
    id_envio = at.session_state["pendiente"]["id"]

    falso.error, falso.resultado = None, positivo()  # la API "se recupera"
    [b for b in at.button if "Reintentar" in b.label][0].click().run()
    r = registros(entorno)
    assert len(r) == 1 and r[0]["id"] == id_envio  # mismo UUID del envío original
    assert at.session_state["pendiente"] is None

    # Otro rerun cualquiera (p. ej. cambiar el selector) no vuelve a guardar.
    at.sidebar.selectbox[0].select("j013").run()
    assert len(registros(entorno)) == 1


def test_fallo_de_escritura_no_muestra_guardado(entorno, monkeypatch):
    monkeypatch.setattr(an, "analizar_opinion", Falso(positivo()))

    def falla(*a, **k):
        raise alm.ErrorEscritura("sin permisos")
    monkeypatch.setattr(alm, "guardar_opinion", falla)
    at = enviar(abrir(), "Su visión de juego es extraordinaria")
    assert not at.success
    assert any("NO se guardó" in e.value for e in at.error)
    assert at.session_state["pendiente"] is not None  # se puede reintentar sin reclasificar


def test_cambio_de_jugador_conserva_cada_registro(entorno, monkeypatch):
    monkeypatch.setattr(an, "analizar_opinion", Falso(positivo()))
    at = enviar(abrir(), "Su visión de juego es extraordinaria")
    at.sidebar.selectbox[0].select("j013").run()
    enviar(at, "Gran velocidad y desborde")
    assert [(r["jugador_id"], r["jugador_nombre"]) for r in registros(entorno)] == [
        ("j001", "Lionel Messi"), ("j013", "Luis Díaz")]


def test_nueva_conversacion_limpia_chat_y_conserva_archivo(entorno, monkeypatch):
    monkeypatch.setattr(an, "analizar_opinion", Falso(positivo()))
    at = enviar(abrir(), "Su visión de juego es extraordinaria")
    antes = entorno.read_text(encoding="utf-8")
    [b for b in at.sidebar.button if "Nueva conversación" in b.label][0].click().run()
    assert len(at.chat_message) == 0 and at.session_state["mensajes"] == []
    assert entorno.read_text(encoding="utf-8") == antes


def test_archivo_danado_detiene_la_app_sin_modificarlo(entorno):
    entorno.write_text("{ json roto", encoding="utf-8")
    at = AppTest.from_file(APP, default_timeout=15).run()
    assert not at.exception
    assert any("dañado" in e.value for e in at.error)
    assert len(at.chat_input) == 0  # st.stop() impidió dibujar el resto
    assert entorno.read_text(encoding="utf-8") == "{ json roto"


def test_consulta_filtra_sin_llamar_al_modelo_ni_escribir(entorno, monkeypatch):
    falso = Falso(positivo())
    monkeypatch.setattr(an, "analizar_opinion", falso)
    at = enviar(abrir(), "Su visión de juego es extraordinaria")
    at.sidebar.selectbox[0].select("j013").run()
    enviar(at, "Gran velocidad y desborde")
    llamadas = len(falso.llamadas)
    antes = entorno.read_text(encoding="utf-8")

    at.sidebar.radio[0].set_value("Consultar opiniones").run()
    assert not at.exception
    assert at.metric[0].value == "2"                       # total sin filtros
    at.selectbox[0].select("j013").run()                  # filtro por jugador
    assert at.metric[0].value == "1"
    at.selectbox[1].select("negativo").run()              # combinado: sin resultados
    assert len(at.info) == 1

    assert len(falso.llamadas) == llamadas                # no hubo llamadas al modelo
    assert entorno.read_text(encoding="utf-8") == antes   # no se escribió nada
