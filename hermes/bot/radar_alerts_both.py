#!/usr/bin/env python3
"""Send radar alerts to both @NpzFuel_Bot and @BPLAlert_bot subscribers."""
import subprocess
import sys

REPO = "/root/npz-tactical-map"
SCRIPT = f"{REPO}/hermes/bot/radar_alerts.py"

# Run for @NpzFuel_Bot
print("=== @NpzFuel_Bot ===")
r1 = subprocess.run([sys.executable, SCRIPT, "--send", "--bot", "fuel"],
                     capture_output=True, text=True, timeout=60)
print(r1.stdout)
if r1.stderr:
    print("STDERR:", r1.stderr[:200])

# Run for @BPLAlert_bot
print("\n=== @BPLAlert_bot ===")
r2 = subprocess.run([sys.executable, SCRIPT, "--send", "--bot", "bpl"],
                     capture_output=True, text=True, timeout=60)
print(r2.stdout)
if r2.stderr:
    print("STDERR:", r2.stderr[:200])

print(f"\nDone. fuel={r1.returncode}, bpl={r2.returncode}")
