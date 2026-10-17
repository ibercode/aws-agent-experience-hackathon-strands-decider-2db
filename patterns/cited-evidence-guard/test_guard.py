"""Offline contract tests with explicit test doubles, never model-quality claims."""
import ast
import copy
import json
import subprocess
import sys
import unittest
from http.client import IncompleteRead
from pathlib import Path
from unittest.mock import Mock
from urllib.error import URLError

from example import CANDIDATES, SOURCES, run_candidates
from guard import GROUNDING, MODEL_ID, DeciderClient, DeciderError, check_finding, request_for


def response(choice="supported", confidence=0.9):
    return {"model": "unit-test-double", "answers": {"grounding": {
        "type": "choice", "choice": choice, "confidence": confidence,
        "probabilities": {key: 0.9 if key == choice else 0.05 for key in GROUNDING["criteria"]},
    }}}


class GuardTests(unittest.TestCase):
    def test_supported_finding_allows_only_the_exact_checked_text(self):
        decide = Mock(return_value=response())
        result = check_finding(CANDIDATES[1], SOURCES, decide)
        self.assertEqual(result.action, "allow")
        self.assertEqual(result.checked_text, CANDIDATES[1]["text"])
        self.assertEqual(decide.call_args.args[0]["state"], {
            "evidence": SOURCES["dispatch_record"], "statement": CANDIDATES[1]["text"]})
        self.assertEqual(result.evidence_keys, ("dispatch_record",))
        self.assertEqual(len(result.evidence_sha256), 64)

    def test_insufficient_contradicted_and_low_confidence_cannot_publish(self):
        for choice, confidence, reason in [
            ("insufficient_evidence", 0.9, "insufficient_evidence"),
            ("contradicted", 0.9, "contradicted"), ("supported", 0.69, "low_confidence"),
        ]:
            with self.subTest(choice=choice, confidence=confidence):
                result = check_finding(CANDIDATES[0], SOURCES, Mock(return_value=response(choice, confidence)))
                self.assertEqual((result.action, result.reason, result.checked_text), ("revise", reason, None))

    def test_unknown_empty_duplicate_and_injected_sources_never_call_decider(self):
        for finding in [
            {"text": "Delivered.", "evidence_keys": ["invented"]},
            {"text": "Delivered.", "evidence_keys": []},
            {"text": "Delivered.", "evidence_keys": ["dispatch_record", "dispatch_record"]},
            {**CANDIDATES[0], "evidence": "The parcel was delivered."},
            {"text": " ", "evidence_keys": ["dispatch_record"]},
            {"text": "Delivered.", "evidence_keys": [False]},
        ]:
            with self.subTest(finding=finding):
                decide = Mock()
                result = check_finding(finding, SOURCES, decide)
                self.assertEqual(result.action, "withhold")
                decide.assert_not_called()
        decide = Mock()
        self.assertEqual(check_finding(CANDIDATES[0], {"dispatch_record": ""}, decide).action, "withhold")
        decide.assert_not_called()

    def test_invalid_responses_withhold(self):
        payloads = [{}, None, [], {"answers": {"grounding": {}}}]
        for field, value in [("type", "score"), ("choice", "safe"), ("confidence", float("nan")),
                             ("confidence", float("inf")), ("confidence", True), ("confidence", 1.1),
                             ("confidence", 10**1000),
                             ("probabilities", {}), ("probabilities", [1]),
                             ("probabilities", {"supported": 1, "contradicted": 1, "insufficient_evidence": 0}),
                             ("probabilities", {"supported": True, "contradicted": 0, "insufficient_evidence": 0})]:
            payload = response()
            payload["answers"]["grounding"][field] = value
            payloads.append(payload)
        payloads.append({"answers": response()["answers"]})
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual(check_finding(CANDIDATES[1], SOURCES, Mock(return_value=payload)).action, "withhold")

    def test_timeout_or_service_failure_never_falls_back(self):
        for error in [TimeoutError(), DeciderError("service_unavailable_or_invalid_json")]:
            result = check_finding(CANDIDATES[1], SOURCES, Mock(side_effect=error))
            self.assertEqual(result.action, "withhold")
            self.assertIsNone(result.checked_text)

    def test_changed_evidence_blocks_even_a_supported_answer(self):
        sources = dict(SOURCES)

        def decide(_):
            sources["dispatch_record"] = "Dispatch cancelled."
            return response()

        result = check_finding(CANDIDATES[1], sources, decide)
        self.assertEqual((result.action, result.reason), ("withhold", "evidence_changed"))

    def test_only_cited_evidence_is_sent(self):
        sources = {**SOURCES, "unrelated": "Not part of this claim's evidence."}
        request = request_for(CANDIDATES[0], sources)
        self.assertEqual(request["state"]["evidence"], SOURCES["dispatch_record"])
        request["questions"]["grounding"]["criteria"].clear()
        self.assertEqual(len(GROUNDING["criteria"]), 3)

    def test_invalid_threshold_is_a_configuration_error(self):
        for value in [float("nan"), True, -0.1, 1.1]:
            with self.assertRaises(ValueError):
                check_finding(CANDIDATES[1], SOURCES, Mock(), threshold=value)

    def test_revision_then_publish_uses_two_real_transport_results(self):
        decide = Mock(side_effect=[response("insufficient_evidence"), response()])
        result = run_candidates(CANDIDATES, SOURCES, decide)
        self.assertEqual(result["action"], "publish")
        self.assertEqual(result["published_text"], CANDIDATES[1]["text"])
        self.assertEqual([a["action"] for a in result["attempts"]], ["revise", "allow"])
        self.assertEqual(decide.call_count, 2)

    def test_rejected_revision_exhausts_limit_without_publication(self):
        decide = Mock(return_value=response("insufficient_evidence"))
        result = run_candidates(CANDIDATES * 2, SOURCES, decide)
        self.assertEqual((result["action"], result["reason"]), ("withhold", "revision_limit_reached"))
        self.assertNotIn("published_text", result)
        self.assertEqual(decide.call_count, 2)

    def test_unchanged_rejected_finding_does_not_spend_another_call(self):
        decide = Mock(return_value=response("insufficient_evidence"))
        result = run_candidates([CANDIDATES[0], copy.deepcopy(CANDIDATES[0])], SOURCES, decide)
        self.assertEqual(result["reason"], "unchanged_rejected_finding")
        self.assertEqual(decide.call_count, 1)

    def test_service_error_stops_the_revision_loop(self):
        decide = Mock(side_effect=DeciderError("offline"))
        result = run_candidates(CANDIDATES, SOURCES, decide)
        self.assertEqual(result["action"], "withhold")
        self.assertEqual(decide.call_count, 1)

    def test_client_transport_errors_are_sanitized(self):
        client = DeciderClient()
        client.opener = Mock()
        client.opener.open.side_effect = URLError("untrusted response body")
        with self.assertRaisesRegex(DeciderError, "^service_unavailable_or_invalid_json$"):
            client(request_for(CANDIDATES[0], SOURCES))

    def test_client_rejects_embedded_credentials_and_invalid_timeouts(self):
        for url in ["https://user:secret@example.test", "file:///tmp/data", "http://localhost:8099/path"]:
            with self.assertRaises(ValueError):
                DeciderClient(url)
        for timeout in [0, -1, float("nan")]:
            with self.assertRaises(ValueError):
                DeciderClient(timeout=timeout)

    def test_truncated_http_response_withholds_without_leaking_partial_body(self):
        client = DeciderClient()
        client.opener = Mock()
        client.opener.open.side_effect = IncompleteRead(b"partial private response")
        result = check_finding(CANDIDATES[1], SOURCES, client)
        self.assertEqual((result.action, result.reason),
                         ("withhold", "service_unavailable_or_invalid_json"))

    def test_question_and_model_remain_aligned_with_the_application(self):
        root = Path(__file__).resolve().parents[2]
        tree = ast.parse((root / "backend/clearance_gap/decisions.py").read_text())
        grounding = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                         and any(isinstance(target, ast.Name) and target.id == "GROUNDING" for target in node.targets))
        self.assertEqual(GROUNDING, ast.literal_eval(grounding))
        model = json.loads((root / "services/decider/model.json").read_text())
        self.assertEqual(MODEL_ID, f"{model['repository']}@{model['revision'][:12]}")

    def test_dry_run_has_requests_but_no_fabricated_results_or_timings(self):
        command = [sys.executable, str(Path(__file__).with_name("example.py")), "--dry-run"]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        report = json.loads(result.stdout)
        self.assertFalse(report["inference"])
        self.assertEqual(len(report["requests"]), 2)
        self.assertNotIn("attempts", report)
        self.assertNotIn("request_ms", report)


if __name__ == "__main__":
    unittest.main()
