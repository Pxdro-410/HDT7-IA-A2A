import asyncio
import os

import httpx
from a2a.client import A2ACardResolver, A2AClientError, ClientConfig, create_client
from a2a.helpers import get_message_text, get_text_parts, new_text_message
from a2a.types import Role, SendMessageRequest, StreamResponse


def extract_response(response: StreamResponse) -> tuple[str, str | None]:
    payload = response.WhichOneof("payload")

    if payload == "message":
        return get_message_text(response.message), response.message.context_id

    if payload == "task":
        text = "\n".join(
            part
            for artifact in response.task.artifacts
            for part in get_text_parts(artifact.parts)
        )
        if not text and response.task.status.HasField("message"):
            text = get_message_text(response.task.status.message)
        return text, response.task.context_id

    if payload == "artifact_update":
        return (
            "\n".join(get_text_parts(response.artifact_update.artifact.parts)),
            response.artifact_update.context_id,
        )

    if payload == "status_update":
        message = response.status_update.status.message
        text = get_message_text(message) if message.parts else ""
        return text, response.status_update.context_id

    return "", None


async def send_text(client, text: str, context_id: str | None = None):
    message = new_text_message(text, context_id=context_id, role=Role.ROLE_USER)
    request = SendMessageRequest(message=message)
    output = ""

    async for response in client.send_message(request):
        response_text, response_context_id = extract_response(response)
        if response_text:
            output = response_text
        if response_context_id:
            context_id = response_context_id

    return output, context_id


async def run_terminal():
    server_url = os.getenv("A2A_SERVER_URL", "http://127.0.0.1:9999")
    timeout_sec = float(os.getenv("A2A_CLIENT_TIMEOUT", "60.0"))
    print("\n  Cliente A2A - Parachute S.A. - HDT7 IA")
    print(f"  Descubriendo agente en: {server_url}")
    print("  Escribe 'Bye' para salir.\n")

    http_client = httpx.AsyncClient(timeout=timeout_sec)
    try:
        resolver = A2ACardResolver(http_client, server_url)
        agent_card = await resolver.get_agent_card()

        client = await create_client(
            agent=agent_card,
            client_config=ClientConfig(streaming=False, httpx_client=http_client),
        )
        context_id = None

        try:
            while True:
                user_input = (await asyncio.to_thread(input, "\nTú: ")).strip()
                if user_input.lower() == "bye":
                    break
                if not user_input:
                    continue

                output, context_id = await send_text(client, user_input, context_id)
                print("\nSupervisor Central:")
                print(output or "El servidor A2A no devolvió contenido.")
        finally:
            await client.close()
    finally:
        await http_client.aclose()


def main():
    try:
        asyncio.run(run_terminal())
    except (A2AClientError, httpx.HTTPError, OSError) as exc:
        print(f"No se pudo conectar al servidor A2A: {exc}")


if __name__ == "__main__":
    main()
