"""Create local secrets without displaying them or changing existing configuration."""

import base64
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env = root / ".env"
if not env.exists():
    template = (root / ".env.example").read_text(encoding="utf-8")
    template = template.replace("replace-with-at-least-32-random-characters", secrets.token_urlsafe(48))
    template = template.replace("replace-with-a-long-unique-password", secrets.token_urlsafe(24))
    template = template.replace("replace-with-a-database-password", secrets.token_urlsafe(32))
    template = template.replace("replace-with-an-independent-runner-token", secrets.token_urlsafe(48))
    template = template.replace(
        "replace-with-base64-encoded-32-byte-key", base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    )
    env.write_text(template, encoding="utf-8")
    print("Created private .env. Read OWNER_EMAIL and OWNER_PASSWORD there to sign in.")
else:
    print("Existing .env preserved.")
    current = env.read_text(encoding="utf-8")
    if "AI_SPENDING_MODE=" not in current:
        with env.open("a", encoding="utf-8") as output:
            output.write("\nAI_SPENDING_MODE=ZERO_COST_ONLY\n")
    if "RUNNER_TOKEN=" not in current:
        with env.open("a", encoding="utf-8") as output:
            output.write("\nRUNNER_TOKEN=" + secrets.token_urlsafe(48) + "\n")
    if "DB_PASSWORD=" not in current:
        with env.open("a", encoding="utf-8") as output:
            output.write("\nDB_PASSWORD=" + secrets.token_urlsafe(32) + "\n")
    if "PROVIDER_SECRET_KEY=" not in current:
        with env.open("a", encoding="utf-8") as output:
            output.write(
                "\nPROVIDER_SECRET_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode() + "\n"
            )
        print("Added an independent provider vault key to private .env.")
(root / "data").mkdir(exist_ok=True)
