"""
runpipeline.py — End-to-end orchestrator for the DL model rebuild
══════════════════════════════════════════════════════════════════════════════
Usage:

  # Full pipeline (download → features → labels → train)
  python -m transformer.runpipeline --mode train

  # Download only (cache parquet files for repeated training experiments)
  python -m transformer.runpipeline --mode download

  # Features + labels only (inspect label distribution)
  python -m transformer.runpipeline --mode labels

  # Test that DLInferenceEngine loads and runs a forward pass
  python -m transformer.runpipeline --mode test-inference

  # Load parquet from transformer/data/ (user-downloaded files)
  python -m transformer.runpipeline --mode train --from-parquet

Swap from LightGBM to DL in main_signal.py — just change the import:
  OLD: from pipeline.inference import InferenceEngine
  NEW: from transformer.inference_dl import DLInferenceEngine as InferenceEngine
══════════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def mode_download(args):
    from .data_fetcher import build_training_dataset, DEFAULT_SYMBOLS
    syms = args.symbols or DEFAULT_SYMBOLS
    print(f"\nDownloading {len(syms)} symbols × {args.days} days "
          f"({args.interval}) using {args.workers} workers...")
    df = build_training_dataset(
        symbols       = syms,
        interval      = args.interval,
        lookback_days = args.days,
        cache         = not args.no_cache,
        n_workers     = args.workers,
    )
    print(f"\nDownload complete: {df.shape}")
    for sym, cnt in df.groupby("symbol").size().items():
        print(f"  {sym:<14} {cnt:>8,} candles")


def mode_labels(args):
    from .data_fetcher import build_training_dataset, load_from_parquet_dir, DEFAULT_SYMBOLS
    from .config_dl import DL_DATA_DIR, SEQ
    from ...Training_package.features_extended import engineer_features_extended
    from .labels_dual import generate_dual_labels

    parquet_path = DL_DATA_DIR / f"training_{args.interval}_{args.days}d.parquet"

    if args.from_parquet:
        # Load all raw *.parquet files from transformer/data/
        # Excludes already-processed files (training_*.parquet, labelled_*.parquet)
        raw_files = [
            p for p in DL_DATA_DIR.glob("*.parquet")
            if not p.stem.startswith(("training_", "labelled_"))
        ]
        if raw_files:
            logger.info(f"Loading {len(raw_files)} raw parquet(s) from {DL_DATA_DIR}")
            raw = load_from_parquet_dir(DL_DATA_DIR,
                                        pattern="*_merged.parquet",
                                        symbols=args.symbols)
        elif parquet_path.exists():
            logger.info(f"Loading combined training file: {parquet_path}")
            raw = pd.read_parquet(parquet_path)
        else:
            logger.error(
                f"No parquet files found in {DL_DATA_DIR}. "
                f"Run: python -m transformer.runpipeline --mode download"
            )
            sys.exit(1)
    elif parquet_path.exists() and not args.no_cache:
        logger.info(f"Loading cached training data: {parquet_path}")
        raw = pd.read_parquet(parquet_path)
    else:
        syms = args.symbols or DEFAULT_SYMBOLS
        raw = build_training_dataset(
            symbols=syms, interval=args.interval,
            lookback_days=args.days, n_workers=args.workers,
        )

    logger.info(f"Loaded: {raw.shape} | {raw['symbol'].nunique()} symbols")
    logger.info("Running extended feature engineering...")
    feat_df = engineer_features_extended(raw, timeframe=args.interval)

    logger.info("Generating dual labels...")
    labelled = generate_dual_labels(feat_df, timeframe=args.interval)

    out_path = DL_DATA_DIR / f"labelled_{args.interval}_{args.days}d.parquet"
    labelled.to_parquet(out_path, index=False)
    logger.info(f"Labelled dataset saved → {out_path}")
    print(f"\nShape: {labelled.shape}")
    print(f"Triple barrier:\n{labelled['label_mapped'].value_counts().sort_index()}")
    print(f"\nFixed ±2%:\n{labelled['label_fixed_mapped'].value_counts().sort_index()}")


def mode_train(args):
    from .config_dl import DL_DATA_DIR, DEVICE

    parquet_path = DL_DATA_DIR / f"labelled_{args.interval}_{args.days}d.parquet"
    if not parquet_path.exists():
        logger.info("Labelled data not found — running labels mode first")
        mode_labels(args)

    logger.info(f"Loading labelled dataset: {parquet_path}")
    df = pd.read_parquet(parquet_path)
    df = df[df["label_mapped"] >= 0].copy()
    logger.info(f"Valid training rows: {len(df):,}")

    from .train_dl import train
    dev = torch.device(args.device) if args.device else DEVICE
    train(df, device=dev)


def mode_test_inference(args):
    from .inference_dl import DLInferenceEngine
    from .config_dl import SEQ, DL_TRAIN

    logger.info("Testing DLInferenceEngine load + forward pass...")
    engine = DLInferenceEngine(mc_samples=5)   # small for quick test
    logger.info("Engine loaded successfully")

    # Build a fake buffer of 300 candles
    n = 300
    fake_buf = []
    price = 50000.0
    for i in range(n):
        price *= (1 + np.random.randn() * 0.001)
        fake_buf.append({
            "timestamp":       pd.Timestamp.now() - pd.Timedelta(minutes=15 * (n - i)),
            "open":            price * 0.9995,
            "high":            price * 1.001,
            "low":             price * 0.999,
            "close":           price,
            "volume":          np.random.uniform(100, 1000),
            "quote_volume":    price * np.random.uniform(100, 1000),
            "taker_buy_quote": price * np.random.uniform(50, 500),
            "trades":          np.random.randint(100, 1000),
            "funding_rate":    np.random.uniform(-0.001, 0.001),
            "oi_usd":          1e9 * np.random.uniform(0.8, 1.2),
            "oi_contracts":    1e4 * np.random.uniform(0.8, 1.2),
        })

    df     = pd.DataFrame(fake_buf)
    result = engine.predict("BTCUSDT", df, market_return=0.001)

    if result is None:
        print("✓ predict() returned None (HOLD / suppressed — expected for random data)")
    else:
        print(f"✓ predict() returned: {result['signal'].upper()} "
              f"| p_long={result['p_long']:.3f} "
              f"| p_short={result['p_short']:.3f} "
              f"| unc={result.get('uncertainty', 'n/a'):.3f}")
    print("\nDLInferenceEngine integration test PASSED ✅")


def main():
    parser = argparse.ArgumentParser(description="DL Multi-Scale Transformer Pipeline")
    parser.add_argument("--mode",
                        choices=["download", "labels", "train", "test-inference"],
                        default="train")
    parser.add_argument("--interval",     default="15m")
    parser.add_argument("--days",         type=int, default=1825,
                        help="Look-back window in days (default: 1825 = 5 years)")
    parser.add_argument("--workers",      type=int, default=4,
                        help="Concurrent download threads (default: 4)")
    parser.add_argument("--symbols",      nargs="*", default=None)
    parser.add_argument("--device",       default=None)
    parser.add_argument("--no-cache",     action="store_true")
    parser.add_argument("--from-parquet", action="store_true",
                        help="Load all *.parquet from transformer/data/ directly")
    args = parser.parse_args()

    dispatch = {
        "download":       mode_download,
        "labels":         mode_labels,
        "train":          mode_train,
        "test-inference": mode_test_inference,
    }
    dispatch[args.mode](args)


if __name__ == "__main__":
    main()