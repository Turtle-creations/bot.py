from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, url_for

from config import ADMIN_PASSWORD
from services.payment_service_db import payment_service
from services.web_admin_service import web_admin_service
from services.web_identity_service import web_identity_service


admin_blueprint = Blueprint("admin", __name__)


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not web_identity_service.is_admin_authenticated():
            flash("Please log in as admin first.", "error")
            return redirect(url_for("admin.admin_login"))
        return view_func(*args, **kwargs)

    return wrapper


@admin_blueprint.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    web_identity_service.get_or_create_user()
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            web_identity_service.mark_admin_authenticated()
            flash("Admin access granted.", "success")
            return redirect(url_for("admin.admin_dashboard"))
        flash("Invalid admin password.", "error")
    return render_template("admin_login.html", page_title="Admin Login")


@admin_blueprint.route("/admin/logout", methods=["POST"])
def admin_logout():
    web_identity_service.clear_admin_authenticated()
    flash("Admin session closed.", "success")
    return redirect(url_for("pages.home"))


@admin_blueprint.route("/admin", methods=["GET", "POST"])
@admin_required
def admin_dashboard():
    if request.method == "POST":
        plan_type = request.form.get("plan_type", "")
        amount = request.form.get("amount", "")
        try:
            payment_service.update_premium_price(plan_type, amount)
            flash("Premium price updated successfully.", "success")
        except Exception as exc:
            flash(str(exc), "error")
        return redirect(url_for("admin.admin_dashboard"))

    dashboard = web_admin_service.dashboard_data()
    return render_template("admin_dashboard.html", page_title="Admin Panel", **dashboard)
