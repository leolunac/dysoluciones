import json

import requests
from django.conf import settings


class ErrorRevisionIA(Exception):
    pass


def _extraer_texto(respuesta):
    for elemento in respuesta.get("output", []):
        for contenido in elemento.get("content", []):
            if contenido.get("type") == "output_text" and contenido.get("text"):
                return contenido["text"]
    raise ErrorRevisionIA("La IA no devolvió una propuesta de redacción.")


def revisar_redaccion(campos, contexto="informe técnico"):
    api_key = getattr(settings, "OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ErrorRevisionIA(
            "La revisión con IA todavía no está configurada en el servidor."
        )

    if not isinstance(campos, dict):
        raise ErrorRevisionIA("Los campos enviados no son válidos.")

    campos_limpios = {}
    for clave, valor in list(campos.items())[:8]:
        if not isinstance(clave, str) or not isinstance(valor, str):
            continue
        clave = clave.strip()[:80]
        valor = valor.strip()[:4000]
        if clave and valor:
            campos_limpios[clave] = valor

    if not campos_limpios:
        raise ErrorRevisionIA("Escriba información antes de solicitar la revisión.")

    if sum(len(valor) for valor in campos_limpios.values()) > 12000:
        raise ErrorRevisionIA("El texto es demasiado extenso para revisarlo en una sola solicitud.")

    esquema = {
        "type": "object",
        "properties": {
            clave: {"type": "string"}
            for clave in campos_limpios
        },
        "required": list(campos_limpios),
        "additionalProperties": False,
    }
    entrada = json.dumps(
        {"contexto": contexto[:120], "campos": campos_limpios},
        ensure_ascii=False,
    )
    datos = {
        "model": getattr(settings, "OPENAI_MODEL", "gpt-5-mini"),
        "store": False,
        "instructions": (
            "Actúa como corrector de informes técnicos de mantenimiento de sistemas "
            "de bombeo. Corrige únicamente ortografía, puntuación, concordancia y "
            "claridad. Conserva exactamente los hechos, nombres de equipos, marcas, "
            "cantidades, unidades, mediciones, resultados y negaciones. No inventes "
            "trabajos, fallas, repuestos, recomendaciones ni conclusiones. Devuelve "
            "todos los campos con las mismas claves y solo el texto corregido."
        ),
        "input": entrada,
        "max_output_tokens": getattr(settings, "OPENAI_MAX_OUTPUT_TOKENS", 1800),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "revision_redaccion_tecnica",
                "strict": True,
                "schema": esquema,
            }
        },
    }

    try:
        respuesta = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=datos,
            timeout=getattr(settings, "OPENAI_TIMEOUT", 30),
        )
    except requests.RequestException as exc:
        raise ErrorRevisionIA(
            "No fue posible comunicarse con la IA. Revise la conexión e intente nuevamente."
        ) from exc

    if respuesta.status_code != 200:
        raise ErrorRevisionIA(
            "El servicio de IA no pudo procesar la solicitud en este momento."
        )

    try:
        corregidos = json.loads(_extraer_texto(respuesta.json()))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ErrorRevisionIA("La respuesta de la IA no tiene el formato esperado.") from exc

    if set(corregidos) != set(campos_limpios):
        raise ErrorRevisionIA("La IA devolvió campos diferentes a los enviados.")
    if not all(isinstance(valor, str) and valor.strip() for valor in corregidos.values()):
        raise ErrorRevisionIA("La IA devolvió una propuesta incompleta.")

    return {clave: valor.strip() for clave, valor in corregidos.items()}
