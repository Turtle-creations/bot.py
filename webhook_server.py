import html
import hashlib
import json
import os
import time
from queue import Empty, Full, Queue
from threading import Thread

import httpx
from flask import Flask, jsonify, render_template, request

from config import ADMINS, BOT_USERNAME, PAYMENT_DEBUG, PUBLIC_BASE_URL, RAZORPAY_KEY_ID, SUPREME_ADMIN_ID, TELEGRAM_TOKEN
from services.payment_service_db import SUBSCRIPTION_PLANS, payment_service
from utils.logging_utils import get_logger


logger = get_logger(__name__)
SITE_NAME = "QuizPathshala"
SITE_TAGLINE = "Online quiz preparation platform via Telegram bot"
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "quizpathshala.help@gmail.com")
SUPPORT_HOURS = os.environ.get("SUPPORT_HOURS", "Monday to Saturday, 10:00 AM to 7:00 PM IST")
SUPPORT_TELEGRAM = os.environ.get("SUPPORT_TELEGRAM", "")
CANONICAL_URL = (os.environ.get("CANONICAL_URL") or PUBLIC_BASE_URL or "").rstrip("/")

app = Flask(
    __name__,
    template_folder="quizpathshala_website/website/templates",
    static_folder="quizpathshala_website/website/static",
)
_TELEGRAM_QUEUE_MAX_SIZE = 1000
_TELEGRAM_QUEUE: Queue[dict] = Queue(maxsize=_TELEGRAM_QUEUE_MAX_SIZE)
_ADMIN_DEBUG_STEPS = {
    "webhook_received",
    "webhook_signature_invalid",
    "webhook_signature_valid",
    "payment_signature_invalid",
    "webhook_not_received",
    "premium_activation_success",
    "already_processed",
    "premium_not_activated",
}


@app.context_processor
def inject_site_context():
    return {
        "site_name": SITE_NAME,
        "tagline": SITE_TAGLINE,
        "bot_url": _resolve_bot_link(),
        "support_email": SUPPORT_EMAIL,
        "support_hours": SUPPORT_HOURS,
        "support_telegram": SUPPORT_TELEGRAM or _resolve_bot_link(),
        "canonical_url": CANONICAL_URL,
    }


def _build_simple_page(title: str, intro: str, *sections: str) -> dict[str, object]:
    return {
        "title": title,
        "intro": intro,
        "sections": list(sections),
    }


def _admin_chat_ids() -> list[int]:
    ids = {int(chat_id) for chat_id in ADMINS if chat_id}
    ids.add(int(SUPREME_ADMIN_ID))
    return sorted(ids)


def _resolve_bot_token() -> str:
    return os.environ.get("TOKEN") or os.environ.get("BOT_TOKEN") or TELEGRAM_TOKEN or ""


def _resolve_bot_username() -> str:
    candidate = (BOT_USERNAME or os.environ.get("BOT_USERNAME") or "").strip()
    if not candidate or candidate == "YOUR_BOT_USERNAME":
        logger.warning("BOT_USERNAME is missing or placeholder; Telegram redirect disabled")
        return ""
    return candidate


def _resolve_bot_link() -> str:
    bot_username = _resolve_bot_username()
    return f"https://t.me/{bot_username}" if bot_username else ""


def _resolve_bot_app_link(start_param: str = "payment_success") -> str:
    bot_username = _resolve_bot_username()
    return f"tg://resolve?domain={bot_username}&start={start_param}" if bot_username else ""


def _resolve_bot_deep_link(start_param: str = "payment_success") -> str:
    bot_username = _resolve_bot_username()
    return f"https://t.me/{bot_username}?start={start_param}" if bot_username else ""


_LAST_TELEGRAM_WORKER_IDLE_LOG = 0.0


def _telegram_worker():
    global _LAST_TELEGRAM_WORKER_IDLE_LOG
    while True:
        try:
            queue_size = _TELEGRAM_QUEUE.qsize()
            now_monotonic = time.monotonic()
            if queue_size > 0 or now_monotonic - _LAST_TELEGRAM_WORKER_IDLE_LOG >= 300:
                logger.debug("Telegram worker waiting | queue_size=%s", queue_size)
                _LAST_TELEGRAM_WORKER_IDLE_LOG = now_monotonic
            item = _TELEGRAM_QUEUE.get(timeout=1)
        except Empty:
            continue

        try:
            token = _resolve_bot_token()
            if not token:
                continue

            logger.info(
                "Telegram sendMessage start | chat_id=%s queue_size_before_send=%s",
                item.get("chat_id"),
                _TELEGRAM_QUEUE.qsize(),
            )
            with httpx.Client(timeout=10) as client:
                client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": item["chat_id"], "text": item["text"]},
                )
            logger.info(
                "Telegram sendMessage end | chat_id=%s queue_size_after_send=%s",
                item.get("chat_id"),
                _TELEGRAM_QUEUE.qsize(),
            )
        except Exception as exc:
            logger.warning(
                "Telegram background send failed | chat_id=%s reason=%s",
                item.get("chat_id"),
                exc,
            )
        finally:
            _TELEGRAM_QUEUE.task_done()


Thread(target=_telegram_worker, daemon=True).start()


def _enqueue_telegram_message(chat_id: int, text: str):
    token = _resolve_bot_token()
    if not token:
        logger.warning("Telegram send skipped | chat_id=%s reason=missing_bot_token", chat_id)
        return
    try:
        logger.info("Telegram enqueue start | chat_id=%s queue_size_before=%s", chat_id, _TELEGRAM_QUEUE.qsize())
        _TELEGRAM_QUEUE.put_nowait({"chat_id": int(chat_id), "text": text})
        logger.info("Telegram enqueue end | chat_id=%s queue_size_after=%s", chat_id, _TELEGRAM_QUEUE.qsize())
    except Full:
        logger.warning("Telegram queue full | chat_id=%s max_size=%s", chat_id, _TELEGRAM_QUEUE_MAX_SIZE)


def _notify_payment_debug(step: str, **fields):
    if not PAYMENT_DEBUG:
        return
    if step not in _ADMIN_DEBUG_STEPS:
        return

    details = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    text = f"[PAYMENT DEBUG] step={step}"
    if details:
        text = f"{text} {details}"

    for chat_id in _admin_chat_ids():
        _enqueue_telegram_message(chat_id, text)


def _trace_payment_step(step: str, **fields):
    logger.info("Payment trace | step=%s %s", step, fields)
    _notify_payment_debug(step, **fields)


def _render_status_page(
    *,
    title: str,
    message: str,
    detail: str,
    status_kind: str,
    action_url: str | None = None,
    action_label: str | None = None,
    fallback_url: str | None = None,
    fallback_label: str | None = None,
    show_close_button: bool = False,
    close_hint: str | None = None,
    auto_redirect_url: str | None = None,
    secondary_redirect_url: str | None = None,
    secondary_redirect_delay_ms: int | None = None,
    auto_redirect_delay_ms: int | None = None,
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
            {f'<p id="redirect-countdown" style="color: #6b7280;">Redirecting in {max(1, int((auto_redirect_delay_ms or 3000) / 1000))} seconds...</p>' if auto_redirect_url and auto_redirect_delay_ms else ""}
            {f'<p style="margin-top: 20px;"><a href="{html.escape(action_url or "")}" style="display: inline-block; background: {accent}; color: white; text-decoration: none; padding: 12px 18px; border-radius: 10px; font-weight: 700; margin-right: 12px;">{html.escape(action_label or "Open")}</a>{f"<button type=\"button\" onclick=\"window.close()\" style=\"display: inline-block; background: #e5e7eb; color: #111827; border: 0; padding: 12px 18px; border-radius: 10px; font-weight: 700; cursor: pointer;\">Close this page</button>" if show_close_button else ""}</p>' if (action_url and action_label) or show_close_button else ""}
            {f'<p style="margin-top: 12px;"><a href="{html.escape(fallback_url or "")}" style="color: {accent}; text-decoration: underline; font-weight: 600;">{html.escape(fallback_label or "Open in Telegram")}</a></p>' if fallback_url and fallback_label else ""}
            {f'<p style="margin-top: 16px; color: #6b7280; line-height: 1.6;">{html.escape(close_hint)}</p>' if close_hint else ""}
          </div>
          {f'''<script>
            (function() {{
              var countdownEl = document.getElementById("redirect-countdown");
              var remaining = {max(1, int((auto_redirect_delay_ms or 3000) / 1000))};
              if (countdownEl) {{
                var timer = setInterval(function () {{
                  remaining -= 1;
                  if (remaining <= 0) {{
                    countdownEl.textContent = "Redirecting now...";
                    clearInterval(timer);
                  }} else {{
                    countdownEl.textContent = "Redirecting in " + remaining + " seconds...";
                  }}
                }}, 1000);
              }}
              setTimeout(function () {{ window.location.href = {json.dumps(auto_redirect_url)}; }}, {int(auto_redirect_delay_ms or 3000)});
              {f'setTimeout(function () {{ window.location.href = {json.dumps(secondary_redirect_url)}; }}, {int(secondary_redirect_delay_ms or 4000)});' if secondary_redirect_url and secondary_redirect_delay_ms else ''}
            }})();
          </script>''' if auto_redirect_url and auto_redirect_delay_ms else ""}
        </body>
        </html>
        """
    )


@app.route("/", methods=["GET"])
def home():
    return render_template("home.html", page_title="Home")


@app.route("/quiz", methods=["GET"])
def quiz_page():
    page = _build_simple_page(
        "Quiz Practice",
        "Practice quizzes are available through the QuizPathshala Telegram bot.",
        "Open the bot to choose your exam, start a quiz, and track your performance.",
    )
    return render_template("simple_page.html", page_title=page["title"], page=page)


@app.route("/premium", methods=["GET"])
def premium_page():
    page = _build_simple_page(
        "Premium Plans",
        "Premium access is managed through the QuizPathshala Telegram bot and payment flow.",
        "Use the bot to explore plans, continue to checkout, and activate premium after Razorpay confirmation.",
    )
    return render_template("simple_page.html", page_title=page["title"], page=page)


@app.route("/privacy", methods=["GET"])
def privacy():
    page = _build_simple_page(
        "Privacy Policy",
        "QuizPathshala uses the information needed to operate quiz access, progress tracking, and support.",
        "Payment verification and premium activation are completed through the secure Razorpay payment workflow.",
    )
    return render_template("simple_page.html", page_title=page["title"], page=page)


@app.route("/terms", methods=["GET"])
def terms():
    page = _build_simple_page(
        "Terms & Conditions",
        "Using QuizPathshala means following the app rules, payment terms, and platform policies.",
        "Premium benefits are activated only after successful payment verification and webhook confirmation.",
    )
    return render_template("simple_page.html", page_title=page["title"], page=page)


@app.route("/refund-policy", methods=["GET"])
def refund():
    page = _build_simple_page(
        "Refund Policy",
        "Refund handling depends on the payment status and the support review process.",
        "Contact support with your payment details if you need help with a premium purchase.",
    )
    return render_template("simple_page.html", page_title=page["title"], page=page)


@app.route("/contact", methods=["GET"])
def contact():
    return render_template("contact.html", page_title="Contact")


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
        _trace_payment_step("payment_page_opened", order_id=order_id)

        order, order_source = payment_service.get_order_with_fallback_sync(order_id)
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
    order_id = payload.get("order_id")
    final_order = payment_service.get_order(order_id) if order_id else None
    if step == "checkout_closed":
        logger.info(
            "payment_closed_before_success | order_id=%s final_order_status=%s",
            order_id,
            final_order.get("status") if final_order else None,
        )
    _trace_payment_step(
        step,
        order_id=order_id,
        payment_id=payload.get("payment_id"),
    )
    return jsonify({"status": "ok"})


@app.route("/payment/cancel", methods=["GET"])
def payment_cancel(razorpay_order_id: str | None = None):
    razorpay_order_id = razorpay_order_id or request.args.get("razorpay_order_id")
    final_order = None
    updated = False
    if razorpay_order_id:
        final_order, updated = payment_service.set_order_status_if_not_paid(razorpay_order_id, "cancelled")
    logger.info(
        "Checkout dismissed | order_id=%s final_order_status=%s updated=%s",
        razorpay_order_id,
        final_order.get("status") if final_order else None,
        updated,
    )
    logger.info(
        "payment_closed_before_success | order_id=%s final_order_status=%s",
        razorpay_order_id,
        final_order.get("status") if final_order else None,
    )
    _trace_payment_step(
        "checkout_closed",
        order_id=razorpay_order_id,
        final_status=final_order.get("status") if final_order else None,
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
    final_order = None
    updated = False
    if razorpay_order_id:
        final_order, updated = payment_service.set_order_status_if_not_paid(razorpay_order_id, "failed")
    logger.warning(
        "Payment failed | order_id=%s reason=%s final_order_status=%s updated=%s",
        razorpay_order_id,
        reason,
        final_order.get("status") if final_order else None,
        updated,
    )
    _trace_payment_step(
        "payment_incomplete",
        order_id=razorpay_order_id,
        final_status=final_order.get("status") if final_order else None,
    )
    return _render_status_page(
        title="Payment Not Completed",
        message="Payment incomplete",
        detail=reason or "The payment app reported a failure before verification could complete.",
        status_kind="failure",
    )


@app.route("/payment/success", methods=["GET", "POST"])
def payment_success():
    order_id = None
    payment_id = None
    route_started_at = time.monotonic()
    route_outcome = "unknown"
    logger.info("payment_success start | method=%s path=%s", request.method, request.path)
    try:
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
        order_id = raw_order_id
        payment_id = raw_payment_id

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
            _trace_payment_step(
                "empty_callback_ignored",
                order_id=raw_order_id,
                payment_id=raw_payment_id or "missing",
                final_status=final_order.get("status") if final_order else None,
            )
            route_outcome = "missing_fields"
            return _render_status_page(
                title="Payment Not Completed",
                message="Payment incomplete",
                detail="Waiting for valid Razorpay callback details. Empty callback was ignored.",
                status_kind="failure",
            )

        signature = raw_signature
        logger.info(
            "Valid payment callback locked | order_id=%s payment_id=%s method=%s",
            order_id,
            payment_id,
            request.method,
        )
        _trace_payment_step(
            "payment_success_callback_received",
            order_id=order_id,
            payment_id=payment_id,
        )
        logger.info(
            "Payment callback payment id status | order_id=%s payment_id_received=%s",
            order_id,
            True,
        )
        _trace_payment_step(
            "payment_id_check",
            order_id=order_id,
            payment_id=payment_id,
        )

        order = payment_service.get_order(order_id)
        if not order:
            logger.warning("Payment callback failed | order_id=%s reason=order_not_found", order_id)
            route_outcome = "order_not_found"
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
            _trace_payment_step(
                "payment_signature_invalid",
                order_id=order_id,
                payment_id=payment_id,
                final_status=final_order.get("status") if final_order else None,
            )
            route_outcome = "invalid_signature"
            return _render_status_page(
                title="Payment Verification Failed",
                message="Payment incomplete",
                detail="Razorpay returned callback details, but the signature did not verify. Premium has not been activated.",
                status_kind="failure",
            )

        remote_payment = payment_service.fetch_razorpay_payment_sync(payment_id)
        remote_order = payment_service.fetch_razorpay_order_sync(order_id)
        remote_payment_status = (remote_payment or {}).get("status")
        remote_order_status = (remote_order or {}).get("status")
        backend_payment_captured = remote_payment_status == "captured"
        backend_order_paid = remote_order_status == "paid"
        _trace_payment_step(
            "razorpay_backend_status",
            order_id=order_id,
            payment_id=payment_id,
            payment_status=remote_payment_status or "missing",
            order_status=remote_order_status or "missing",
        )
        if not backend_payment_captured:
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
            logger.info(
                "payment_not_captured_no_activation | order_id=%s payment_id=%s remote_payment_status=%s remote_order_status=%s",
                order_id,
                payment_id,
                remote_payment_status,
                remote_order_status,
            )
            logger.warning(
                "payment_not_captured_blocked | order_id=%s payment_id=%s remote_payment_status=%s remote_order_status=%s",
                order_id,
                payment_id,
                remote_payment_status,
                remote_order_status,
            )
            _trace_payment_step(
                "webhook_not_received",
                order_id=order_id,
                payment_id=payment_id,
                final_status=final_order.get("status") if final_order else None,
            )
            route_outcome = "payment_not_captured"
            return _render_status_page(
                title="Payment Not Completed",
                message="Payment incomplete",
                detail="Razorpay did not confirm a captured payment for this order. Premium has not been activated.",
                status_kind="failure",
            )

        final_order = payment_service.get_order(order_id)
        local_order_paid = bool(final_order and final_order.get("status") == "paid")
        if final_order and final_order.get("status") not in {"paid", "already_processed"}:
            payment_service.update_order_status(order_id, "callback_verified")
            final_order = payment_service.get_order(order_id)
            local_order_paid = bool(final_order and final_order.get("status") == "paid")
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
        if not backend_order_paid:
            logger.warning(
                "premium_activation_blocked_reason | order_id=%s payment_id=%s reason=remote_order_not_paid remote_payment_status=%s remote_order_status=%s local_order_status=%s",
                order_id,
                payment_id,
                remote_payment_status,
                remote_order_status,
                final_order.get("status") if final_order else None,
            )
            route_outcome = "remote_order_not_paid"
            return _render_status_page(
                title="Payment Verification Pending",
                message="Your payment is still being confirmed.",
                detail="Razorpay has not marked this order as paid yet, so premium was not activated.",
                status_kind="pending",
                action_url=_resolve_bot_link() or None,
                action_label="Return to Bot" if _resolve_bot_link() else None,
            )

        if not local_order_paid:
            logger.warning(
                "premium_activation_blocked_reason | order_id=%s payment_id=%s reason=local_order_not_paid remote_payment_status=%s remote_order_status=%s local_order_status=%s",
                order_id,
                payment_id,
                remote_payment_status,
                remote_order_status,
                final_order.get("status") if final_order else None,
            )
            route_outcome = "local_order_not_paid"
            return _render_status_page(
                title="Payment Verification Pending",
                message="Your payment is still being confirmed.",
                detail="The local order is not marked as paid yet, so premium was not activated.",
                status_kind="pending",
                action_url=_resolve_bot_link() or None,
                action_label="Return to Bot" if _resolve_bot_link() else None,
            )

        if final_order and final_order.get("status") in {"paid", "already_processed"}:
            logger.info(
                "redirecting_to_bot | order_id=%s payment_id=%s final_order_status=%s redirect_url=%s fallback_url=%s",
                order_id,
                payment_id,
                final_order.get("status"),
                _resolve_bot_app_link(),
                _resolve_bot_deep_link(),
            )
            route_outcome = "success"
            return _render_status_page(
                title="Payment Successful",
                message="Your premium payment was verified successfully.",
                detail="Payment verification is complete. Premium activation happens only from the verified Razorpay webhook, so please return to the bot and use /premium_status to confirm it is active.",
                status_kind="success",
                action_url=_resolve_bot_app_link() or _resolve_bot_deep_link() or None,
                action_label="Open Bot" if (_resolve_bot_app_link() or _resolve_bot_deep_link()) else None,
                fallback_url=_resolve_bot_deep_link() or None,
                fallback_label="Open in Telegram" if _resolve_bot_deep_link() else None,
                show_close_button=True,
                close_hint="If page does not close automatically, tap X/Back and return to bot.",
                auto_redirect_url=_resolve_bot_app_link() or None,
                secondary_redirect_url=_resolve_bot_deep_link() or None,
                auto_redirect_delay_ms=3000 if _resolve_bot_app_link() else None,
                secondary_redirect_delay_ms=4000 if _resolve_bot_deep_link() else None,
            )

        if not (final_order and final_order.get("status") == "paid"):
            _trace_payment_step(
                "webhook_not_received",
                order_id=order_id,
                payment_id=payment_id,
                final_status=final_order.get("status") if final_order else None,
            )
        route_outcome = "waiting_for_webhook"
        return _render_status_page(
            title="Payment Verification Received",
            message="Your payment details were received and the payment is captured.",
            detail="Premium will be activated only after Razorpay sends a valid payment.captured webhook confirmation.",
            status_kind="pending",
        )
    except Exception:
        logger.exception(
            "Payment success route failed | order_id=%s payment_id=%s method=%s",
            order_id,
            payment_id,
            request.method,
        )
        route_outcome = "exception"
        return _render_status_page(
            title="Payment Received",
            message="Your payment is being verified.",
            detail="We hit a temporary issue while finalizing this payment. Please return to the bot and use /premium_status shortly.",
            status_kind="pending",
            action_url=_resolve_bot_link() or None,
            action_label="Return to Bot" if _resolve_bot_link() else None,
        )
    finally:
        logger.info(
            "payment_success end | order_id=%s payment_id=%s outcome=%s duration_ms=%s",
            order_id,
            payment_id,
            route_outcome,
            int((time.monotonic() - route_started_at) * 1000),
        )


@app.route("/webhook", methods=["POST"])
@app.route("/webhook/razorpay", methods=["POST"])
def razorpay_webhook():
    route_started_at = time.monotonic()
    route_outcome = "unknown"
    x_razorpay_signature = request.headers.get("X-Razorpay-Signature")
    x_razorpay_event_id = request.headers.get("X-Razorpay-Event-Id")
    logger.info("webhook start | path=%s method=%s event_id=%s", request.path, request.method, x_razorpay_event_id)
    def _log_webhook_end():
        logger.info(
            "webhook end | path=%s method=%s event_id=%s outcome=%s duration_ms=%s queue_size=%s",
            request.path,
            request.method,
            x_razorpay_event_id,
            route_outcome,
            int((time.monotonic() - route_started_at) * 1000),
            _TELEGRAM_QUEUE.qsize(),
        )

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
    if not x_razorpay_signature:
        logger.warning("Webhook rejected | event_id=%s reason=missing_signature", x_razorpay_event_id)
        _trace_payment_step(
            "webhook_signature_invalid",
            order_id=preview_order_id,
            payment_id=preview_payment_id,
            final_status=preview_final_order.get("status") if preview_final_order else None,
        )
        route_outcome = "missing_signature"
        _log_webhook_end()
        return jsonify({"detail": "Missing Razorpay signature"}), 401

    signature_ok = payment_service.verify_webhook_signature(raw_body, x_razorpay_signature)
    if not signature_ok:
        logger.warning(
            "Webhook signature failed | event_id=%s order_id=%s payment_id=%s event=%s",
            x_razorpay_event_id,
            preview_order_id,
            preview_payment_id,
            preview_event_name,
        )
        _trace_payment_step(
            "webhook_signature_invalid",
            order_id=preview_order_id,
            payment_id=preview_payment_id,
            final_status=preview_final_order.get("status") if preview_final_order else None,
        )
        route_outcome = "invalid_signature"
        _log_webhook_end()
        return jsonify({"detail": "Invalid webhook signature"}), 401

    logger.info(
        "Webhook signature verified | event_id=%s order_id=%s payment_id=%s event=%s",
        x_razorpay_event_id,
        preview_order_id,
        preview_payment_id,
        preview_event_name,
    )
    if payload_preview:
        payload = payload_preview
    else:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("Webhook rejected | event_id=%s reason=invalid_json", x_razorpay_event_id)
            route_outcome = "invalid_json"
            _log_webhook_end()
            return jsonify({"detail": "Invalid webhook payload"}), 400

    event_name = payload.get("event")
    logger.info("Webhook event type | event_id=%s event=%s", x_razorpay_event_id, event_name)
    if event_name != "payment.captured":
        logger.info("Webhook ignored | event_id=%s event=%s", x_razorpay_event_id, event_name)
        route_outcome = "ignored"
        _log_webhook_end()
        return jsonify({"status": "ignored", "reason": "unsupported_event"})

    derived_event_id = (
        x_razorpay_event_id
        or payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id")
        or hashlib.sha256(raw_body).hexdigest()
    )
    duplicate_status = payment_service.check_processed_webhook(
        derived_event_id,
        payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id"),
        payload.get("payload", {}).get("payment", {}).get("entity", {}).get("order_id"),
    )
    if duplicate_status.get("duplicate"):
        logger.info(
            "Webhook duplicate ignored | event_id=%s payment_id=%s order_id=%s reason=%s",
            derived_event_id,
            payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id"),
            payload.get("payload", {}).get("payment", {}).get("entity", {}).get("order_id"),
            duplicate_status.get("reason"),
        )
        route_outcome = "already_processed"
        _log_webhook_end()
        return jsonify({"status": "already_processed", "reason": duplicate_status.get("reason")}), 200

    _trace_payment_step(
        "webhook_signature_valid",
        order_id=preview_order_id,
        payment_id=preview_payment_id,
        final_status=preview_final_order.get("status") if preview_final_order else None,
    )
    _trace_payment_step(
        "webhook_received",
        order_id=preview_order_id,
        payment_id=preview_payment_id,
        final_status=preview_final_order.get("status") if preview_final_order else None,
    )
    try:
        result = payment_service.process_captured_payment(derived_event_id, payload)
    except ValueError as exc:
        logger.warning("Webhook processing failed | event_id=%s reason=%s", derived_event_id, exc)
        route_outcome = "validation_error"
        _log_webhook_end()
        return jsonify({"detail": str(exc)}), 400
    except Exception as exc:
        logger.exception("Webhook processing crashed | event_id=%s", derived_event_id)
        route_outcome = "exception"
        _log_webhook_end()
        return jsonify({"detail": f"Webhook processing failed: {exc}"}), 500

    if result.get("status") in {"processed", "already_processed"}:
        final_order = payment_service.get_order(
            payload.get("payload", {}).get("payment", {}).get("entity", {}).get("order_id")
        )
        logger.info(
            "Webhook processed successfully | event_id=%s user_id=%s plan_type=%s result_status=%s webhook_received=%s final_order_status=%s",
            derived_event_id,
            result.get("user_id"),
            result.get("plan_type"),
            result.get("status"),
            True,
            final_order.get("status") if final_order else None,
        )
        trace_step = "premium_activation_success" if result.get("status") == "processed" else "already_processed"
        _trace_payment_step(
            trace_step,
            order_id=payload.get("payload", {}).get("payment", {}).get("entity", {}).get("order_id"),
            payment_id=payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id"),
            final_status=final_order.get("status") if final_order else None,
        )
        activation_result = result.get("activation_result") or {}
        if result.get("status") == "processed" and activation_result.get("activated_now") and result.get("user_id"):
            _enqueue_telegram_message(
                int(result["user_id"]),
                "✅ Premium activated successfully. Use /premium_status",
            )
            logger.info(
                "premium_activation_success_sent_to_user | user_id=%s order_id=%s",
                result.get("user_id"),
                payload.get("payload", {}).get("payment", {}).get("entity", {}).get("order_id"),
            )
    else:
        _trace_payment_step(
            "premium_not_activated",
            order_id=payload.get("payload", {}).get("payment", {}).get("entity", {}).get("order_id"),
            payment_id=payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id"),
            final_status=result.get("status"),
        )

    route_outcome = result.get("status") or "completed"
    _log_webhook_end()
    return jsonify(result)
