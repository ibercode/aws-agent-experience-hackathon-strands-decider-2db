"""Publication-boundary checks; synthetic examples contain no actual credentials."""
import importlib.util
import subprocess
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("publication", Path(__file__).parents[1] / "check_publication.py")
publication = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publication)


def test_private_paths_are_blocked_and_examples_are_allowed():
    for name in ["backend/.env", ".data/session.json", "infra/terraform.tfstate.backup",
                 "infra/terraform.tfvars.json", ".aws/config", "docs/hackathon-submission-checklist.md",
                 "docs/submission/video-script.md", "docs/submission/video-voiceover.txt"]:
        assert publication.private_path(name)
    for name in ["backend/.env.example", "infrastructure/terraform/terraform.tfvars.example", "LICENSE"]:
        assert not publication.private_path(name)


def test_identifiers_report_location_and_category_without_values():
    value = "person" + "@" + "private-company.testdomain"
    assert publication.scan_text("app.py", value) == [("app.py", 1, "email")]
    assert publication.scan_text("app.py", "/" + "Users" + "/private-user/file") == [("app.py", 1, "private_home_path")]


def test_only_documented_test_and_license_exceptions_are_allowed():
    assert publication.scan_text("tests.py", "example@example.test") == []
    public_copyright = "author" + "@" + "upstream-project.org"
    assert publication.scan_text("frontend/public/third-party-notices.txt", public_copyright) == []
    assert publication.scan_text("frontend/src/app.ts", public_copyright)
    example_arn = "arn:aws:service:eu-west-1:" + "123456789012" + ":resource/example"
    assert publication.scan_text("scripts/tests/example.py", example_arn) == []
    assert publication.scan_text("config.py", example_arn)


def test_public_contact_exception_does_not_allow_other_mailboxes():
    assert publication.scan_text("frontend/src/JudgeAccessContact.tsx", "decider@ibercode.com") == []
    for address in ["personal" + "@" + "ibercode.com", "decider" + "@" + "private-company.testdomain"]:
        assert publication.scan_text("README.md", address) == [("README.md", 1, "email")]


def test_staged_check_reads_index_not_subsequent_working_copy(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "settings.py"
    path.write_text('address="' + "private" + "@" + "example-company.testdomain" + '"\n')
    subprocess.run(["git", "add", "settings.py"], check=True)
    path.write_text('address="example@example.test"\n')
    assert publication.check(staged=True)[1] == [("settings.py", 1, "email")]
    assert publication.check(staged=False)[1] == []
