#!/usr/bin/env python3
"""
Production-ready webhook server using Flask.

Deploy to Railway, Render, Fly.io, or any Docker host.

Environment variables required:
    STRIPE_SECRET_KEY
    STRIPE_WEBHOOK_SECRET
    SENDGRID_API_KEY
    FROM_EMAIL
    FROM_NAME
"""

import json
import os
from flask import Flask, request, jsonify

from payment_webhook import (
    verify_stripe_signature,
    handle_checkout_completed,
    load_env,
    STRIPE_SECRET_KEY,
    SENDGRID_API_KEY,
)

# Load environment
load_env()

app = Flask(__name__)


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'stripe_configured': bool(os.environ.get('STRIPE_SECRET_KEY')),
        'sendgrid_configured': bool(os.environ.get('SENDGRID_API_KEY')),
    })


@app.route('/webhook', methods=['POST'])
def webhook():
    """Stripe webhook endpoint."""
    payload = request.get_data()
    signature = request.headers.get('Stripe-Signature', '')

    # Verify signature
    if not verify_stripe_signature(payload, signature):
        return jsonify({'error': 'Invalid signature'}), 400

    try:
        event = json.loads(payload)
        event_type = event.get('type')

        print(f"Received event: {event_type}")

        if event_type == 'checkout.session.completed':
            success = handle_checkout_completed(event.get('data', {}))
            if success:
                return jsonify({'status': 'ok'})
            else:
                return jsonify({'error': 'Failed to process'}), 500
        else:
            # Acknowledge other events
            return jsonify({'status': 'ok'})

    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON'}), 400


@app.route('/', methods=['GET'])
def index():
    """Root endpoint."""
    return jsonify({
        'service': 'Roura Agent License Server',
        'endpoints': {
            '/health': 'Health check',
            '/webhook': 'Stripe webhook (POST)',
        }
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
