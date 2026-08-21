from pathlib import Path

from crypto_ai.cli import main
from crypto_ai.data.schema import candles_to_table
from crypto_ai.data.storage import write_immutable
from tests.factories import make_candle


def test_validate_and_inspect_commands_smoke(tmp_path: Path, capsys) -> None:
    path = tmp_path / "sample.parquet"
    write_immutable(
        path,
        candles_to_table([make_candle(0), make_candle(1)]),
        metadata={"interval": "5m"},
    )

    assert main(["validate", str(path), "--interval", "5m"]) == 0
    validate_output = capsys.readouterr().out
    assert '"is_valid": true' in validate_output

    assert main(["inspect", str(path), "--limit", "1"]) == 0
    inspect_output = capsys.readouterr().out
    assert '"row_count": 2' in inspect_output
    assert "65000.123456789012345678" in inspect_output
