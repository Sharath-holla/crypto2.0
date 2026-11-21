"""Re-base the 2026-11-21b contract: same owner approval ($8.40 total, hard stop 14:42:53Z), remaining budget only.

The wallet policy projects elapsed-time x all-in rate, so a contract started at 06:42Z blocked new folds by 11:11Z
although real spend was far lower. This contract spends only what is left of the approved $8.39.
"""
import importlib.util, json, hashlib
from datetime import UTC, datetime
spec = importlib.util.spec_from_file_location("d", "/Users/cortex/.crypto2-transfer/pilot_4fold_20261118.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
prev = json.loads((m.PILOT / "pilot-session-20261121d.json").read_text())
w = m.wallet(); now = datetime.now(UTC)
spent = round(prev["wallet_usd_at_start"] - w, 4)
cap = round(min(prev["max_session_usd"] - spent, w - 1.0, 18 - (prev["identified_cumulative_usd_at_start"] + spent) - 0.01), 2)
s = {"all_in_usd_per_hour_upper_bound": 1.72, "compute_usd_per_hour": 1.4, "hard_stop_utc": prev["hard_stop_utc"],
     "identified_cumulative_usd_at_start": round(prev["identified_cumulative_usd_at_start"] + spent, 2),
     "max_session_usd": cap, "session_start_utc": now.isoformat(), "wallet_usd_at_start": w}
assert not m.SESSION_PATH.exists() and not m.AUTHORIZATION_PATH.exists() and cap > 1 and s["max_session_usd"] + s["identified_cumulative_usd_at_start"] <= 18
m.write(m.SESSION_PATH, s); m.SESSION_PATH.chmod(0o600)
m.write(m.AUTHORIZATION_PATH, {"instruction": "Continuation of OWNER_AUTHORIZATION_20261121b via 20261121c/d (owner chose 'Spend up to $8.40, 8-hour limit'). Same total cap and hard stop; budget re-based to the unspent remainder.",
    "new_compute_or_training_authorized": True, "session_contract": str(m.SESSION_PATH), "continues": "pilot-session-20261121d.json", "spent_in_previous_segment_usd": spent,
    "authorization_sha256": hashlib.sha256(m.AUTHORIZATION_NOTE.encode()).hexdigest(), "utc": now.isoformat()})
print(json.dumps(s))
