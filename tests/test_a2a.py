import unittest

from a2a.helpers import get_message_text, new_text_artifact, new_text_message
from a2a.types import Role, StreamResponse, Task, UnsupportedOperationError

from a2a_client import extract_response
from a2a_server import ParachuteAgentExecutor, build_agent_card


class FakeContext:
    def __init__(self, text, context_id="conversation-1"):
        self.context_id = context_id
        self.task_id = "task-1"
        self._text = text

    def get_user_input(self):
        return self._text


class FakeEventQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, event):
        self.events.append(event)


class A2AServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_executor_returns_agent_output_and_reuses_conversation_history(self):
        calls = []

        def run_turn(text, messages=None):
            calls.append((text, messages))
            return {"output": f"respuesta: {text}", "messages": [text]}

        executor = ParachuteAgentExecutor(turn_runner=run_turn)

        first_queue = FakeEventQueue()
        await executor.execute(FakeContext("hola"), first_queue)
        second_queue = FakeEventQueue()
        await executor.execute(FakeContext("¿y el precio?"), second_queue)

        self.assertEqual("respuesta: hola", get_message_text(first_queue.events[0]))
        self.assertEqual("respuesta: ¿y el precio?", get_message_text(second_queue.events[0]))
        self.assertIsNone(calls[0][1])
        self.assertEqual(["hola"], calls[1][1])

    async def test_executor_rejects_oversized_input_before_calling_the_agent(self):
        calls = []
        executor = ParachuteAgentExecutor(
            turn_runner=lambda text, messages=None: calls.append(text)
        )
        queue = FakeEventQueue()

        await executor.execute(FakeContext("x" * 10_001), queue)

        self.assertEqual([], calls)
        self.assertIn("demasiado largo", get_message_text(queue.events[0]))

    async def test_executor_does_not_expose_internal_errors_to_the_client(self):
        def broken_runner(text, messages=None):
            raise RuntimeError("NVIDIA_API_KEY=secret-value")

        executor = ParachuteAgentExecutor(turn_runner=broken_runner)
        queue = FakeEventQueue()

        with self.assertLogs("a2a_server", level="ERROR") as logs:
            await executor.execute(FakeContext("hola"), queue)

        response = get_message_text(queue.events[0])
        self.assertIn("No fue posible procesar", response)
        self.assertNotIn("secret-value", response)
        self.assertNotIn("secret-value", "\n".join(logs.output))

    def test_agent_card_advertises_faq_and_weather_skills(self):
        card = build_agent_card("http://127.0.0.1:9999")

        self.assertEqual("Parachute S.A. Multi-Agent System", card.name)
        self.assertEqual({"faq", "weather"}, {skill.id for skill in card.skills})
        self.assertEqual("JSONRPC", card.supported_interfaces[0].protocol_binding)

    async def test_executor_reports_cancellation_as_unsupported(self):
        executor = ParachuteAgentExecutor()

        with self.assertRaises(UnsupportedOperationError):
            await executor.cancel(FakeContext("cancelar"), FakeEventQueue())


class A2AClientTests(unittest.TestCase):
    def test_extract_response_supports_direct_messages(self):
        message = new_text_message(
            "respuesta directa", context_id="ctx-message", role=Role.ROLE_AGENT
        )

        text, context_id = extract_response(StreamResponse(message=message))

        self.assertEqual("respuesta directa", text)
        self.assertEqual("ctx-message", context_id)

    def test_extract_response_supports_task_artifacts(self):
        task = Task(
            id="task-1",
            context_id="ctx-task",
            artifacts=[new_text_artifact("respuesta", "respuesta de tarea")],
        )

        text, context_id = extract_response(StreamResponse(task=task))

        self.assertEqual("respuesta de tarea", text)
        self.assertEqual("ctx-task", context_id)


if __name__ == "__main__":
    unittest.main()
