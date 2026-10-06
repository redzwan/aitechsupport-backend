"""Send renewal-reminder emails to clients whose subscription is due within 3 days.

Run by a daily cron on the VPS:
    cd ~/aitechsupport-backend && venv/bin/python scripts/send_renewal_reminders.py

Mirrors POST /admin/billing/send-renewal-reminders (app/api/v1/endpoints/admin.py)
but runs standalone so it doesn't need an admin JWT. Safe to run repeatedly —
billing.subscriptions_due_for_reminder() only returns subscriptions that haven't
already been reminded for their current renewal cycle.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

from app.db.session import SessionLocal
from app.core import billing, email as email_service
from app.models.organization import Organization
from app.models.user import User


def main() -> None:
    db = SessionLocal()
    try:
        due = billing.subscriptions_due_for_reminder(db)
        sent = 0
        for sub in due:
            org = db.query(Organization).filter(Organization.id == sub.organization_id).first()
            owner = (
                db.query(User)
                .filter(User.organization_id == sub.organization_id, User.role == "owner")
                .first()
            )
            if not org or not owner:
                continue
            pkg = billing.package_for(db, sub.plan)
            email_service.send_template_bg(
                owner.email,
                "renewal_reminder",
                {
                    "name": org.name,
                    "plan": pkg.name if pkg else sub.plan,
                    "next_billing_date": sub.next_billing_date.strftime("%d %b %Y"),
                    "dashboard_url": f"{billing.settings.FRONTEND_URL}/dashboard/billing",
                },
            )
            sub.last_reminder_sent = datetime.utcnow()
            sent += 1
        db.commit()
        print(f"renewal reminders: {sent} sent, {len(due)} due")
    finally:
        db.close()


if __name__ == "__main__":
    main()
