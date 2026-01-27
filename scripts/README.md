# Payment & Licensing Scripts

Scripts for managing Roura Agent payments and license keys.

## Setup

1. Fill in `.env.stripe` with your API keys:
   ```
   STRIPE_SECRET_KEY=sk_live_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   SENDGRID_API_KEY=SG....
   FROM_EMAIL=license@roura.io
   FROM_NAME=Roura Agent
   ```

2. Set up Stripe products (one-time):
   ```bash
   python scripts/setup_stripe.py
   ```

3. Start the webhook server:
   ```bash
   python scripts/payment_webhook.py
   ```

## Scripts

### `generate_licenses.py`

Generate license keys manually (for friends, family, or manual orders).

```bash
# Single license
python scripts/generate_licenses.py john@example.com PRO --lifetime

# With email delivery
python scripts/generate_licenses.py john@example.com PRO --lifetime --send --name "John Doe"

# Batch generation from file
python scripts/generate_licenses.py --batch emails.txt PRO --lifetime
```

### `setup_stripe.py`

Set up Stripe products, prices, and payment links.

```bash
python scripts/setup_stripe.py
```

Creates:
- Pro Monthly ($19/mo)
- Pro Annual ($159/yr)
- Pro Lifetime ($299)
- Enterprise Annual ($499/yr)

### `payment_webhook.py`

Webhook server that:
1. Receives Stripe checkout.session.completed events
2. Generates license keys
3. Sends them via SendGrid email

For development with ngrok:
```bash
ngrok http 8000
python scripts/payment_webhook.py
```

Then add the ngrok URL to Stripe webhooks.

## Pricing

| Plan | Price | Duration |
|------|-------|----------|
| Pro Monthly | $19/mo | 30 days |
| Pro Annual | $159/yr | 365 days |
| Pro Lifetime | $299 | Perpetual |
| Enterprise Annual | $499/yr | 365 days |

## License Key Format

```
TIER-EMAIL-EXPIRY
```

Examples:
- `PRO-user@example.com-2027-01-27` (1 year)
- `PRO-user@example.com-PERPETUAL` (lifetime)
- `ENTERPRISE-admin@company.com-2027-01-27`
