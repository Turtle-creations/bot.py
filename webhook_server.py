import asyncio
import html
import hashlib
import json
import os

import httpx
from flask import Flask, jsonify, request

from config import ADMINS, PUBLIC_BASE_URL, RAZORPAY_KEY_ID, SUPREME_ADMIN_ID, TELEGRAM_TOKEN
from services.payment_service_db import SUBSCRIPTION_PLANS, payment_service
from utils.logging_utils import get_logger


logger = get_logger(__name__)

app = Flask(__name__)


def _admin_chat_ids() -> list[int]:
    ids = {int(chat_id) for chat_id in ADMINS if chat_id}
    ids.add(int(SUPREME_ADMIN_ID))
    return sorted(ids)


def _resolve_bot_token() -> str:
    return os.environ.get("TOKEN") or os.environ.get("BOT_TOKEN") or TELEGRAM_TOKEN or ""


def _run_async(coro):
    return asyncio.run(coro)


async def _notify_payment_debug(step: str, **fields):
    token = _resolve_bot_token()
    if not token:
        logger.warning("Payment debug notify skipped | step=%s reason=missing_bot_token", step)
        return

    details = " ".join(f"{key}={value}" for key, value in fields.items())
    text = f"[PAYMENT DEBUG] step={step}"
    if details:
        text = f"{text} {details}"

    async with httpx.AsyncClient(timeout=10) as client:
        for chat_id in _admin_chat_ids():
            try:
                await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": text},
                )
            except Exception as exc:
                logger.warning(
                    "Payment debug notify failed | step=%s chat_id=%s reason=%s",
                    step,
                    chat_id,
                    exc,
                )


async def _trace_payment_step(step: str, **fields):
    logger.info("Payment trace | step=%s %s", step, fields)
    await _notify_payment_debug(step, **fields)


def _render_status_page(
    *,
    title: str,
    message: str,
    detail: str,
    status_kind: str,
) -> str:
    palette = {
        "success": ("#15803d", "Verified"),
        "failure": ("#b91c1c", "Not Verified"),
        "pending": ("#b45309", "Pending Verification"),
    }
    accent, badge = palette.get(status_kind, palette["failure"])
    return (
        f"""
        <!doctype html>
        <html>
        <head>
          <meta charset="utf-8" />
          <title>{html.escape(title)}</title>
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 640px; margin: 48px auto; padding: 0 16px;">
          <div style="border: 1px solid #e5e7eb; border-radius: 16px; padding: 24px;">
            <div style="display: inline-block; padding: 6px 10px; border-radius: 999px; background: #f3f4f6; color: {accent}; font-weight: 700;">
              {badge}
            </div>
            <h2 style="margin-top: 16px; color: {accent};">{html.escape(title)}</h2>
            <p style="font-size: 16px; line-height: 1.6;">{html.escape(message)}</p>
            <p style="color: #4b5563; line-height: 1.6;">{html.escape(detail)}</p>
          </div>
        </body>
        </html>
        """
    )


@app.route("/", methods=["GET"])
def index():
    return "Bot is running!"


@app.route("/health", methods=["GET"])
def health():
    return "OK"


@app.route("/webhook", methods=["GET"])
def webhook_debug_get():
    logger.info("Webhook debug GET hit | route=/webhook")
    return "Webhook endpoint is live. Configure Razorpay to send POST requests to this URL."


@app.route("/pay/<order_id>", methods=["GET"])
def payment_page(order_id: str):
    try:
        logger.info("Payment page opened | order_id=%s", order_id)
        _run_async(_trace_payment_step("payment_page_opened", order_id=order_id))

        order, order_source = _run_async(payment_service.get_order_with_fallback(order_id))
        if not order:
            logger.warning(
                "Payment page open failed | order_id=%s reason=order_not_found available_order_source=%s",
                order_id,
                order_source,
            )
            return "Invalid order_id", 404

        logger.info("Payment page order resolved | order_id=%s source=%s", order_id, order_source)

        plan_name = SUBSCRIPTION_PLANS.get(order["plan_type"], {}).get("name", "Payment")
        amount_rupees = order["amount"] / 100
        checkout_options = {
            "amount": order["amount"],
            "currency": order["currency"],
            "name": "Quiz Bot Premium",
            "description": plan_name,
            "order_id": order_id,
            "notes": {
                "user_id": str(order["user_id"]),
                "plan_type": str(order["plan_type"]),
            },
            "theme": {"color": "#0f766e"},
            "retry": {"enabled": True},
        }
        logger.info("Checkout options prepared | order_id=%s options=%s", order_id, checkout_options)
        checkout_options_json = json.dumps(
            {
                "key": RAZORPAY_KEY_ID,
                **checkout_options,
            }
        )

        return (
            f"""
            <!doctype html>
            <html>
            <head>
              <meta charset="utf-8" />
              <title>Quiz Bot Premium Payment</title>
              <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
            </head>
            <body style="font-family: Arial, sans-serif; max-width: 560px; margin: 40px auto;">
              <h2>Quiz Bot Premium</h2>
              <p><b>Plan:</b> {html.escape(plan_name)}</p>
              <p><b>Amount:</b> INR {amount_rupees:.2f}</p>
              <p style="color: #4b5563;">Secure checkout is handled entirely by Razorpay. Available UPI and payment methods come directly from Razorpay.</p>
              <button id="pay-btn" style="padding: 12px 20px; font-size: 16px;">Pay with Razorpay</button>
              <script>
                const successUrl = "{PUBLIC_BASE_URL}/payment/success";
                const cancelUrl = "{PUBLIC_BASE_URL}/payment/cancel?razorpay_order_id={order_id}";
                const eventUrl = "{PUBLIC_BASE_URL}/payment/event";
                const failureUrlBase = "{PUBLIC_BASE_URL}/payment/failed?razorpay_order_id={order_id}";
                const options = {checkout_options_json};
                function reportEvent(step, extra = {{}}) {{
                  fetch(eventUrl, {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ step, order_id: "{order_id}", ...extra }})
                  }}).catch(() => {{}});
                }}
                options.redirect = false;
                options.handler = function (response) {{
                  reportEvent("payment_success_callback_received", {{
                    payment_id: response.razorpay_payment_id || "",
                    order_id: response.razorpay_order_id || "{order_id}"
                  }});
                  console.log("Payment success response:", response);

                  const form = document.createElement("form");
                  form.method = "POST";
                  form.action = successUrl;

                  for (const key in response) {{
                    const input = document.createElement("input");
                    input.type = "hidden";
                    input.name = key;
                    input.value = response[key];
                    form.appendChild(input);
                  }}

                  document.body.appendChild(form);
                  form.submit();
                }};
                options.modal = {{
                  ondismiss: function () {{
                    reportEvent("checkout_closed", {{ order_id: "{order_id}" }});
                    alert("Payment cancelled or incomplete");
                    window.location.href = cancelUrl;
                  }}
                }};

                const rzp = new Razorpay(options);
                rzp.on("payment.failed", function (response) {{
                  const reason = encodeURIComponent(
                    response.error && (response.error.description || response.error.reason || response.error.code) || "payment_failed"
                  );
                  window.location.href = failureUrlBase + "&reason=" + reason;
                }});
                document.getElementById("pay-btn").onclick = function (e) {{
                  reportEvent("checkout_opened", {{ order_id: "{order_id}" }});
                  rzp.open();
                  e.preventDefault();
                }};
              </script>
            </body>
            </html>
            """
        )
    except Exception as exc:
        logger.exception(
            "Payment init failed | order_id=%s error=%s",
            order_id,
            str(exc),
        )
        return "Payment init failed", 500


@app.route("/payment/event", methods=["POST"])
def payment_event():
    payload = request.get_json(silent=True) or {}
    step = payload.get("step") or "unknown"
    _run_async(
        _trace_payment_step(
            step,
            order_id=payload.get("order_id"),
            payment_id=payload.get("payment_id"),
        )
    )
    return jsonify({"status": "ok"})


@app.route("/payment/cancel", methods=["GET"])
def payment_cancel(razorpay_order_id: str | None = None):
    razorpay_order_id = razorpay_order_id or request.args.get("razorpay_order_id")
    if razorpay_order_id:
        payment_service.update_order_status(razorpay_order_id, "cancelled")
    final_order = payment_service.get_order(razorpay_order_id) if razorpay_order_id else None
    logger.info(
        "Checkout dismissed | order_id=%s final_order_status=%s",
        razorpay_order_id,
        final_order.get("status") if final_order else None,
    )
    _run_async(
        _trace_payment_step(
            "checkout_closed",
            order_id=razorpay_order_id,
            final_status=final_order.get("status") if final_order else None,
        )
    )
    return _render_status_page(
        title="Payment Cancelled",
        message="Payment incomplete",
        detail="You can close this page and try again from the bot whenever you are ready.",
        status_kind="failure",
    )


@app.route("/payment/failed", methods=["GET"])
def payment_failed(
    razorpay_order_id: str | None = None,
    reason: str | None = None,
):
    razorpay_order_id = razorpay_order_id or request.args.get("razorpay_order_id")
    reason = reason or request.args.get("reason")
    if razorpay_order_id:
        payment_service.update_order_status(razorpay_order_id, "failed")
    final_order = payment_service.get_order(razorpay_order_id) if razorpay_order_id else None
    logger.warning(
        "Payment failed | order_id=%s reason=%s final_order_status=%s",
        razorpay_order_id,
        reason,
        final_order.get("status") if final_order else None,
    )
    _run_async(
        _trace_payment_step(
            "payment_incomplete",
            order_id=razorpay_order_id,
            final_status=final_order.get("status") if final_order else None,
        )
    )
    return _render_status_page(
        title="Payment Not Completed",
        message="Payment incomplete",
        detail=reason or "The payment app reported a failure before verification could complete.",
        status_kind="failure",
    )


@app.route("/payment/success", methods=["GET", "POST"])
def payment_success():
    form_data = {}
    if request.method == "POST":
        try:
            form_data = request.form.to_dict()
        except Exception:
            form_data = {}

    query_data = request.args.to_dict()
    logger.info(
        "Payment callback params received | method=%s form_keys=%s query_keys=%s",
        request.method,
        sorted(form_data.keys()),
        sorted(query_data.keys()),
    )

    raw_payment_id = form_data.get("razorpay_payment_id") or query_data.get("razorpay_payment_id")
    raw_order_id = form_data.get("razorpay_order_id") or query_data.get("razorpay_order_id")
    raw_signature = form_data.get("razorpay_signature") or query_data.get("razorpay_signature")

    logger.info(
        "Payment callback received | order_id=%s payment_id=%s method=%s",
        raw_order_id,
        raw_payment_id,
        request.method,
    )
    if not raw_payment_id or not raw_order_id or not raw_signature:
        final_order = payment_service.get_order(raw_order_id) if raw_order_id else None
        logger.info(
            "Payment callback ignored | order_id=%s reason=missing_fields payment_id=%s signature_present=%s webhook_received=%s final_order_status=%s",
            raw_order_id,
            raw_payment_id,
            bool(raw_signature),
            bool(final_order and final_order.get("status") == "paid"),
            final_order.get("status") if final_order else None,
        )
        _run_async(
            _trace_payment_step(
                "empty_callback_ignored",
                order_id=raw_order_id,
                payment_id=raw_payment_id or "missing",
                final_status=final_order.get("status") if final_order else None,
            )
        )
        return _render_status_page(
            title="Payment Not Completed",
            message="Payment incomplete",
            detail="Waiting for valid Razorpay callback details. Empty callback was ignored.",
            status_kind="failure",
        )

    order_id = raw_order_id
    payment_id = raw_payment_id
    signature = raw_signature
    logger.info(
        "Valid payment callback locked | order_id=%s payment_id=%s method=%s",
        order_id,
        payment_id,
        request.method,
    )
    _run_async(
        _trace_payment_step(
            "payment_success_callback_received",
            order_id=order_id,
            payment_id=payment_id,
        )
    )
    logger.info(
        "Payment callback payment id status | order_id=%s payment_id_received=%s",
        order_id,
        True,
    )
    _run_async(
        _trace_payment_step(
            "payment_id_check",
            order_id=order_id,
            payment_id=payment_id,
        )
    )

    order = payment_service.get_order(order_id)
    if not order:
        logger.warning("Payment callback failed | order_id=%s reason=order_not_found", order_id)
        return _render_status_page(
            title="Payment Details Not Found",
            message="Payment not completed or verification failed.",
            detail="We could not match this callback to a saved order.",
            status_kind="failure",
        )

    signature_ok = payment_service.verify_payment_signature(
        order_id=order_id,
        payment_id=payment_id,
        signature=signature,
    )
    if not signature_ok:
        payment_service.update_order_status(order_id, "callback_verification_failed")
        final_order = payment_service.get_order(order_id)
        logger.warning(
            "Payment callback signature failed | order_id=%s payment_id=%s reason=signature_mismatch webhook_received=%s final_order_status=%s",
            order_id,
            payment_id,
            bool(final_order and final_order.get("status") == "paid"),
            final_order.get("status") if final_order else None,
        )
        _run_async(
            _trace_payment_step(
                "payment_signature_invalid",
                order_id=order_id,
                payment_id=payment_id,
                final_status=final_order.get("status") if final_order else None,
            )
        )
        return _render_status_page(
            title="Payment Verification Failed",
            message="Payment incomplete",
            detail="Razorpay returned callback details, but the signature did not verify. Premium has not been activated.",
            status_kind="failure",
        )

    remote_payment = _run_async(payment_service.fetch_razorpay_payment(payment_id))
    remote_order = _run_async(payment_service.fetch_razorpay_order(order_id))
    remote_payment_status = (remote_payment or {}).get("status")
    remote_order_status = (remote_order or {}).get("status")
    _run_async(
        _trace_payment_step(
            "razorpay_backend_status",
            order_id=order_id,
            payment_id=payment_id,
            payment_status=remote_payment_status or "missing",
            order_status=remote_order_status or "missing",
        )
    )
    if remote_payment_status != "captured":
        payment_service.update_order_status(order_id, "callback_incomplete")
        final_order = payment_service.get_order(order_id)
        logger.warning(
            "Payment callback not captured | order_id=%s payment_id=%s remote_payment_status=%s remote_order_status=%s webhook_received=%s final_order_status=%s",
            order_id,
            payment_id,
            remote_payment_status,
            remote_order_status,
            bool(final_order and final_order.get("status") == "paid"),
            final_order.get("status") if final_order else None,
        )
        _run_async(
            _trace_payment_step(
                "webhook_not_received",
                order_id=order_id,
                payment_id=payment_id,
                final_status=final_order.get("status") if final_order else None,
            )
        )
        return _render_status_page(
            title="Payment Not Completed",
            message="Payment incomplete",
            detail="Razorpay did not confirm a captured payment for this order. Premium has not been activated.",
            status_kind="failure",
        )

    payment_service.update_order_status(order_id, "callback_verified")
    final_order = payment_service.get_order(order_id)
    logger.info(
        "Payment callback signature verified | order_id=%s payment_id=%s remote_payment_status=%s remote_order_status=%s webhook_received=%s final_order_status=%s",
        order_id,
        payment_id,
        remote_payment_status,
        remote_order_status,
        bool(final_order and final_order.get("status") == "paid"),
        final_order.get("status") if final_order else None,
    )
    logger.info(
        "Final valid callback status | order_id=%s payment_id=%s remote_payment_status=%s remote_order_status=%s final_order_status=%s",
        order_id,
        payment_id,
        remote_payment_status,
        remote_order_status,
        final_order.get("status") if final_order else None,
    )
    if not (final_order and final_order.get("status") == "paid"):
        _run_async(
            _trace_payment_step(
                "webhook_not_received",
                order_id=order_id,
                payment_id=payment_id,
                final_status=final_order.get("status") if final_order else None,
            )
        )
    return _render_status_page(
        title="Payment Verification Received",
        message="Your payment details were received and the payment is captured.",
        detail="Premium will be activated only after Razorpay sends a valid payment.captured webhook confirmation.",
        status_kind="pending",
    )


@app.route("/webhook", methods=["POST"])
@app.route("/webhook/razorpay", methods=["POST"])
def razorpay_webhook():
    x_razorpay_signature = request.headers.get("X-Razorpay-Signature")
    x_razorpay_event_id = request.headers.get("X-Razorpay-Event-Id")
    raw_body = request.get_data()
    headers_dict = dict(request.headers)
    body_text = raw_body.decode("utf-8", errors="replace")
    payload_preview = {}
    try:
        payload_preview = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload_preview = {}

    preview_entity = payload_preview.get("payload", {}).get("payment", {}).get("entity", {})
    preview_payment_id = preview_entity.get("id")
    preview_order_id = preview_entity.get("order_id")
    preview_final_order = payment_service.get_order(preview_order_id) if preview_order_id else None
    preview_event_name = payload_preview.get("event")
    logger.info(
        "Incoming webhook request | path=%s method=%s headers=%s body=%s",
        request.path,
        request.method,
        headers_dict,
        body_text,
    )
    logger.info(
        "Webhook received | event_id=%s payment_id=%s order_id=%s final_order_status=%s",
        x_razorpay_event_id,
        preview_payment_id,
        preview_order_id,
        preview_final_order.get("status") if preview_final_order else None,
    )
    _run_async(
        _trace_payment_step(
            "webhook_received",
            order_id=preview_order_id,
            payment_id=preview_payment_id,
            final_status=preview_final_order.get("status") if preview_final_order else None,
        )
    )

    if not x_razorpay_signature:
        logger.warning("Webhook rejected | event_id=%s reason=missing_signature", x_razorpay_event_id)
        _run_async(
            _trace_payment_step(
                "webhook_signature_invalid",
                order_id=preview_order_id,
                payment_id=preview_payment_id,
                final_status=preview_final_order.get("status") if preview_final_order else None,
            )
        )
        return jsonify({"detail": "Missing Razorpay signature"}), 400

    signature_ok = payment_service.verify_webhook_signature(raw_body, x_razorpay_signature)
    if not signature_ok:
        logger.warning(
            "Webhook signature failed | event_id=%s order_id=%s payment_id=%s event=%s",
            x_razorpay_event_id,
            preview_order_id,
            preview_payment_id,
            preview_event_name,
        )
        _run_async(
            _trace_payment_step(
                "webhook_signature_invalid",
                order_id=preview_order_id,
                payment_id=preview_payment_id,
                final_status=preview_final_order.get("status") if preview_final_order else None,
            )
        )
        return jsonify({"detail": "Invalid webhook signature"}), 401

    logger.info(
        "Webhook signature verified | event_id=%s order_id=%s payment_id=%s event=%s",
        x_razorpay_event_id,
        preview_order_id,
        preview_payment_id,
        preview_event_name,
    )
    _run_async(
        _trace_payment_step(
            "webhook_signature_valid",
            order_id=preview_order_id,
            payment_id=preview_payment_id,
            final_status=preview_final_order.get("status") if preview_final_order else None,
        )
    )
    if payload_preview:
        payload = payload_preview
    else:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("Webhook rejected | event_id=%s reason=invalid_json", x_razorpay_event_id)
            return jsonify({"detail": "Invalid webhook payload"}), 400

    event_name = payload.get("event")
    logger.info("Webhook event type | event_id=%s event=%s", x_razorpay_event_id, event_name)
    if event_name != "payment.captured":
        logger.info("Webhook ignored | event_id=%s event=%s", x_razorpay_event_id, event_name)
        return jsonify({"status": "ignored", "reason": "unsupported_event"})

    derived_event_id = (
        x_razorpay_event_id
        or payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id")
        or hashlib.sha256(raw_body).hexdigest()
    )
    try:
        result = payment_service.process_captured_payment(derived_event_id, payload)
    except ValueError as exc:
        logger.warning("Webhook processing failed | event_id=%s reason=%s", derived_event_id, exc)
        return jsonify({"detail": str(exc)}), 400
    except Exception as exc:
        logger.exception("Webhook processing crashed | event_id=%s", derived_event_id)
        return jsonify({"detail": f"Webhook processing failed: {exc}"}), 500

    if result.get("status") == "processed":
        final_order = payment_service.get_order(
            payload.get("payload", {}).get("payment", {}).get("entity", {}).get("order_id")
        )
        logger.info(
            "Webhook processed successfully | event_id=%s user_id=%s plan_type=%s webhook_received=%s final_order_status=%s",
            derived_event_id,
            result.get("user_id"),
            result.get("plan_type"),
            True,
            final_order.get("status") if final_order else None,
        )
        _run_async(
            _trace_payment_step(
                "premium_activated",
                order_id=payload.get("payload", {}).get("payment", {}).get("entity", {}).get("order_id"),
                payment_id=payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id"),
                final_status=final_order.get("status") if final_order else None,
            )
        )
    else:
        _run_async(
            _trace_payment_step(
                "premium_not_activated",
                order_id=payload.get("payload", {}).get("payment", {}).get("entity", {}).get("order_id"),
                payment_id=payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id"),
                final_status=result.get("status"),
            )
        )

    return jsonify(result)
