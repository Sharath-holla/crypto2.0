import pytest
from company_os.security import redact

from scripts.secret_scan import findings


@pytest.mark.parametrize("prefix", ["gsk_", "github_pat_"])
def test_additional_provider_and_fine_grained_token_patterns_are_redacted_and_blocked(prefix):
    synthetic = prefix + "z" * 40
    assert redact(synthetic, ()) == "[REDACTED]"
    assert "provider/GitHub token" in findings("src/sample.py", synthetic.encode(), set())


def test_publication_scan_detects_configured_secrets_tokens_and_private_files():
    value = b"synthetic-secret-scan-case"
    assert "configured secret" in findings("src/sample.py", value, {value})
    assert "provider/GitHub token" in findings("src/sample.py", b"sk-" + b"z" * 32, set())
    assert "private configuration filename" in findings(".env", b"", set())
    assert "private configuration filename" not in findings(".env.example", b"KEY=", set())


def test_synthetic_redaction_fixture_allowance_is_file_and_value_specific():
    sample = b"sk-" + b"abcdefghijklmnopqrstuvwxyz"
    assert not findings("tests/test_security.py", sample, set())
    assert findings("src/service.py", sample, set())
    assert findings("tests/test_security.py", b"sk-" + b"z" * 32, set())
