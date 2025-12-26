#!/usr/bin/env python3
"""Test that perch interval configuration works correctly."""

import os
import sys

# Test different configurations
test_cases = [
    (None, 60),  # Default: 60 minutes
    ("30", 30),  # 30 minutes
    ("120", 120),  # 2 hours
    ("5", 5),  # 5 minutes for testing
]

print("Testing LARES_PERCH_INTERVAL_MINUTES configuration...")
print("=" * 50)

for env_value, expected in test_cases:
    # Set or unset the environment variable
    if env_value is not None:
        os.environ["LARES_PERCH_INTERVAL_MINUTES"] = env_value
        print(f"\nTest: LARES_PERCH_INTERVAL_MINUTES='{env_value}'")
    else:
        os.environ.pop("LARES_PERCH_INTERVAL_MINUTES", None)
        print(f"\nTest: LARES_PERCH_INTERVAL_MINUTES not set (using default)")

    # Import the module to get the constant value
    # We need to reload it to pick up the new env var
    if 'lares.discord_bot' in sys.modules:
        del sys.modules['lares.discord_bot']

    # Add src to path if needed
    if 'src' not in sys.path:
        sys.path.insert(0, 'src')

    try:
        from lares.discord_bot import PERCH_INTERVAL_MINUTES

        print(f"  Expected: {expected} minutes")
        print(f"  Got: {PERCH_INTERVAL_MINUTES} minutes")

        if PERCH_INTERVAL_MINUTES == expected:
            print("  ✅ PASS")
        else:
            print("  ❌ FAIL")
            sys.exit(1)

    except ImportError as e:
        print(f"  ❌ Import failed: {e}")
        print("  Make sure to run this in the virtual environment")
        sys.exit(1)

print("\n" + "=" * 50)
print("✅ All tests passed!")
print("\nUsage examples for .env file:")
print("  LARES_PERCH_INTERVAL_MINUTES=30    # Every 30 minutes")
print("  LARES_PERCH_INTERVAL_MINUTES=60    # Every hour (default)")
print("  LARES_PERCH_INTERVAL_MINUTES=120   # Every 2 hours")
print("  LARES_PERCH_INTERVAL_MINUTES=1440  # Once per day")