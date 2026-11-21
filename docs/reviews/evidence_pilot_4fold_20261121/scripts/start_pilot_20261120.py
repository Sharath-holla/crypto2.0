"""Write the fresh 2026-11-20 session contract ($7 cap, 5-hour window) and owner authorization."""
import importlib.util, json, hashlib
from datetime import UTC, datetime, timedelta
spec = importlib.util.spec_from_file_location("d", "/Users/cortex/.crypto2-transfer/pilot_4fold_20261118.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
w = m.wallet(); now = datetime.now(UTC)
overnight = round(12.894 - w, 4)  # storage since the 19 Nov 16:26Z reading
s = {"all_in_usd_per_hour_upper_bound": 1.72, "compute_usd_per_hour": 1.4, "hard_stop_utc": (now + timedelta(hours=5)).isoformat(),
     "identified_cumulative_usd_at_start": round(6.11 + overnight, 2),
     "max_session_usd": 7.0, "session_start_utc": now.isoformat(), "wallet_usd_at_start": w}
assert not m.SESSION_PATH.exists() and not m.AUTHORIZATION_PATH.exists() and w - s["max_session_usd"] > 1
m.write(m.SESSION_PATH, s); m.SESSION_PATH.chmod(0o600)
m.write(m.AUTHORIZATION_PATH, {"instruction": "Owner 2026-11-20 ~16:56Z: 'continue my crypto project and start doing training'; chose '$7 cap, 5 hours'. EU-SE-1 network volume.",
    "new_compute_or_training_authorized": True, "session_contract": str(m.SESSION_PATH), "supersedes": ["OWNER_STOP_20261119.json"],
    "authorization_sha256": hashlib.sha256(m.AUTHORIZATION_NOTE.encode()).hexdigest(), "utc": now.isoformat()})
print(json.dumps(s))
