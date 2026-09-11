"""Patch test_task_aware_routing.py to use new source-role rejection messages."""
import os

path = os.path.join(os.path.dirname(__file__), "..", "tests", "test_task_aware_routing.py")

with open(path, encoding="utf-8") as f:
    content = f.read()

OLD_LINKEDIN = (
    "        self.assertFalse(res[\"verified\"])\n"
    "        self.assertEqual(res[\"status\"], \"UNVERIFIED\")\n"
    "        self.assertIn(\"generic encyclopedia/dictionary/social\", res[\"reason\"])\n"
    "\n"
    "    def test_google_play_rejected_as_trigger_source"
)
NEW_LINKEDIN = (
    "        self.assertFalse(res[\"verified\"])\n"
    "        self.assertEqual(res[\"status\"], \"UNVERIFIED\")\n"
    "        self.assertEqual(res[\"source_role\"], \"DISCOVERY_ONLY\")\n"
    "        self.assertIn(\"not acceptable for claim type\", res[\"reason\"])\n"
    "\n"
    "    def test_google_play_rejected_as_trigger_source"
)

assert OLD_LINKEDIN in content, "LinkedIn block not found"
content = content.replace(OLD_LINKEDIN, NEW_LINKEDIN, 1)

OLD_GPLAY = (
    "        self.assertFalse(res[\"verified\"])\n"
    "        self.assertEqual(res[\"status\"], \"UNVERIFIED\")\n"
    "        self.assertIn(\"generic encyclopedia/dictionary/social\", res[\"reason\"])\n"
    "\n"
    "    def test_job_board_rejected_as_trigger_source"
)
NEW_GPLAY = (
    "        self.assertFalse(res[\"verified\"])\n"
    "        self.assertEqual(res[\"status\"], \"UNVERIFIED\")\n"
    "        self.assertEqual(res[\"source_role\"], \"IRRELEVANT\")\n"
    "        self.assertIn(\"irrelevant\", res[\"reason\"])\n"
    "\n"
    "    def test_job_board_rejected_as_trigger_source"
)

assert OLD_GPLAY in content, "Google Play block not found"
content = content.replace(OLD_GPLAY, NEW_GPLAY, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched test_task_aware_routing.py successfully.")
