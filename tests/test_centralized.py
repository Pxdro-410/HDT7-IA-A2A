import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import centralized


class CentralizedSupervisorTests(unittest.TestCase):
    def test_extracts_next_saturday_without_asking_the_model(self):
        result = centralized.extract_weather_date(
            "¿Puedo saltar el próximo sábado?",
            today=datetime.date(2026, 10, 13),
        )

        self.assertEqual("2026-10-17", result)

    def test_weather_queries_require_worker_delegation(self):
        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=None))

        with (
            patch.object(centralized, "client", fake_client),
            patch.object(
                centralized,
                "extract_weather_date",
                return_value="2026-10-17",
            ),
            patch.object(
                centralized,
                "weather_worker_agent",
                return_value="Reporte meteorológico para 2026-10-17.",
            ),
        ):
            result = centralized.run_agent_turn(
                "¿Puedo saltar el próximo sábado?"
            )

        self.assertEqual(["delegate_to_weather_worker"], result["tools_called"])
        self.assertIn("2026-10-17", result["output"])


if __name__ == "__main__":
    unittest.main()
