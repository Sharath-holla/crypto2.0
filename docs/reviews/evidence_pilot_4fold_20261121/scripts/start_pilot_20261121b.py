"""Write the 2026-11-21b session contract: all remaining folds, up to $8.40, 8-hour window, $1 wallet floor, $18 lifetime cap."""
import importlib.util, json, hashlib
from datetime import UTC, datetime, timedelta
spec = importlib.util.spec_from_file_location("d", "/Users/cortex/.crypto2-transfer/pilot_4fold_20261118.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
prev = json.loads((m.PILOT / "pilot-session-20261121.json").read_text())
w = m.wallet(); now = datetime.now(UTC)
cum = round(prev["identified_cumulative_usd_at_start"] + (prev["wallet_usd_at_start"] - w) + 0.005, 2)
cap = round(min(8.40, 18 - cum - 0.01, w - 1.0), 2)
s = {"all_in_usd_per_hour_upper_bound": 1.72, "compute_usd_per_hour": 1.4, "hard_stop_utc": (now + timedelta(hours=8)).isoformat(),
     "identified_cumulative_usd_at_start": cum, "max_session_usd": cap, "session_start_utc": now.isoformat(), "wallet_usd_at_start": w}
assert not m.SESSION_PATH.exists() and not m.AUTHORIZATION_PATH.exists() and cap > 1 and cap + cum <= 18
m.write(m.SESSION_PATH, s); m.SESSION_PATH.chmod(0o600)
m.write(m.AUTHORIZATION_PATH, {"instruction": "Owner 2026-11-21 ~05:55Z: 'use that 9.41 as well just train all folds and save all'; told of the $1 wallet floor and $18 lifetime cap; chose 'Spend up to $8.40, 8-hour limit'.",
    "new_compute_or_training_authorized": True, "session_contract": str(m.SESSION_PATH), "supersedes": ["OWNER_STOP_20261121.json"],
    "authorization_sha256": hashlib.sha256(m.AUTHORIZATION_NOTE.encode()).hexdigest(), "utc": now.isoformat()})
print(json.dumps(s))
