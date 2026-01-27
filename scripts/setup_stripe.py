#!/usr/bin/env python3
"""
Set up Stripe products and prices for Roura Agent.

This script creates the products and prices in your Stripe account.
Run it once to set up your payment infrastructure.

Usage:
    python scripts/setup_stripe.py

Requires:
    STRIPE_SECRET_KEY in .env.stripe
"""

import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode

# Load environment
def load_env():
    env_file = Path(__file__).parent.parent / '.env.stripe'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key, value)

load_env()

STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')

if not STRIPE_SECRET_KEY or STRIPE_SECRET_KEY.startswith('sk_test_PASTE'):
    print("ERROR: Please set STRIPE_SECRET_KEY in .env.stripe")
    print("\nGet your key from: https://dashboard.stripe.com/apikeys")
    sys.exit(1)


def stripe_request(method: str, endpoint: str, data: dict = None) -> dict:
    """Make a request to Stripe API."""
    url = f"https://api.stripe.com/v1/{endpoint}"

    headers = {
        "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    body = None
    if data:
        body = urlencode(data).encode('utf-8')

    req = Request(url, data=body, headers=headers, method=method)

    try:
        with urlopen(req) as response:
            return json.loads(response.read())
    except HTTPError as e:
        error = json.loads(e.read())
        print(f"Stripe API error: {error}")
        raise


def create_product(name: str, description: str, metadata: dict = None) -> str:
    """Create a Stripe product."""
    data = {
        "name": name,
        "description": description,
    }
    if metadata:
        for key, value in metadata.items():
            data[f"metadata[{key}]"] = value

    result = stripe_request("POST", "products", data)
    return result["id"]


def create_price(product_id: str, amount: int, currency: str = "usd",
                recurring: dict = None, metadata: dict = None) -> str:
    """Create a Stripe price."""
    data = {
        "product": product_id,
        "unit_amount": amount,
        "currency": currency,
    }

    if recurring:
        for key, value in recurring.items():
            data[f"recurring[{key}]"] = value

    if metadata:
        for key, value in metadata.items():
            data[f"metadata[{key}]"] = value

    result = stripe_request("POST", "prices", data)
    return result["id"]


def create_checkout_link(price_id: str, success_url: str, cancel_url: str,
                        plan: str) -> str:
    """Create a Stripe payment link."""
    data = {
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        f"metadata[plan]": plan,
    }

    result = stripe_request("POST", "payment_links", data)
    return result["url"]


def main():
    print("""
╔════════════════════════════════════════════════════════════════╗
║           Roura Agent - Stripe Setup                           ║
╚════════════════════════════════════════════════════════════════╝
""")

    # Check if already set up
    try:
        existing = stripe_request("GET", "products?limit=10")
        existing_names = [p["name"] for p in existing.get("data", [])]

        if "Roura Agent Pro" in existing_names:
            print("Products already exist in Stripe. Skipping creation.")
            print("\nExisting products:")
            for p in existing.get("data", []):
                print(f"  - {p['name']} ({p['id']})")
            print("\nTo recreate, delete products in Stripe Dashboard first.")
            return list_payment_links()
    except Exception as e:
        print(f"Note: {e}")

    print("Creating Stripe products and prices...\n")

    # Create Pro product
    print("Creating Roura Agent Pro product...")
    pro_product_id = create_product(
        name="Roura Agent Pro",
        description="Professional features: OpenAI, Anthropic, autonomous fix loops, integrations",
        metadata={"tier": "PRO"}
    )
    print(f"  ✓ Product created: {pro_product_id}")

    # Create Pro prices
    print("\nCreating Pro prices...")

    pro_monthly_id = create_price(
        product_id=pro_product_id,
        amount=1900,  # $19
        recurring={"interval": "month"},
        metadata={"plan": "pro_monthly"}
    )
    print(f"  ✓ Pro Monthly ($19/mo): {pro_monthly_id}")

    pro_annual_id = create_price(
        product_id=pro_product_id,
        amount=15900,  # $159
        recurring={"interval": "year"},
        metadata={"plan": "pro_annual"}
    )
    print(f"  ✓ Pro Annual ($159/yr): {pro_annual_id}")

    pro_lifetime_id = create_price(
        product_id=pro_product_id,
        amount=29900,  # $299
        metadata={"plan": "pro_lifetime"}
    )
    print(f"  ✓ Pro Lifetime ($299): {pro_lifetime_id}")

    # Create Enterprise product
    print("\nCreating Roura Agent Enterprise product...")
    enterprise_product_id = create_product(
        name="Roura Agent Enterprise",
        description="Enterprise features: team collaboration, SSO, advanced audit",
        metadata={"tier": "ENTERPRISE"}
    )
    print(f"  ✓ Product created: {enterprise_product_id}")

    # Create Enterprise price
    print("\nCreating Enterprise prices...")

    enterprise_annual_id = create_price(
        product_id=enterprise_product_id,
        amount=49900,  # $499
        recurring={"interval": "year"},
        metadata={"plan": "enterprise_annual"}
    )
    print(f"  ✓ Enterprise Annual ($499/yr): {enterprise_annual_id}")

    # Create payment links
    print("\nCreating payment links...")

    prices = {
        "pro_monthly": pro_monthly_id,
        "pro_annual": pro_annual_id,
        "pro_lifetime": pro_lifetime_id,
        "enterprise_annual": enterprise_annual_id,
    }

    links = {}
    for plan, price_id in prices.items():
        link = create_checkout_link(
            price_id=price_id,
            success_url="https://roura.io/success",
            cancel_url="https://roura.io/pricing",
            plan=plan
        )
        links[plan] = link
        print(f"  ✓ {plan}: {link}")

    # Save configuration
    config = {
        "products": {
            "pro": pro_product_id,
            "enterprise": enterprise_product_id,
        },
        "prices": prices,
        "payment_links": links,
    }

    config_file = Path(__file__).parent.parent / 'stripe_config.json'
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"\n✓ Configuration saved to {config_file}")

    print("""
╔════════════════════════════════════════════════════════════════╗
║                    Setup Complete!                             ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  Next steps:                                                   ║
║                                                                ║
║  1. Set up webhook endpoint:                                   ║
║     https://dashboard.stripe.com/webhooks                      ║
║                                                                ║
║     Add endpoint: https://your-domain.com/webhook              ║
║     Events: checkout.session.completed                         ║
║                                                                ║
║  2. Copy the webhook signing secret to .env.stripe:            ║
║     STRIPE_WEBHOOK_SECRET=whsec_...                            ║
║                                                                ║
║  3. Start the webhook server:                                  ║
║     python scripts/payment_webhook.py                          ║
║                                                                ║
║  4. Use payment links on your pricing page                     ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
""")

    return 0


def list_payment_links():
    """List existing payment links."""
    try:
        result = stripe_request("GET", "payment_links?limit=10")
        links = result.get("data", [])

        if links:
            print("\nExisting payment links:")
            for link in links:
                print(f"  - {link.get('url')} (active: {link.get('active')})")

        return 0
    except Exception as e:
        print(f"Could not list payment links: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
