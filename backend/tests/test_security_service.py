import json
from types import SimpleNamespace
from unittest.mock import patch

from app.services.security_service import SecurityScanner


def test_dependency_audit_uses_real_advisory_output():
    report = {
        "dependencies": [
            {
                "name": "example",
                "version": "1.0",
                "vulns": [
                    {
                        "id": "PYSEC-2026-1",
                        "aliases": ["CVE-2026-12345"],
                        "description": "test advisory",
                        "fix_versions": ["1.1"],
                    }
                ],
            }
        ]
    }
    completed = SimpleNamespace(returncode=1, stdout=json.dumps(report), stderr="")
    with patch("app.services.security_service.subprocess.run", return_value=completed):
        findings = SecurityScanner().audit_dependencies("example==1.0")

    assert len(findings) == 1
    assert findings[0].cve == "CVE-2026-12345"
    assert findings[0].package == "example"


def test_dependency_audit_does_not_invent_results_on_tool_failure():
    completed = SimpleNamespace(returncode=2, stdout="", stderr="network unavailable")
    with patch("app.services.security_service.subprocess.run", return_value=completed):
        assert SecurityScanner().audit_dependencies("example==1.0") == []
