#!/usr/bin/env python3
"""
Production webhook server for Roura Agent license delivery.

Environment variables required:
    STRIPE_WEBHOOK_SECRET
    SENDGRID_API_KEY
    FROM_EMAIL (default: license@roura.io)
    FROM_NAME (default: Roura Agent)
    PORT (default: 8000)
"""

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from flask import Flask, request, jsonify

app = Flask(__name__)

# Configuration from environment
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY', '')
FROM_EMAIL = os.environ.get('FROM_EMAIL', 'license@roura.io')
FROM_NAME = os.environ.get('FROM_NAME', 'Roura Agent')

# Pricing configuration
PRICING = {
    'pro_monthly': {'tier': 'PRO', 'duration_days': 30},
    'pro_annual': {'tier': 'PRO', 'duration_days': 365},
    'pro_lifetime': {'tier': 'PRO', 'duration_days': None},
    'enterprise_annual': {'tier': 'ENTERPRISE', 'duration_days': 365},
}

# Track processed events to prevent duplicate emails (in-memory cache)
# Note: For production with multiple instances, use Redis or a database
processed_events: set[str] = set()


def generate_license_key(email: str, tier: str, duration_days: int | None) -> dict:
    """Generate a license key."""
    if duration_days is None:
        expiry = "PERPETUAL"
        valid_until = None
    else:
        expiry_date = datetime.utcnow() + timedelta(days=duration_days)
        expiry = expiry_date.strftime("%Y-%m-%d")
        valid_until = expiry

    key = f"{tier}-{email}-{expiry}"
    return {
        'key': key,
        'tier': tier,
        'email': email,
        'valid_until': valid_until,
    }


def send_license_email(license: dict, customer_name: str) -> bool:
    """Send license key via SendGrid."""
    if not SENDGRID_API_KEY:
        print("ERROR: SENDGRID_API_KEY not set")
        return False

    expiry_text = license['valid_until'] if license['valid_until'] else "Never (Lifetime)"

    html_content = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h1 style="color: #2563eb;">Welcome to Roura Agent {license['tier']}!</h1>
        <p>Hi {customer_name},</p>
        <p>Thank you for your purchase! Here's your license key:</p>
        <div style="background: #f3f4f6; border-radius: 8px; padding: 20px; margin: 20px 0; font-family: monospace; font-size: 14px; word-break: break-all;">
            {license['key']}
        </div>
        <h2 style="color: #374151;">Quick Setup</h2>
        <p>Add this to your <code>.env</code> file:</p>
        <pre style="background: #1f2937; color: #f9fafb; padding: 15px; border-radius: 8px;">ROURA_LICENSE_KEY={license['key']}</pre>
        <p><strong>Valid Until:</strong> {expiry_text}</p>
        <p style="margin-top: 30px; color: #6b7280;">Happy coding!<br>The Roura Team</p>
    </div>
    """

    text_content = f"""Welcome to Roura Agent {license['tier']}!

Your license key: {license['key']}

Add to your .env file:
ROURA_LICENSE_KEY={license['key']}

Valid Until: {expiry_text}

Happy coding!
The Roura Team"""

    payload = {
        "personalizations": [{
            "to": [{"email": license['email'], "name": customer_name}],
            "subject": f"Your Roura Agent {license['tier']} License Key"
        }],
        "from": {"email": FROM_EMAIL, "name": FROM_NAME},
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
            print(f"Email sent to {license['email']}")
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
        print("WARNING: No webhook secret, skipping verification")
        return True

    try:
        elements = dict(item.split('=', 1) for item in signature.split(','))
        timestamp = elements.get('t')
        v1_signature = elements.get('v1')

        if not timestamp or not v1_signature:
            return False

        if abs(time.time() - int(timestamp)) > 300:
            return False

        signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
        expected = hmac.new(
            STRIPE_WEBHOOK_SECRET.encode('utf-8'),
            signed_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, v1_signature)
    except Exception as e:
        print(f"Signature error: {e}")
        return False


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'sendgrid': bool(SENDGRID_API_KEY),
        'webhook_secret': bool(STRIPE_WEBHOOK_SECRET),
    })


@app.route('/webhook', methods=['POST'])
def webhook():
    """Stripe webhook endpoint."""
    payload = request.get_data()
    signature = request.headers.get('Stripe-Signature', '')

    if not verify_stripe_signature(payload, signature):
        return jsonify({'error': 'Invalid signature'}), 400

    try:
        event = json.loads(payload)
        event_id = event.get('id')
        event_type = event.get('type')
        print(f"Event: {event_type} ({event_id})")

        # Check for duplicate events
        if event_id in processed_events:
            print(f"Duplicate event {event_id}, skipping")
            return jsonify({'status': 'ok', 'message': 'Already processed'})

        if event_type == 'checkout.session.completed':
            session = event.get('data', {}).get('object', {})
            customer_email = session.get('customer_email') or session.get('customer_details', {}).get('email')
            customer_name = session.get('customer_details', {}).get('name', 'Customer')
            plan = session.get('metadata', {}).get('plan', 'pro_lifetime')

            if not customer_email:
                return jsonify({'error': 'No email'}), 400

            pricing = PRICING.get(plan, PRICING['pro_lifetime'])
            license = generate_license_key(customer_email, pricing['tier'], pricing['duration_days'])

            print(f"License: {license['key']}")

            if send_license_email(license, customer_name):
                # Mark event as processed
                processed_events.add(event_id)
                # Keep cache bounded (remove old entries if too large)
                if len(processed_events) > 10000:
                    # Remove oldest half
                    to_remove = list(processed_events)[:5000]
                    for item in to_remove:
                        processed_events.discard(item)
                return jsonify({'status': 'ok', 'license': license['key']})
            else:
                return jsonify({'error': 'Email failed'}), 500

        return jsonify({'status': 'ok'})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/', methods=['GET'])
def index():
    """Root endpoint."""
    return jsonify({
        'service': 'Roura Agent License Server',
        'status': 'running'
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    print(f"Starting on port {port}")
    app.run(host='0.0.0.0', port=port)
