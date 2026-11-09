import pytest
from pydantic import ValidationError

import analisis as an

MESSI = {"id": "j001", "nombre": "Lionel Messi", "pais": "Argentina"}


class CadenaFalsa:
    """Modelo falso: devuelve lo configurado y cuenta las llamadas."""

    def __init__(self, resultado=None, error=None):
        self.resultado, self.error, self.llamadas = resultado, error, []

    def invoke(self, entrada):
        self.llamadas.append(entrada)
        if self.error:
            raise self.error
        return self.resultado


def ok(sentimiento="positivo", razon="Expresa admiración."):
    return an.AnalisisOpinion(es_pertinente=True, sentimiento=sentimiento, razon=razon)


# ---------- coherencia pertinencia/sentimiento ----------
def test_pertinente_sin_sentimiento_es_invalido():
    with pytest.raises(ValidationError):
        an.AnalisisOpinion(es_pertinente=True, sentimiento=None, razon="x")


def test_no_pertinente_con_sentimiento_es_invalido():
    with pytest.raises(ValidationError):
        an.AnalisisOpinion(es_pertinente=False, sentimiento="neutro", razon="x")


def test_no_pertinente_con_none_es_valido():
    a = an.AnalisisOpinion(es_pertinente=False, sentimiento=None, razon="Habla de geografía.")
    assert a.sentimiento is None


def test_categoria_fuera_de_las_cuatro_es_invalida():
    with pytest.raises(ValidationError):
        an.AnalisisOpinion(es_pertinente=True, sentimiento="genial", razon="x")


def test_razon_vacia_o_muy_larga_es_invalida():
    for razon in ("", "x" * 301):
        with pytest.raises(ValidationError):
            an.AnalisisOpinion(es_pertinente=True, sentimiento="positivo", razon=razon)


# ---------- entrada ----------
@pytest.mark.parametrize("texto", ["", "     ", None, "  ab  ", "x" * 1001])
def test_entrada_invalida_no_llama_al_modelo(texto):
    cadena = CadenaFalsa(resultado=ok())
    with pytest.raises(an.ErrorEntrada):
        an.analizar_opinion(MESSI, texto, cadena)
    assert cadena.llamadas == []


def test_limites_de_longitud_tras_strip():
    assert an.validar_texto_opinion("  12345  ") == "12345"
    assert len(an.validar_texto_opinion("x" * 1000)) == 1000


# ---------- análisis con modelo falso ----------
def test_analisis_exitoso_envia_solo_jugador_y_opinion_actual():
    cadena = CadenaFalsa(resultado=ok())
    res = an.analizar_opinion(MESSI, "  Su visión de juego es extraordinaria  ", cadena)
    assert res.sentimiento == "positivo"
    # Solo se envían estas dos claves: sin historial.
    assert cadena.llamadas == [
        {"jugador": "Lionel Messi", "opinion": "Su visión de juego es extraordinaria"}
    ]


def test_no_pertinente_se_devuelve_sin_sentimiento():
    nulo = an.AnalisisOpinion(es_pertinente=False, sentimiento=None, razon="Tema ajeno.")
    res = an.analizar_opinion(MESSI, "La capital de Francia es París", CadenaFalsa(nulo))
    assert res.es_pertinente is False and res.sentimiento is None


def test_error_de_api_no_se_convierte_en_neutro():
    cadena = CadenaFalsa(error=ConnectionError("sin red"))
    with pytest.raises(an.ErrorAPI):
        an.analizar_opinion(MESSI, "Un comentario válido", cadena)


def test_respuesta_incoherente_en_dict_lanza_error_validacion():
    cadena = CadenaFalsa(resultado={"es_pertinente": True, "sentimiento": None, "razon": "x"})
    with pytest.raises(an.ErrorValidacion):
        an.analizar_opinion(MESSI, "Un comentario válido", cadena)


def test_respuesta_vacia_lanza_error_validacion():
    with pytest.raises(an.ErrorValidacion):
        an.analizar_opinion(MESSI, "Un comentario válido", CadenaFalsa(resultado=None))


def test_validation_error_del_parser_es_error_validacion():
    try:
        an.AnalisisOpinion(es_pertinente=True, sentimiento="x", razon="y")
    except ValidationError as e:
        error = e
    with pytest.raises(an.ErrorValidacion):
        an.analizar_opinion(MESSI, "Un comentario válido", CadenaFalsa(error=error))


# ---------- configuración ----------
def test_sin_api_key_o_modelo_lanza_error_api(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(an.ErrorAPI, match="OPENAI_API_KEY"):
        an.construir_cadena()
    monkeypatch.setenv("OPENAI_API_KEY", "clave-falsa")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(an.ErrorAPI, match="OPENAI_MODEL"):
        an.construir_cadena()


def test_cadena_se_construye_sin_red(monkeypatch):
    """Construir la cadena no llama a la API (solo arma el prompt y el modelo)."""
    monkeypatch.setenv("OPENAI_API_KEY", "clave-falsa")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    for metodo in ("json_schema", "function_calling"):
        monkeypatch.setenv("OPENAI_STRUCTURED_METHOD", metodo)
        assert an.construir_cadena() is not None


def test_prompt_tiene_dos_roles_y_las_cuatro_categorias():
    msgs = an.PROMPT.format_messages(jugador="Lionel Messi", opinion="texto {con llaves}")
    assert [m.type for m in msgs] == ["system", "human"]
    for cat in ("positivo", "negativo", "neutro", "mixto"):
        assert cat in msgs[0].content
    assert "Lionel Messi" in msgs[1].content and "{con llaves}" in msgs[1].content
