"""bank transfer fallback payments + subscription renewal dates

Revision ID: b2c3d4e5f6a7
Revises: 1a2b3c4d5e6f
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = '1a2b3c4d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # payments: which gateway collected it + a customer-supplied note for manual
    # bank transfers (no webhook to confirm those, so a human note is the input
    # an admin confirms against).
    op.add_column('payments', sa.Column('method', sa.String(), nullable=False, server_default='billplz'))
    op.add_column('payments', sa.Column('reference_note', sa.Text(), nullable=True))
    op.add_column('payments', sa.Column('reported_at', sa.DateTime(), nullable=True))
    op.alter_column('payments', 'method', server_default=None)

    # subscriptions: admin-set renewal cycle so reminders/manual confirmation know
    # when the next payment is due.
    op.add_column('subscriptions', sa.Column('start_date', sa.DateTime(), nullable=True))
    op.add_column('subscriptions', sa.Column('next_billing_date', sa.DateTime(), nullable=True))
    op.add_column('subscriptions', sa.Column('last_reminder_sent', sa.DateTime(), nullable=True))

    # Seed the bank-transfer + renewal email templates (see 7c318f1875c9 for pattern).
    templates = sa.table(
        'email_templates',
        sa.column('key', sa.String), sa.column('name', sa.String),
        sa.column('subject', sa.String), sa.column('body_html', sa.Text),
        sa.column('is_active', sa.Boolean),
    )
    op.bulk_insert(templates, [
        {
            'key': 'bank_transfer_instructions', 'name': 'Bank transfer instructions', 'is_active': True,
            'subject': 'How to pay for your AiTechSupport {plan} plan by bank transfer',
            'body_html': (
                '<p>Hi {name},</p>'
                '<p>To activate the <strong>{plan}</strong> plan (RM{amount}/month), transfer to:</p>'
                '<p><strong>{bank_name}</strong><br/>Account name: {account_name}<br/>'
                'Account number: {account_number}</p>'
                '<p>You can also scan the QR code on your <a href="{dashboard_url}">Billing page</a> '
                'from your banking app.</p>'
                '<p>After transferring, let us know on WhatsApp ({whatsapp_number}) or report it on the '
                'Billing page so we can confirm and activate your plan.</p>'
                '<p>— The AiTechSupport team</p>'
            ),
        },
        {
            'key': 'bank_transfer_reported', 'name': 'Bank transfer reported', 'is_active': True,
            'subject': "We've received your payment notice",
            'body_html': (
                '<p>Hi {name},</p>'
                '<p>Thanks — we\'ve noted your bank transfer for the <strong>{plan}</strong> plan '
                '(RM{amount}). We\'ll confirm receipt and activate your plan shortly.</p>'
                '<p>— The AiTechSupport team</p>'
            ),
        },
        {
            'key': 'payment_confirmed', 'name': 'Payment confirmed', 'is_active': True,
            'subject': 'Your AiTechSupport payment was confirmed',
            'body_html': (
                '<p>Hi {name},</p>'
                '<p>We\'ve confirmed your payment and activated the <strong>{plan}</strong> plan. '
                'Your next payment is due around <strong>{next_billing_date}</strong>.</p>'
                '<p><a href="{dashboard_url}">Open your dashboard</a></p>'
                '<p>— The AiTechSupport team</p>'
            ),
        },
        {
            'key': 'renewal_reminder', 'name': 'Renewal reminder', 'is_active': True,
            'subject': 'Your AiTechSupport plan renews soon',
            'body_html': (
                '<p>Hi {name},</p>'
                '<p>Your <strong>{plan}</strong> plan is due for renewal around '
                '<strong>{next_billing_date}</strong>. Pay by FPX/card on your '
                '<a href="{dashboard_url}">Billing page</a>, or by bank transfer '
                '(details on the same page) and let us know once it\'s done.</p>'
                '<p>— The AiTechSupport team</p>'
            ),
        },
    ])


def downgrade() -> None:
    op.execute("DELETE FROM email_templates WHERE key IN "
               "('bank_transfer_instructions', 'bank_transfer_reported', 'payment_confirmed', 'renewal_reminder')")
    op.drop_column('subscriptions', 'last_reminder_sent')
    op.drop_column('subscriptions', 'next_billing_date')
    op.drop_column('subscriptions', 'start_date')
    op.drop_column('payments', 'reported_at')
    op.drop_column('payments', 'reference_note')
    op.drop_column('payments', 'method')
