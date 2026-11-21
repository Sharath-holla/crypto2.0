"""Paper-trade the averaged Phase 7A fold models on live Binance USD-M data (no orders, no keys).

Every 5m close: pull public klines/funding/mark/index, build features with the project's own
feature code, average the predictions of every saved fold model, and open a paper position when
|ensemble| clears round-trip cost + the smallest Cal-B threshold. At the end, open positions are
marked to the live price net of cost. The models predict 60m ahead, so a short run only shows
mark-to-market, not the realized 60m outcome.
"""

import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pyarrow as pa

from crypto_ai.phase7.config import FeatureConfig
from crypto_ai.phase7.features import (
    bind_fold_cross_sectional_context,
    build_higher_timeframe_context,
    generate_multiasset_features,
)

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "docs/reviews/evidence_pilot_4fold_20261121/models"
API = "https://fapi.binance.com"
COST_BPS = 14.0
THRESHOLD_BPS = 2.0
IST = timedelta(hours=5, minutes=30)


def get(path, **params):
    url = API + path + "?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                return json.loads(response.read())
        except OSError:
            if attempt == 4:
                raise
            time.sleep(2)


def ist(ms):
    return (datetime.fromtimestamp(ms / 1000, UTC) + IST).strftime("%H:%M:%S IST")


def klines(path, symbol_key, symbol, interval, rows, now_ms):
    out, end = [], now_ms - 1
    while len(out) < rows:
        params = {
            symbol_key: symbol,
            "interval": interval,
            "limit": min(1500, rows - len(out)),
            "endTime": end,
        }
        batch = get(path, **params)
        if not batch:
            break
        out = batch + out
        end = batch[0][0] - 1
    return [k for k in out if k[6] < now_ms]  # completed candles only


def candle_table(symbol, raw):
    return {
        "symbol": [symbol] * len(raw),
        "open_time": [k[0] * 1000 for k in raw],
        "open": [float(k[1]) for k in raw],
        "high": [float(k[2]) for k in raw],
        "low": [float(k[3]) for k in raw],
        "close": [float(k[4]) for k in raw],
        "volume": [float(k[5]) for k in raw],
        "quote_volume": [float(k[7]) for k in raw],
        "trade_count": [float(k[8]) for k in raw],
        "taker_buy_quote_volume": [min(float(k[10]), float(k[7])) for k in raw],
    }


def asof(feature_times_ms, available_ms, values, max_age_ms):
    out = np.full(len(feature_times_ms), np.nan)
    idx = np.searchsorted(available_ms, feature_times_ms, side="right") - 1
    ok = idx >= 0
    ok[ok] = feature_times_ms[ok] - available_ms[idx[ok]] <= max_age_ms
    out[ok] = values[idx[ok]]
    return out


def to_table(columns):
    columns = dict(columns)
    columns["open_time"] = pa.array(columns["open_time"], type=pa.timestamp("us", tz="UTC"))
    return pa.table(columns)


class Registry:
    """Duck-typed registry: features only need by_symbol() records.

    Each record exposes exists_at() and causal_available_from.
    """

    class Record:
        def __init__(self, onboard):
            self.causal_available_from = onboard

        def exists_at(self, timestamp):
            return timestamp >= self.causal_available_from

    def __init__(self, onboard):
        self.records = {s: self.Record(t) for s, t in onboard.items()}

    def by_symbol(self):
        return self.records


def build_snapshot(symbols, onboard, now_ms=None):
    now_ms = now_ms or int(time.time() * 1000)
    five, twelve, daily = [], [], []
    for symbol in symbols:
        raw5 = klines("/fapi/v1/klines", "symbol", symbol, "5m", 2200, now_ms)
        cols = candle_table(symbol, raw5)
        feature_ms = np.asarray(cols["open_time"]) // 1000 + 300_000
        funding = get("/fapi/v1/fundingRate", symbol=symbol, limit=1000, endTime=now_ms - 1)
        mark = klines("/fapi/v1/markPriceKlines", "symbol", symbol, "5m", 3, now_ms)
        index = klines("/fapi/v1/indexPriceKlines", "pair", symbol, "5m", 3, now_ms)
        cols["funding_rate"] = asof(
            feature_ms,
            np.asarray([f["fundingTime"] for f in funding], dtype=np.int64),
            np.asarray([float(f["fundingRate"]) for f in funding]),
            86_400_000,
        )
        for name, series in (("mark_price", mark), ("index_price", index)):
            cols[name] = asof(
                feature_ms,
                np.asarray([k[0] + 300_000 for k in series], dtype=np.int64),
                np.asarray([float(k[4]) for k in series]),
                300_000,
            )
        five.append(to_table(cols))
        twelve.append(
            to_table(
                candle_table(
                    symbol, klines("/fapi/v1/klines", "symbol", symbol, "12h", 500, now_ms)
                )
            )
        )
        daily.append(
            to_table(
                candle_table(symbol, klines("/fapi/v1/klines", "symbol", symbol, "1d", 500, now_ms))
            )
        )
    candles = pa.concat_tables(five)
    context = build_higher_timeframe_context(pa.concat_tables(twelve), pa.concat_tables(daily))
    features = generate_multiasset_features(
        candles,
        registry=Registry(onboard),
        config=FeatureConfig(),
        higher_timeframe_context=context,
    ).table
    times = features.column("feature_time").combine_chunks().cast(pa.int64()).to_numpy()
    latest = features.filter(pa.array(times == times.max()))
    latest = bind_fold_cross_sectional_context(latest)
    prices = {s: float(c.column("close")[-1].as_py()) for s, c in zip(symbols, five, strict=True)}
    return latest, int(times.max() // 1000), prices


def live_prices(symbols):
    book = {t["symbol"]: t for t in get("/fapi/v1/ticker/bookTicker")}
    return {s: (float(book[s]["bidPrice"]) + float(book[s]["askPrice"])) / 2 for s in symbols}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=10.0)
    parser.add_argument("--out", type=Path, default=ROOT / "output/paper_trade")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    run = args.out / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run.mkdir()

    models = {p.parent.name: joblib.load(p) for p in sorted(MODELS.glob("*/model.joblib"))}
    universe = sorted({s for m in models.values() for s in m.symbol_levels})
    info = {s["symbol"]: s for s in get("/fapi/v1/exchangeInfo")["symbols"]}
    symbols = [s for s in universe if s in info and info[s]["status"] == "TRADING"]
    onboard = {s: datetime.fromtimestamp(info[s]["onboardDate"] / 1000, UTC) for s in symbols}
    print(
        f"{len(models)} models loaded; trading {len(symbols)} live symbols "
        f"(skipped delisted: {sorted(set(universe) - set(symbols))})",
        flush=True,
    )

    deadline = time.time() + args.minutes * 60
    positions, decisions, seen = [], [], set()
    while True:
        table, feature_ms, prices = build_snapshot(symbols, onboard)
        if feature_ms not in seen:
            seen.add(feature_ms)
            row_symbols = table.column("symbol").to_pylist()
            per_model = np.vstack([m.predict(table)[0] for m in models.values()])
            # Re-runs of one fold are identical; average per fold so no fold counts twice.
            folds = sorted({name.split("__")[0] for name in models})
            per_fold = np.vstack(
                [per_model[[n.split("__")[0] == f for n in models]].mean(axis=0) for f in folds]
            )
            ensemble = per_fold.mean(axis=0)
            agree = (np.sign(per_model) == np.sign(ensemble)).mean(axis=0)
            print(
                f"\n=== candle closed {ist(feature_ms)} — ensemble 60m forecast (bps) ===",
                flush=True,
            )
            for i in np.argsort(-np.abs(ensemble)):
                bps = ensemble[i] * 1e4
                take = abs(bps) >= COST_BPS + THRESHOLD_BPS
                side = ("LONG" if bps > 0 else "SHORT") if take else "skip"
                print(
                    f"  {row_symbols[i]:10s} {bps:+7.2f}  "
                    f"models agreeing {agree[i]:4.0%}  -> {side}",
                    flush=True,
                )
                decisions.append(
                    {
                        "time_ist": ist(feature_ms),
                        "symbol": row_symbols[i],
                        "ensemble_bps": bps,
                        "agreement": agree[i],
                        "decision": side,
                        "per_model_bps": dict(
                            zip(models, (per_model[:, i] * 1e4).round(3).tolist(), strict=True)
                        ),
                    }
                )
                if take:
                    positions.append(
                        {
                            "symbol": row_symbols[i],
                            "side": side,
                            "entry": prices[row_symbols[i]],
                            "entry_time_ist": ist(feature_ms),
                            "forecast_bps": bps,
                        }
                    )
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        next_close = (int(time.time()) // 300 + 1) * 300 + 8  # 8s after the next 5m close
        wait = next_close - time.time()
        if wait > remaining:
            time.sleep(remaining)
            break
        print(f"  ...waiting for next 5m candle ({int(wait)}s)", flush=True)
        time.sleep(wait)

    now = live_prices(symbols)
    total = 0.0
    print(f"\n=== {args.minutes:g}-minute paper result at {ist(time.time() * 1000)} ===")
    for p in positions:
        move = (now[p["symbol"]] / p["entry"] - 1) * 1e4 * (1 if p["side"] == "LONG" else -1)
        p["exit_mark"], p["gross_bps"], p["net_bps"] = now[p["symbol"]], move, move - COST_BPS
        total += p["net_bps"]
        print(
            f"  {p['side']:5s} {p['symbol']:10s} gross {move:+7.2f} bps  "
            f"net {p['net_bps']:+7.2f} bps"
        )
    if not positions:
        print(
            "  NO TRADES — no ensemble forecast cleared cost + threshold "
            f"({COST_BPS + THRESHOLD_BPS:g} bps)."
        )
    else:
        print(
            f"  total net {total:+.2f} bps over {len(positions)} paper trades "
            "(mark-to-market, 60m horizon not reached)"
        )
    (run / "decisions.json").write_text(json.dumps(decisions, indent=1))
    (run / "positions.json").write_text(json.dumps(positions, indent=1))
    print(f"\nsaved: {run}")


if __name__ == "__main__":
    main()
