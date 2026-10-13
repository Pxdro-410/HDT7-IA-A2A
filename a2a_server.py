import asyncio
import logging
import os
import time

from a2a.helpers import new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    UnsupportedOperationError,
)
from starlette.applications import Starlette


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [A2A-SERVER] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("a2a_server")
MAX_INPUT_CHARS = 10_000


def _run_centralized_turn(user_input, messages=None):
    from centralized import run_agent_turn

    return run_agent_turn(user_input, messages)


class ParachuteAgentExecutor(AgentExecutor):
    """Adapta el MAS centralizado al contrato AgentExecutor de A2A."""

    def __init__(self, turn_runner=_run_centralized_turn):
        self.turn_runner = turn_runner
        self.conversations = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        user_input = context.get_user_input().strip()
        context_id = context.context_id
        started_at = time.perf_counter()
        logger.info(
            "event=a2a_request_received entry_point=jsonrpc context_id=%s",
            context_id,
        )

        if not user_input:
            output = "No se recibió texto para procesar."
        elif len(user_input) > MAX_INPUT_CHARS:
            logger.warning(
                "event=a2a_request_rejected reason=input_too_long context_id=%s",
                context_id,
            )
            output = "El mensaje es demasiado largo para procesarlo."
        else:
            try:
                result = await asyncio.to_thread(
                    self.turn_runner,
                    user_input,
                    self.conversations.get(context_id),
                )
                self.conversations[context_id] = result["messages"]
                output = result["output"]
                logger.info(
                    "event=a2a_request_completed context_id=%s tools=%s latency_ms=%.1f",
                    context_id,
                    result.get("tools_called", []),
                    (time.perf_counter() - started_at) * 1000,
                )
            except Exception as exc:
                logger.error(
                    "event=a2a_request_failed context_id=%s error_type=%s latency_ms=%.1f",
                    context_id,
                    type(exc).__name__,
                    (time.perf_counter() - started_at) * 1000,
                )
                output = "No fue posible procesar la solicitud. Revisa los logs del servidor."

        await event_queue.enqueue_event(
            new_text_message(output, context_id=context_id)
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        logger.info(
            "event=a2a_cancel_rejected reason=immediate_response context_id=%s",
            context.context_id,
        )
        raise UnsupportedOperationError


def build_agent_card(public_url: str) -> AgentCard:
    return AgentCard(
        name="Parachute S.A. Multi-Agent System",
        description=(
            "Supervisor de Parachute S.A. para preguntas frecuentes y "
            "evaluación meteorológica de fechas de salto."
        ),
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                url=public_url,
                protocol_version="1.0",
            )
        ],
        skills=[
            AgentSkill(
                id="faq",
                name="Preguntas frecuentes",
                description="Responde consultas sobre requisitos, precios y logística.",
                tags=["faq", "paracaidismo", "rag"],
                examples=["¿Cuál es el peso máximo para saltar?"],
            ),
            AgentSkill(
                id="weather",
                name="Factibilidad meteorológica",
                description="Evalúa si una fecha es apta para un salto tándem.",
                tags=["clima", "agenda", "seguridad"],
                examples=["¿Puedo saltar el próximo sábado?"],
            ),
        ],
    )


def build_app(
    public_url: str | None = None,
    executor: AgentExecutor | None = None,
) -> Starlette:
    public_url = public_url or os.getenv("A2A_PUBLIC_URL", "http://127.0.0.1:9999")
    agent_card = build_agent_card(public_url)
    handler = DefaultRequestHandler(
        agent_executor=executor or ParachuteAgentExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )
    routes = create_agent_card_routes(agent_card)
    routes.extend(create_jsonrpc_routes(handler, "/"))
    return Starlette(routes=routes)


app = build_app()


def main():
    import uvicorn

    host = os.getenv("A2A_HOST", "127.0.0.1")
    port = int(os.getenv("A2A_PORT", "9999"))
    logger.info("event=a2a_server_started host=%s port=%s", host, port)
    logger.info(
        "event=a2a_agent_card_ready url=http://%s:%s/.well-known/agent-card.json",
        host,
        port,
    )
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
