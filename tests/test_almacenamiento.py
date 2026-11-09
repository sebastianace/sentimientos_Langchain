import json
import os
from types import SimpleNamespace

import pytest

import almacenamiento as alm

MESSI = {"id": "j001", "nombre": "Lionel Messi", "pais": "Argentina"}
LUIS = {"id": "j013", "nombre": "Luis Díaz", "pais": "Colombia"}


def registro(jugador=MESSI, texto="Su visión de juego es extraordinaria",
             sentimiento="positivo", **kw):
    analisis = SimpleNamespace(sentimiento=sentimiento, razon="Razón de prueba.")
    return alm.crear_registro(jugador, texto, analisis, "modelo-x",
                              version_prompt="1.0", **kw)


# ---------------- catálogo ----------------
def test_catalogo_real_es_valido():
    assert len(alm.cargar_jugadores()) == 20


def test_catalogo_con_ids_repetidos(tmp_path):
    ruta = tmp_path / "j.json"
    ruta.write_text(json.dumps({"version": 1, "jugadores": [
        {"id": "j1", "nombre": "A", "pais": "X"},
        {"id": "j1", "nombre": "B", "pais": "Y"}]}), encoding="utf-8")
    with pytest.raises(alm.ErrorCatalogo, match="repetido"):
        alm.cargar_jugadores(ruta)


def test_catalogo_inexistente_o_danado(tmp_path):
    with pytest.raises(alm.ErrorCatalogo):
        alm.cargar_jugadores(tmp_path / "no_existe.json")
    mala = tmp_path / "mala.json"
    mala.write_text("{no es json", encoding="utf-8")
    with pytest.raises(alm.ErrorCatalogo):
        alm.cargar_jugadores(mala)


# ---------------- cargar_opiniones ----------------
def test_archivo_inexistente_devuelve_estructura_vacia(tmp_path):
    ruta = tmp_path / "opiniones.json"
    assert alm.cargar_opiniones(ruta) == {"version": 1, "opiniones": []}
    assert not ruta.exists()  # cargar no crea el archivo


def test_json_danado_lanza_error_y_se_conserva(tmp_path):
    ruta = tmp_path / "opiniones.json"
    ruta.write_text("{ esto no es json", encoding="utf-8")
    with pytest.raises(alm.ErrorArchivoOpiniones):
        alm.cargar_opiniones(ruta)
    # guardar sobre un archivo dañado tampoco lo sobrescribe
    with pytest.raises(alm.ErrorArchivoOpiniones):
        alm.guardar_opinion(ruta, registro())
    assert ruta.read_text(encoding="utf-8") == "{ esto no es json"


@pytest.mark.parametrize("contenido", ['[]', '{"version": 2, "opiniones": []}',
                                       '{"version": 1, "opiniones": {}}'])
def test_esquema_inesperado(tmp_path, contenido):
    ruta = tmp_path / "opiniones.json"
    ruta.write_text(contenido, encoding="utf-8")
    with pytest.raises(alm.ErrorArchivoOpiniones):
        alm.cargar_opiniones(ruta)
    assert ruta.read_text(encoding="utf-8") == contenido


# ---------------- guardar_opinion ----------------
def test_guardar_crea_archivo_y_no_pierde_previos(tmp_path):
    ruta = tmp_path / "opiniones.json"
    r1, r2 = registro(), registro(LUIS, "Gran velocidad", "positivo")
    assert alm.guardar_opinion(ruta, r1) is True
    assert alm.guardar_opinion(ruta, r2) is True
    ids = [r["id"] for r in alm.cargar_opiniones(ruta)["opiniones"]]
    assert ids == [r1["id"], r2["id"]]


def test_mismo_id_no_se_duplica(tmp_path):
    ruta = tmp_path / "opiniones.json"
    r = registro()
    assert alm.guardar_opinion(ruta, r) is True
    assert alm.guardar_opinion(ruta, r) is False  # reintento
    assert len(alm.cargar_opiniones(ruta)["opiniones"]) == 1


def test_mismo_texto_enviado_dos_veces_son_dos_registros(tmp_path):
    ruta = tmp_path / "opiniones.json"
    alm.guardar_opinion(ruta, registro())
    alm.guardar_opinion(ruta, registro())  # UUID distinto, mismo texto
    assert len(alm.cargar_opiniones(ruta)["opiniones"]) == 2


def test_formato_utf8_sin_escapes_e_indentacion(tmp_path):
    ruta = tmp_path / "opiniones.json"
    alm.guardar_opinion(ruta, registro(LUIS, "Qué velocidad, ñandú"))
    texto = ruta.read_text(encoding="utf-8")
    assert "Luis Díaz" in texto and "\\u" not in texto
    assert "\n  " in texto  # indentado


def test_registro_incompleto_o_sentimiento_invalido(tmp_path):
    ruta = tmp_path / "opiniones.json"
    r = registro()
    del r["razon"]
    with pytest.raises(ValueError):
        alm.guardar_opinion(ruta, r)
    with pytest.raises(ValueError):
        alm.guardar_opinion(ruta, registro(sentimiento="genial"))
    assert not ruta.exists()


def test_fallo_de_escritura_sube_excepcion_y_conserva_archivo(tmp_path, monkeypatch):
    ruta = tmp_path / "opiniones.json"
    alm.guardar_opinion(ruta, registro())
    antes = ruta.read_text(encoding="utf-8")

    def falla(*a, **k):
        raise PermissionError("sin permisos")
    monkeypatch.setattr(os, "replace", falla)

    with pytest.raises(alm.ErrorEscritura):
        alm.guardar_opinion(ruta, registro(LUIS, "otra"))
    assert ruta.read_text(encoding="utf-8") == antes
    assert list(tmp_path.glob("*.tmp")) == []  # no quedan temporales


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="los permisos de carpeta no aplican")
def test_destino_sin_permisos(tmp_path):
    carpeta = tmp_path / "ro"
    carpeta.mkdir()
    carpeta.chmod(0o500)
    try:
        with pytest.raises(alm.ErrorEscritura):
            alm.guardar_opinion(carpeta / "opiniones.json", registro())
    finally:
        carpeta.chmod(0o700)


# ---------------- consultar_opiniones ----------------
@pytest.fixture
def muestra():
    return [
        registro(MESSI, "a", "positivo"),
        registro(MESSI, "b", "negativo"),
        registro(LUIS, "c", "positivo"),
        registro(LUIS, "d", "mixto"),
    ]


def test_consulta_sin_filtros_devuelve_todo(muestra):
    assert len(alm.consultar_opiniones(muestra)) == 4


def test_consulta_por_jugador_y_por_sentimiento(muestra):
    assert len(alm.consultar_opiniones(muestra, jugador_id="j001")) == 2
    assert len(alm.consultar_opiniones(muestra, sentimiento="positivo")) == 2


def test_consulta_filtros_combinados(muestra):
    res = alm.consultar_opiniones(muestra, "j013", "mixto")
    assert [r["opinion_original"] for r in res] == ["d"]
    assert alm.consultar_opiniones(muestra, "j001", "mixto") == []


def test_consulta_no_modifica_la_entrada(muestra):
    copia = list(muestra)
    alm.consultar_opiniones(muestra, "j001", "positivo")
    assert muestra == copia
