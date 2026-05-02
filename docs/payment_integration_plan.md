# Razorpay Integration Plan

This bot is deploy-ready with payment checkout disabled in the user UI.

## Live features now

- Quiz flow
- Question timer
- Admin panel
- Scheduled notifications
- Premium placeholder UI only

## Keep as-is

- `services/payment_service_db.py`
- `webhook_server.py`
- payment-related database tables

These remain available for backend work and testing, but they are not exposed in the live Telegram premium UI.

## Fresh Razorpay rebuild plan

1. Create order from the bot backend only.
2. Use standard Razorpay checkout with the returned `order_id`.
3. Do not inject any custom UPI id or force any payment app path.
4. Use Razorpay `handler(response)` to submit:
   - `razorpay_payment_id`
   - `razorpay_order_id`
   - `razorpay_signature`
5. Use `modal.ondismiss` only for cancel UX.
6. Treat `/payment/success` as callback verification only.
7. Activate premium only from verified `payment.captured` webhook processing.
8. Validate:
   - webhook signature
   - checkout signature
   - order amount
   - user existence
9. Add an admin-only staging switch before re-enabling checkout in production.

## Re-enable checklist later

- Replace placeholder premium button with live subscribe button.
- Restore plan selection UI.
- Re-enable safe order creation handler.
- Test with Razorpay test mode first.
- Verify webhook delivery on deployed domain.
