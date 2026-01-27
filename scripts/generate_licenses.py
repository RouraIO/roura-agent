#!/usr/bin/env python3
"""
Generate license keys for Roura Agent.

Usage:
    # Generate a single PRO license
    python scripts/generate_licenses.py user@example.com PRO

    # Generate a lifetime PRO license
    python scripts/generate_licenses.py user@example.com PRO --lifetime

    # Generate with custom expiry (days)
    python scripts/generate_licenses.py user@example.com PRO --days 365

    # Generate batch licenses from a file
    python scripts/generate_licenses.py --batch emails.txt PRO --lifetime

    # Send license via email
    python scripts/generate_licenses.py user@example.com PRO --send
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.payment_webhook import (
    generate_license_key,
    send_license_email,
    store_license,
    load_env,
    License,
)


def main():
    parser = argparse.ArgumentParser(description='Generate Roura Agent license keys')
    parser.add_argument('email', nargs='?', help='Customer email address')
    parser.add_argument('tier', nargs='?', default='PRO', choices=['PRO', 'ENTERPRISE'],
                       help='License tier (default: PRO)')
    parser.add_argument('--lifetime', action='store_true', help='Generate perpetual license')
    parser.add_argument('--days', type=int, default=365, help='License duration in days (default: 365)')
    parser.add_argument('--batch', type=str, help='File with email addresses (one per line)')
    parser.add_argument('--send', action='store_true', help='Send license via email')
    parser.add_argument('--name', type=str, default='Customer', help='Customer name for email')

    args = parser.parse_args()

    # Load environment for email sending
    load_env()

    emails = []

    if args.batch:
        # Batch mode
        with open(args.batch) as f:
            emails = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    elif args.email:
        emails = [args.email]
    else:
        parser.print_help()
        sys.exit(1)

    duration_days = None if args.lifetime else args.days
    generated = []

    print(f"\nGenerating {len(emails)} {args.tier} license(s)...\n")
    print("-" * 70)

    for email in emails:
        license = generate_license_key(email, args.tier, duration_days)
        generated.append(license)
        store_license(license)

        expiry = license.valid_until if license.valid_until else "PERPETUAL"
        print(f"Email: {email}")
        print(f"Key:   {license.key}")
        print(f"Valid: {expiry}")
        print("-" * 70)

        if args.send:
            print(f"Sending email to {email}...")
            if send_license_email(license, args.name):
                print("  ✓ Email sent successfully")
            else:
                print("  ✗ Failed to send email")
            print("-" * 70)

    print(f"\n✓ Generated {len(generated)} license(s)")

    # Output as copyable format
    print("\n=== Copy-paste format ===\n")
    for lic in generated:
        print(f"ROURA_LICENSE_KEY={lic.key}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
