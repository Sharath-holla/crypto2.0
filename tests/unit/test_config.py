from pathlib import Path

import pytest
from pydantic import ValidationError

from crypto_ai.config import BinanceSettings, load_binance_settings
from crypto_ai.domain import Market


def test_default_market_is_primary_usdm_futures() -> None:
    settings = BinanceSettings()

    assert settings.market is Market.USD_M
    assert settings.request_limit == 1_000


def test_settings_normalize_symbol_and_load_toml(tmp_path: Path) -> None:
    config = tmp_path / "binance.toml"
    config.write_text(
        '[binance]\nmarket = "usdm"\nsymbol = "btcusdt"\ninterval = "1m"\n',
        encoding="utf-8",
    )

    settings = load_binance_settings(config, {"request_limit": 900})

    assert settings.market is Market.USD_M
    assert settings.symbol == "BTCUSDT"
    assert settings.interval == "1m"
    assert settings.request_limit == 900


def test_settings_reject_calendar_month_and_market_specific_oversized_pages() -> None:
    with pytest.raises(ValidationError):
        BinanceSettings(interval="1M")
    with pytest.raises(ValidationError):
        BinanceSettings(market=Market.SPOT, request_limit=1_001)
    with pytest.raises(ValidationError):
        BinanceSettings(market=Market.USD_M, request_limit=1_501)

    assert BinanceSettings(market=Market.USD_M, request_limit=1_500).request_limit == 1_500
