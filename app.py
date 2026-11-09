"""Tribuna Global: interfaz Streamlit.

Adaptación de intermedio/streamlit_chatbot2.py. Diferencias principales:
- Sin selector de personalidad ni temperatura: el clasificador es estable.
- No se envía historial al modelo: cada opinión se analiza de forma independiente.
- Sin streaming: se necesita el resultado estructurado completo (`invoke`).
- Las opiniones se guardan en disco (JSON), no solo en st.session_state.
"""

import json
import uuid

import streamlit as st

import almacenamiento as alm
import analisis as an

st.set_page_config(page_title="Tribuna Global", page_icon="⚽")
st.title("⚽ Tribuna Global")
st.caption(
    "Opiniones de aficionados sobre futbolistas. La clasificación describe lo que "
    "expresa el aficionado, no la calidad del jugador; las cifras solo reflejan "
    "las opiniones registradas en esta aplicación."
)

SENTIMIENTOS = alm.SENTIMIENTOS
ICONOS = {"positivo": "🟢", "negativo": "🔴", "neutro": "⚪", "mixto": "🟡"}


# --------------------------------------------------------------------------
# Carga inicial: si los datos están dañados se muestra el error y se detiene
# la app SIN modificar ningún archivo.
# --------------------------------------------------------------------------
try:
    JUGADORES = alm.cargar_jugadores()
except alm.ErrorCatalogo as e:
    st.error(f"Catálogo de jugadores inválido: {e}")
    st.stop()

try:
    alm.cargar_opiniones(alm.RUTA_OPINIONES)
except alm.ErrorArchivoOpiniones as e:
    st.error(
        f"El archivo de opiniones está dañado y no se modificará: {e}\n\n"
        "Corrígelo o restáuralo manualmente y vuelve a cargar la página."
    )
    st.stop()

JUGADOR_POR_ID = {j["id"]: j for j in JUGADORES}


def etiqueta_jugador(jugador_id):
    j = JUGADOR_POR_ID[jugador_id]
    return f"{j['nombre']} ({j['pais']})"


# --------------------------------------------------------------------------
# Estado de sesión.
#   mensajes : historial VISUAL del chat (se limpia con «Nueva conversación»).
#   pendiente: último envío que no terminó de guardarse (error de API/escritura).
#              Conserva el UUID del envío para que un reintento NO cree un
#              segundo registro (idempotencia, ver guardar_opinion).
# --------------------------------------------------------------------------
st.session_state.setdefault("mensajes", [])
st.session_state.setdefault("pendiente", None)


def procesar_envio(envio):
    """Clasifica y guarda un envío. Devuelve (mensaje_para_el_chat, terminado).

    `terminado` es False cuando hubo un fallo recuperable (se puede reintentar).
    Cada tipo de fallo (entrada, clasificación, almacenamiento) produce un
    mensaje distinto. La confirmación «Guardado» solo se devuelve después de
    que guardar_opinion terminó sin excepción.
    """
    jugador = envio["jugador"]

    # 1) Clasificación (se omite en un reintento si el análisis ya se obtuvo).
    if envio["analisis"] is None:
        try:
            envio["analisis"] = an.analizar_opinion(jugador, envio["texto"])
        except an.ErrorEntrada as e:
            return {"tipo": "error_entrada", "texto": str(e)}, True
        except an.ErrorAPI as e:
            return {"tipo": "error_clasificacion",
                    "texto": f"No se pudo consultar el modelo: {e}"}, False
        except an.ErrorValidacion as e:
            return {"tipo": "error_clasificacion",
                    "texto": f"La respuesta del modelo no fue válida: {e}"}, False

    analisis = envio["analisis"]

    # 2) Opinión ajena al jugador: aviso, no se guarda como «neutro».
    if not analisis.es_pertinente:
        return {"tipo": "no_pertinente", "texto": analisis.razon}, True

    # 3) Guardado. El UUID se creó al enviar, no aquí.
    try:
        registro = alm.crear_registro(
            jugador, envio["texto"], analisis, an.nombre_modelo(),
            version_prompt=an.VERSION_PROMPT, registro_id=envio["id"],
        )
        nuevo = alm.guardar_opinion(alm.RUTA_OPINIONES, registro)
    except (alm.ErrorTribuna, an.ErrorAPI) as e:
        return {"tipo": "error_almacenamiento",
                "texto": f"La opinión NO se guardó: {e}"}, False

    return {
        "tipo": "guardado" if nuevo else "ya_guardado",
        "sentimiento": analisis.sentimiento,
        "texto": analisis.razon,
    }, True


def registrar_resultado(envio):
    """Ejecuta el envío y actualiza el estado de sesión."""
    mensaje, terminado = procesar_envio(envio)
    st.session_state.mensajes.append({"rol": "assistant", **mensaje})
    # Si falló de forma recuperable, el envío queda pendiente para «Reintentar».
    st.session_state.pendiente = None if terminado else envio


def reintentar():
    # on_click corre antes de re-ejecutar el script: el resultado aparece ya en el chat.
    if st.session_state.pendiente is not None:
        with st.spinner("Reintentando..."):
            registrar_resultado(st.session_state.pendiente)


def nueva_conversacion():
    # Solo limpia la sesión; los archivos de datos no se tocan.
    st.session_state.mensajes = []
    st.session_state.pendiente = None


# --------------------------------------------------------------------------
# Barra lateral
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Tribuna Global")
    seccion = st.radio("Sección", ["Emitir opinión", "Consultar opiniones"])
    if seccion == "Emitir opinión":
        # El valor interno es el id; el usuario ve «Nombre (País)».
        jugador_id = st.selectbox(
            "Jugador", [j["id"] for j in JUGADORES], format_func=etiqueta_jugador
        )
        st.button("🗑️ Nueva conversación", on_click=nueva_conversacion)


# --------------------------------------------------------------------------
# Sección: Emitir opinión
# --------------------------------------------------------------------------
def mostrar_mensaje(m):
    if m["rol"] == "user":
        with st.chat_message("user"):
            # El jugador se capturó al enviar: cambiar el selector después no altera esto.
            st.caption(f"Sobre: {m['jugador']}")
            st.markdown(m["texto"])
        return
    with st.chat_message("assistant"):
        tipo = m["tipo"]
        if tipo in ("guardado", "ya_guardado"):
            st.markdown(f"{ICONOS[m['sentimiento']]} **{m['sentimiento'].capitalize()}**")
            st.markdown(m["texto"])
            st.success("Guardado" if tipo == "guardado" else "Esta opinión ya estaba guardada.")
        elif tipo == "no_pertinente":
            st.warning(f"No pertinente: no se guardó. {m['texto']}")
        elif tipo == "error_entrada":
            st.error(f"Entrada no válida: {m['texto']}")
        elif tipo == "error_clasificacion":
            st.error(f"Error de clasificación. {m['texto']}")
        else:
            st.error(f"Error de almacenamiento. {m['texto']}")


def seccion_emitir():
    st.subheader("Emitir opinión")
    st.write(f"Jugador seleccionado: **{etiqueta_jugador(jugador_id)}**")

    opinion = st.chat_input("Escribe tu opinión sobre el jugador (5 a 1000 caracteres):")
    if opinion is not None:
        jugador = JUGADOR_POR_ID[jugador_id]  # capturado en este instante
        st.session_state.mensajes.append(
            {"rol": "user", "jugador": jugador["nombre"], "texto": opinion}
        )
        # La longitud se valida ANTES de crear el envío o llamar al modelo.
        try:
            texto = an.validar_texto_opinion(opinion)
        except an.ErrorEntrada as e:
            st.session_state.mensajes.append(
                {"rol": "assistant", "tipo": "error_entrada", "texto": str(e)}
            )
        else:
            # El UUID se genera aquí, una sola vez por envío, y viaja con el envío
            # pendiente: un reintento reutiliza el mismo id y no duplica el registro.
            envio = {"id": str(uuid.uuid4()), "jugador": jugador,
                     "texto": texto, "analisis": None}
            with st.spinner("Analizando opinión..."):
                registrar_resultado(envio)

    for m in st.session_state.mensajes:
        mostrar_mensaje(m)

    if st.session_state.pendiente is not None:
        st.button("🔁 Reintentar envío", on_click=reintentar)


# --------------------------------------------------------------------------
# Sección: Consultar opiniones (solo lectura; nunca llama al modelo)
# --------------------------------------------------------------------------
def seccion_consultar():
    st.subheader("Consultar opiniones")
    try:
        registros = alm.cargar_opiniones(alm.RUTA_OPINIONES)["opiniones"]
    except alm.ErrorArchivoOpiniones as e:
        st.error(f"No se pudo leer el archivo de opiniones: {e}")
        return

    c1, c2 = st.columns(2)
    with c1:
        filtro_jugador = st.selectbox(
            "Jugador", [None] + [j["id"] for j in JUGADORES],
            format_func=lambda i: "Todos" if i is None else etiqueta_jugador(i),
        )
    with c2:
        filtro_sent = st.selectbox(
            "Sentimiento", [None, *SENTIMIENTOS],
            format_func=lambda s: "Todos" if s is None else s.capitalize(),
        )

    # Una sola consulta alimenta tabla, recuentos y descarga: siempre coinciden.
    filtrados = alm.consultar_opiniones(registros, filtro_jugador, filtro_sent)
    if not filtrados:
        st.info("No hay opiniones que coincidan con los filtros.")
        return

    cols = st.columns(5)
    cols[0].metric("Total", len(filtrados))
    for col, s in zip(cols[1:], SENTIMIENTOS):
        col.metric(s.capitalize(), sum(1 for r in filtrados if r["sentimiento"] == s))

    ordenados = sorted(filtrados, key=lambda r: r["fecha_utc"], reverse=True)
    st.dataframe(
        [{"Fecha (UTC)": r["fecha_utc"], "Jugador": r["jugador_nombre"],
          "Opinión": r["opinion_original"], "Sentimiento": r["sentimiento"],
          "Razón": r["razon"]} for r in ordenados],
        width="stretch", hide_index=True,
    )
    st.download_button(
        "⬇️ Descargar JSON filtrado",
        data=json.dumps({"version": 1, "opiniones": filtrados}, ensure_ascii=False, indent=2),
        file_name="opiniones_filtradas.json",
        mime="application/json",
    )


if seccion == "Emitir opinión":
    seccion_emitir()
else:
    seccion_consultar()
