#!/usr/bin/env python3
"""
Roura Agent Payment Webhook Handler

This script handles Stripe webhooks for license purchases and sends
license keys via SendGrid email.

Usage:
    # Development (with ngrok)
    ngrok http 8000
    python scripts/payment_webhook.py

    # Production (deploy to your server)
    gunicorn payment_webhook:app -b 0.0.0.0:8000
"""

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# Load environment from .env.stripe
def load_env():
    env_file = os.path.join(os.path.dirname(__file__), '..', '.env.stripe')
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key, value)

load_env()

# Configuration
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY', '')
FROM_EMAIL = os.environ.get('FROM_EMAIL', 'license@roura.io')
FROM_NAME = os.environ.get('FROM_NAME', 'Roura Agent')

# Pricing (in cents)
PRICING = {
    'pro_monthly': {
        'price_id': 'price_pro_monthly',
        'amount': 1900,  # $19/month
        'tier': 'PRO',
        'duration_days': 30,
    },
    'pro_annual': {
        'price_id': 'price_pro_annual',
        'amount': 15900,  # $159/year (2 months free)
        'tier': 'PRO',
        'duration_days': 365,
    },
    'pro_lifetime': {
        'price_id': 'price_pro_lifetime',
        'amount': 29900,  # $299 lifetime
        'tier': 'PRO',
        'duration_days': None,  # Perpetual
    },
    'enterprise_annual': {
        'price_id': 'price_enterprise_annual',
        'amount': 49900,  # $499/year
        'tier': 'ENTERPRISE',
        'duration_days': 365,
    },
}


@dataclass
class License:
    """Generated license key."""
    key: str
    tier: str
    email: str
    valid_until: Optional[str]
    created_at: str


def generate_license_key(email: str, tier: str, duration_days: Optional[int]) -> License:
    """
    Generate a license key for a customer.

    Format: TIER-EMAIL-EXPIRY
    Example: PRO-user@example.com-2027-01-27
    """
    if duration_days is None:
        expiry = "PERPETUAL"
        valid_until = None
    else:
        expiry_date = datetime.utcnow() + timedelta(days=duration_days)
        expiry = expiry_date.strftime("%Y-%m-%d")
        valid_until = expiry

    key = f"{tier}-{email}-{expiry}"

    return License(
        key=key,
        tier=tier,
        email=email,
        valid_until=valid_until,
        created_at=datetime.utcnow().isoformat(),
    )


def send_license_email(license: License, customer_name: str) -> bool:
    """Send license key via SendGrid."""
    if not SENDGRID_API_KEY:
        print("ERROR: SENDGRID_API_KEY not set")
        return False

    expiry_text = license.valid_until if license.valid_until else "Never (Lifetime)"

    html_content = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h1 style="color: #2563eb;">Welcome to Roura Agent {license.tier}!</h1>

        <p>Hi {customer_name},</p>

        <p>Thank you for your purchase! Here's your license key:</p>

        <div style="background: #f3f4f6; border-radius: 8px; padding: 20px; margin: 20px 0; font-family: monospace; font-size: 14px; word-break: break-all;">
            {license.key}
        </div>

        <h2 style="color: #374151;">Quick Setup</h2>

        <p>Add this to your <code>.env</code> file:</p>

        <pre style="background: #1f2937; color: #f9fafb; padding: 15px; border-radius: 8px; overflow-x: auto;">
ROURA_LICENSE_KEY={license.key}</pre>

        <p>Or set it as an environment variable:</p>

        <pre style="background: #1f2937; color: #f9fafb; padding: 15px; border-radius: 8px; overflow-x: auto;">
export ROURA_LICENSE_KEY="{license.key}"</pre>

        <h2 style="color: #374151;">License Details</h2>

        <table style="width: 100%; border-collapse: collapse;">
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;"><strong>Tier</strong></td>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{license.tier}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;"><strong>Email</strong></td>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{license.email}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;"><strong>Valid Until</strong></td>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{expiry_text}</td>
            </tr>
        </table>

        <h2 style="color: #374151; margin-top: 30px;">What's Included</h2>

        <ul style="line-height: 1.8;">
            <li>OpenAI GPT-4 provider support</li>
            <li>Anthropic Claude provider support</li>
            <li>Autonomous fix loops (test.fix, build.fix, typecheck.fix)</li>
            <li>GitHub and Jira integrations</li>
            <li>Priority email support</li>
        </ul>

        <p style="margin-top: 30px; color: #6b7280; font-size: 14px;">
            Questions? Reply to this email or visit <a href="https://roura.io/support">roura.io/support</a>
        </p>

        <p style="color: #6b7280; font-size: 14px;">
            Happy coding!<br>
            The Roura Team
        </p>
    </div>
    """

    text_content = f"""
Welcome to Roura Agent {license.tier}!

Hi {customer_name},

Thank you for your purchase! Here's your license key:

{license.key}

Quick Setup
-----------
Add this to your .env file:

ROURA_LICENSE_KEY={license.key}

Or set it as an environment variable:

export ROURA_LICENSE_KEY="{license.key}"

License Details
---------------
Tier: {license.tier}
Email: {license.email}
Valid Until: {expiry_text}

What's Included
---------------
- OpenAI GPT-4 provider support
- Anthropic Claude provider support
- Autonomous fix loops (test.fix, build.fix, typecheck.fix)
- GitHub and Jira integrations
- Priority email support

Questions? Reply to this email or visit https://roura.io/support

Happy coding!
The Roura Team
"""

    payload = {
        "personalizations": [{
            "to": [{"email": license.email, "name": customer_name}],
            "subject": f"Your Roura Agent {license.tier} License Key"
        }],
        "from": {"email": FROM_EMAIL, "name": FROM_NAME},
        "reply_to": {"email": FROM_EMAIL, "name": FROM_NAME},
        "content": [
            {"type": "text/plain", "value": text_content},
            {"type": "text/html", "value": html_content}
        ]
    }

    try:
        req = Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=json.dumps(payload).encode('utf-8'),
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        with urlopen(req) as response:
            print(f"Email sent successfully to {license.email}")
            return True
    except HTTPError as e:
        print(f"SendGrid error: {e.code} - {e.read().decode()}")
        return False
    except Exception as e:
        print(f"Email error: {e}")
        return False


def verify_stripe_signature(payload: bytes, signature: str) -> bool:
    """Verify Stripe webhook signature."""
    if not STRIPE_WEBHOOK_SECRET:
        print("WARNING: STRIPE_WEBHOOK_SECRET not set, skipping verification")
        return True

    try:
        # Parse signature header
        elements = dict(item.split('=', 1) for item in signature.split(','))
        timestamp = elements.get('t')
        v1_signature = elements.get('v1')

        if not timestamp or not v1_signature:
            return False

        # Check timestamp is recent (within 5 minutes)
        if abs(time.time() - int(timestamp)) > 300:
            print("Webhook timestamp too old")
            return False

        # Compute expected signature
        signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
        expected = hmac.new(
            STRIPE_WEBHOOK_SECRET.encode('utf-8'),
            signed_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, v1_signature)
    except Exception as e:
        print(f"Signature verification error: {e}")
        return False


def handle_checkout_completed(event_data: dict) -> bool:
    """Handle successful checkout session."""
    session = event_data.get('object', {})

    customer_email = session.get('customer_email') or session.get('customer_details', {}).get('email')
    customer_name = session.get('customer_details', {}).get('name', 'Customer')

    if not customer_email:
        print("ERROR: No customer email in checkout session")
        return False

    # Get the price/product info
    metadata = session.get('metadata', {})
    plan = metadata.get('plan', 'pro_lifetime')  # Default to lifetime

    pricing = PRICING.get(plan, PRICING['pro_lifetime'])

    # Generate license
    license = generate_license_key(
        email=customer_email,
        tier=pricing['tier'],
        duration_days=pricing['duration_days']
    )

    # Log the purchase
    print(f"New purchase: {customer_email} - {plan} - {license.key}")

    # Store license (in production, save to database)
    store_license(license)

    # Send email
    return send_license_email(license, customer_name)


def store_license(license: License):
    """Store license to file (replace with database in production)."""
    licenses_file = os.path.join(os.path.dirname(__file__), '..', 'licenses.json')

    try:
        if os.path.exists(licenses_file):
            with open(licenses_file) as f:
                licenses = json.load(f)
        else:
            licenses = []

        licenses.append({
            'key': license.key,
            'tier': license.tier,
            'email': license.email,
            'valid_until': license.valid_until,
            'created_at': license.created_at,
        })

        with open(licenses_file, 'w') as f:
            json.dump(licenses, f, indent=2)

        print(f"License stored: {license.key}")
    except Exception as e:
        print(f"Error storing license: {e}")


class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP handler for Stripe webhooks."""

    def do_POST(self):
        if self.path == '/webhook':
            content_length = int(self.headers.get('Content-Length', 0))
            payload = self.rfile.read(content_length)
            signature = self.headers.get('Stripe-Signature', '')

            # Verify signature
            if not verify_stripe_signature(payload, signature):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Invalid signature')
                return

            try:
                event = json.loads(payload)
                event_type = event.get('type')

                print(f"Received event: {event_type}")

                if event_type == 'checkout.session.completed':
                    success = handle_checkout_completed(event.get('data', {}))
                    if success:
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b'OK')
                    else:
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(b'Failed to process')
                else:
                    # Acknowledge other events
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'OK')

            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Invalid JSON')
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        """Health check endpoint."""
        if self.path == '/health':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")


def main():
    """Run the webhook server."""
    port = int(os.environ.get('PORT', 8000))

    print(f"""
╔════════════════════════════════════════════════════════════════╗
║           Roura Agent Payment Webhook Server                   ║
╠════════════════════════════════════════════════════════════════╣
║  Status: {'✓ Ready' if STRIPE_SECRET_KEY and SENDGRID_API_KEY else '✗ Missing config'}
║  Port: {port}
║  Webhook endpoint: http://localhost:{port}/webhook
║  Health check: http://localhost:{port}/health
╠════════════════════════════════════════════════════════════════╣
║  Config:                                                       ║
║  - Stripe: {'✓ Configured' if STRIPE_SECRET_KEY else '✗ STRIPE_SECRET_KEY missing'}
║  - SendGrid: {'✓ Configured' if SENDGRID_API_KEY else '✗ SENDGRID_API_KEY missing'}
║  - From: {FROM_EMAIL}
╚════════════════════════════════════════════════════════════════╝

For development, use ngrok to expose this endpoint:
  ngrok http {port}

Then add the ngrok URL to Stripe webhooks:
  https://dashboard.stripe.com/webhooks

Press Ctrl+C to stop.
""")

    server = HTTPServer(('0.0.0.0', port), WebhookHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == '__main__':
    main()
