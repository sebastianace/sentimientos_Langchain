# Tribuna Global

Chatbot en Streamlit que registra opiniones de aficionados sobre futbolistas, clasifica su
sentimiento (`positivo`, `negativo`, `neutro`, `mixto`) con LangChain + OpenAI y las guarda en
JSON para consultarlas después de reiniciar la app.

> El catálogo es una selección didáctica, no una clasificación oficial. La clasificación describe
> lo que expresa el aficionado, no la calidad del jugador, y las cifras solo reflejan las
> opiniones registradas en esta aplicación.

## Instalación

Requiere Python 3.10 o superior.

```bash
cd tribuna_global
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configuración

```bash
cp .env.example .env
```

Edita `.env` (nunca se sube al repositorio):

```dotenv
OPENAI_API_KEY=tu_clave
OPENAI_MODEL=un_modelo_que_admita_salida_estructurada
# Opcional: json_schema (por defecto) o function_calling
# OPENAI_STRUCTURED_METHOD=json_schema
```

### Alternativa sin costo: Ollama (la usada en esta entrega)

Las pruebas y los datos semilla se generaron con Ollama local y `llama3.1`, no con OpenAI:

```dotenv
OPENAI_API_KEY=ollama
OPENAI_MODEL=llama3.1
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_STRUCTURED_METHOD=function_calling
```

Requiere `ollama serve` activo y `ollama pull llama3.1`. Cada registro guarda el modelo usado.

`OPENAI_STRUCTURED_METHOD` solo se cambia si el modelo elegido rechaza el esquema `json_schema`
(ver «Decisiones» más abajo).

## Ejecución

```bash
streamlit run app.py
```

También funciona desde otra carpeta (`streamlit run /ruta/a/tribuna_global/app.py`), porque las
rutas se calculan desde la ubicación de los archivos.

Para sembrar 16 opiniones ficticias (usa la API real y requiere `.env`):

```bash
python scripts/sembrar_opiniones.py
```

## Pruebas

```bash
python -m pytest
```

Ninguna prueba llama a la API: el modelo se sustituye por un objeto falso y `OPENAI_API_KEY` se
borra del entorno durante los tests. Los resultados y los casos pendientes están en
[PRUEBAS.md](PRUEBAS.md).

## Versiones utilizadas

Obtenidas con `pip freeze` filtrado a las dependencias directas (Python 3.15.2):

```text
streamlit==1.67.0
langchain-core==1.7.6
langchain-openai==1.7.4
python-dotenv==1.2.4
pydantic==2.14.3
pytest==9.2.0
```

## Arquitectura

```text
app.py              Interfaz Streamlit (dos secciones, estado de sesión, mensajes de error)
analisis.py         Prompt, esquema AnalisisOpinion, validación y analizar_opinion
almacenamiento.py   Lectura/escritura atómica de JSON, excepciones propias, consultar_opiniones
datos/              jugadores.json (catálogo) y opiniones.json (registro persistente)
scripts/            sembrar_opiniones.py (datos ficticios clasificados por el modelo real)
tests/              pytest + streamlit.testing, sin llamadas a la API
```

Flujo de «Emitir opinión»: validar longitud (5–1000 tras `strip`) → generar UUID del envío →
`analizar_opinion` (solo la opinión actual, sin historial) → si no es pertinente, aviso sin guardar →
`guardar_opinion` → «Guardado» solo si la escritura terminó bien.

### Decisiones

- **Sin duplicados en reruns.** El UUID se crea al enviar y viaja en `session_state` con el envío
  pendiente; `guardar_opinion` rechaza ids ya existentes. Cambiar un filtro solo ejecuta código de
  lectura.
- **Escritura atómica.** Se escribe un archivo temporal en el mismo directorio y se reemplaza con
  `os.replace`; un fallo no deja el JSON a medias.
- **Archivo dañado.** Se muestra el error y se detiene la app; nunca se sobrescribe con una lista vacía.
- **Fallos ≠ neutro.** Error de entrada, de API/validación y de escritura son excepciones distintas y
  nunca se registran como sentimiento.
- **Salida estructurada.** `with_structured_output(AnalisisOpinion, method="json_schema")`: es el
  mecanismo nativo de OpenAI y restringe la respuesta al esquema. La coherencia
  pertinente ⇔ sentimiento se valida aparte con un `model_validator`.
  Pendiente de comprobar con la API real: el esquema incluye `minLength/maxLength` en `razon`; si el
  modelo lo rechaza, usar `OPENAI_STRUCTURED_METHOD=function_calling`.
- **Un solo escritor.** El acceso concurrente al JSON es un desafío de ampliación (sección 12 del
  enunciado) y no está implementado.
