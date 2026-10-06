from __future__ import annotations

import argparse
import asyncio
import importlib
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, AsyncMock

from workflow.config import WorkflowConfig
from workflow.models import DEFAULT_MODEL, MODEL_OPTIONS, validate_model


class ModelSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        refs = Path(__file__).resolve().parents[1] / "Initial sanitized reference files"
        sys.path.insert(0, str(refs))
        with patch.dict(os.environ, {"COPILOT_BASE_MESSAGE_PATH": str(refs / "resources" / "base_message_sanitized.md")}):
            cls.engine = importlib.import_module("resources.implementation_sanitized")
        cls.engine.load_playwright()

    def test_requested_catalogue_and_initial_default(self):
        self.assertEqual(DEFAULT_MODEL, "GPT-6 Sol")
        self.assertEqual(WorkflowConfig.defaults().default_model, DEFAULT_MODEL)
        self.assertEqual([option["value"] for option in MODEL_OPTIONS], [
            "GPT 5.6 Sol Quick response", "GPT 5.6 Sol Think deeper", "GPT-6 Sol",
            "Sonnet 5.5", "Opus 5.5", "Sonnet 5",
        ])
        with self.assertRaises(ValueError):
            validate_model("automatic")

    def test_exact_patterns_keep_version_and_response_mode(self):
        pattern = self.engine.exact_global_model_pattern
        self.assertRegex("GPT-5.6 Sol Think deeper", pattern("GPT 5.6 Sol Think deeper"))
        self.assertRegex("GPT\u20115.6 Sol Quick response", pattern("GPT 5.6 Sol Quick response"))
        self.assertRegex("GPT 6.0 Sol", pattern(DEFAULT_MODEL))
        self.assertIsNone(pattern("Sonnet 5").search("Sonnet 5.5"))
        self.assertIsNone(pattern("Sonnet 5.5").search("Sonnet"))
        self.assertIsNone(pattern("Opus 5.5").search("Opus"))
        self.assertIsNone(pattern("GPT 5.6 Sol Quick response").search("GPT 5.6 Sol Think deeper"))
        self.assertIsNone(pattern(DEFAULT_MODEL).search("GPT 6.0 Think deeper"))

    def test_global_selection_survives_every_size_and_retry_without_input(self):
        for option in MODEL_OPTIONS:
            model = option["value"]
            args = argparse.Namespace(default_model=model)
            with patch("builtins.input", side_effect=AssertionError("Global selection must not prompt")):
                self.engine.confirm_large_case_model(args)
            self.assertEqual((args.small_model, args.medium_model, args.large_model), (model,) * 3)
            for generation in (0, 1, 3, 4, 12):
                self.assertEqual(self.engine.adaptive_retry_model(args, generation, "Opus"), model)

    def test_unavailable_versioned_opus_never_uses_legacy_fallback(self):
        async def check():
            with patch.object(self.engine, "click_model_option", new_callable=AsyncMock) as click:
                click.side_effect = RuntimeError("Exact Opus 5.5 unavailable")
                with patch.object(self.engine, "disable_opus_globally") as disable:
                    with self.assertRaisesRegex(RuntimeError, "Opus 5.5 unavailable"):
                        await self.engine.select_model_with_opus_fallback(object(), "Opus 5.5")
                    self.assertEqual(click.await_count, 1)
                    self.assertEqual(click.await_args.args[1], "Opus 5.5")
                    disable.assert_not_called()
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
