import hashlib
import json

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from config import BOT_URL, PUBLIC_BASE_URL, RAZORPAY_KEY_ID
from services.payment_service_db import payment_service
from services.web_identity_service import web_identity_service
from services.web_payment_service import web_payment_service


premium_blueprint = Blueprint("premium", __name__)


@premium_blueprint.route("/premium", methods=["GET", "POST"])
def premium_page():
    user = web_identity_service.get_or_create_user()
    if request.method == "POST":
        plan_type = request.form.get("plan_type", "")
        try:
            order = web_payment_service.create_order(user["user_id"], plan_type)
        except Exception as exc:
            flash(str(exc), "error")
            return redirect(url_for("premium.premium_page"))
        return redirect(url_for("premium.payment_page", order_id=order["order_id"]))

    return render_template(
        "premium.html",
        page_title="Premium Plans",
        user=user,
        premium_prices=payment_service.list_premium_prices(),
        payment_ready=not payment_service.get_missing_configuration(),
        missing_payment_config=payment_service.get_missing_configuration(),
        premium_status=payment_service.premium_status_text(user),
        bot_url=BOT_URL,
        admin_authenticated=web_identity_service.is_admin_authenticated(),
    )


@premium_blueprint.route("/payment/<order_id>")
def payment_page(order_id: str):
    user = web_identity_service.get_or_create_user()
    order, _source = payment_service.get_order_with_fallback_sync(order_id)
    if not order:
        flash("Invalid payment order.", "error")
        return redirect(url_for("premium.premium_page"))

    plan = payment_service.get_plan(order["plan_type"])
    checkout_options = {
        "key": RAZORPAY_KEY_ID,
        "amount": order["amount"],
        "currency": order["currency"],
        "name": "QuizPathshala Premium",
        "description": plan["name"],
        "order_id": order_id,
        "notes": {
            "user_id": str(order["user_id"]),
            "plan_type": str(order["plan_type"]),
        },
        "theme": {"color": "#c35b2f"},
    }
    return render_template(
        "payment_page.html",
        page_title="Payment Checkout",
        user=user,
        order=order,
        plan=plan,
        checkout_options=json.dumps(checkout_options),
        public_base_url=PUBLIC_BASE_URL.rstrip("/") or request.url_root.rstrip("/"),
        admin_authenticated=web_identity_service.is_admin_authenticated(),
    )


@premium_blueprint.route("/payment/success", methods=["GET", "POST"])
def payment_success():
    order_id = request.values.get("razorpay_order_id")
    payment_id = request.values.get("razorpay_payment_id")
    signature = request.values.get("razorpay_signature")
    order = payment_service.get_order(order_id) if order_id else None
    verified = False
    if order_id and payment_id and signature:
        verified = payment_service.verify_payment_signature(
            order_id=order_id,
            payment_id=payment_id,
            signature=signature,
        )
    return render_template(
        "payment_status.html",
        page_title="Payment Received",
        status_kind="pending" if not verified else "success",
        title="Payment Received",
        message="Your payment details were received.",
        detail="Premium activation is completed only after the Razorpay webhook confirms a captured payment.",
        order=order,
        verified=verified,
        bot_url=BOT_URL,
        admin_authenticated=web_identity_service.is_admin_authenticated(),
    )


@premium_blueprint.route("/payment/cancel")
def payment_cancel():
    order_id = request.args.get("razorpay_order_id")
    if order_id:
        payment_service.set_order_status_if_not_paid(order_id, "cancelled")
    return render_template(
        "payment_status.html",
        page_title="Payment Cancelled",
        status_kind="failure",
        title="Payment Cancelled",
        message="The payment was not completed.",
        detail="You can return to the premium page and try again whenever you are ready.",
        order=payment_service.get_order(order_id) if order_id else None,
        verified=False,
        bot_url=BOT_URL,
        admin_authenticated=web_identity_service.is_admin_authenticated(),
    )


@premium_blueprint.route("/payment/failed")
def payment_failed():
    order_id = request.args.get("razorpay_order_id")
    reason = request.args.get("reason") or "Payment verification failed before completion."
    if order_id:
        payment_service.set_order_status_if_not_paid(order_id, "failed")
    return render_template(
        "payment_status.html",
        page_title="Payment Failed",
        status_kind="failure",
        title="Payment Failed",
        message="The payment could not be completed.",
        detail=reason,
        order=payment_service.get_order(order_id) if order_id else None,
        verified=False,
        bot_url=BOT_URL,
        admin_authenticated=web_identity_service.is_admin_authenticated(),
    )


@premium_blueprint.route("/webhook", methods=["POST"])
@premium_blueprint.route("/webhook/razorpay", methods=["POST"])
def razorpay_webhook():
    raw_body = request.get_data()
    signature = request.headers.get("X-Razorpay-Signature", "")
    event_id = request.headers.get("X-Razorpay-Event-Id")

    if not payment_service.verify_webhook_signature(raw_body, signature):
        return jsonify({"detail": "Invalid webhook signature"}), 401

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        return jsonify({"detail": "Invalid webhook payload"}), 400

    derived_event_id = (
        event_id
        or payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id")
        or hashlib.sha256(raw_body).hexdigest()
    )
    result = payment_service.process_captured_payment(derived_event_id, payload)
    return jsonify(result)
