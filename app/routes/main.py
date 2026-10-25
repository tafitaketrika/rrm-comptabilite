from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import func, and_

from app.models.entry import JournalEntry
from app.models.account import Account
from app.models.period import Period
from app.models.user import User
from app.models.budget import Budget
from app import db

main_bp = Blueprint('main', __name__)


def _dec(val):
    if val is None:
        return Decimal('0')
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal('0')


def _fmt_mga(val):
    n = int(round(float(_dec(val))))
    return f"{n:,}".replace(',', ' ')


def _fmt_fx(val):
    n = float(_dec(val))
    return f"{n:,.2f}".replace(',', ' ')


def _fmt_pct(val):
    try:
        return f"{float(val):.1f}"
    except Exception:
        return "0.0"


def _month_bounds(d):
    """Premier et dernier jour du mois de la date d."""
    start = d.replace(day=1)
    last = monthrange(d.year, d.month)[1]
    end = d.replace(day=last)
    return start, end


def _prev_month_start(d):
    first = d.replace(day=1)
    prev_last = first - timedelta(days=1)
    return prev_last.replace(day=1)


@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(current_user.first_allowed_url())
    return redirect(url_for('auth.login'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    if not current_user.is_admin() and not current_user.has_module('dashboard'):
        flash("Vous n'avez pas accès au tableau de bord.", 'warning')
        return redirect(current_user.first_allowed_url())

    today = date.today()
    month_start, month_end = _month_bounds(today)
    prev_start = _prev_month_start(today)
    prev_end = month_start - timedelta(days=1)

    total_entries = JournalEntry.query.count()
    total_accounts = Account.query.filter_by(is_active=True).count()
    current_period = Period.query.filter_by(is_current=True).first()
    total_users = User.query.filter_by(is_active=True).count()
    total_budgets = Budget.query.count()

    month_entries_count = JournalEntry.query.filter(
        JournalEntry.entry_date >= month_start,
        JournalEntry.entry_date <= month_end,
    ).count()
    drafts_count = JournalEntry.query.filter_by(status='draft').count()
    posted_count = JournalEntry.query.filter_by(status='posted').count()

    # Totaux mois en cours
    month_totals = db.session.query(
        func.coalesce(func.sum(JournalEntry.total_mga_debit), 0),
        func.coalesce(func.sum(JournalEntry.total_usd_debit), 0),
        func.coalesce(func.sum(JournalEntry.total_eur_debit), 0),
    ).filter(
        JournalEntry.entry_date >= month_start,
        JournalEntry.entry_date <= month_end,
    ).first()

    month_mga = _dec(month_totals[0] if month_totals else 0)
    month_usd = _dec(month_totals[1] if month_totals else 0)
    month_eur = _dec(month_totals[2] if month_totals else 0)

    # Totaux mois précédent (pour évolution)
    prev_totals = db.session.query(
        func.coalesce(func.sum(JournalEntry.total_mga_debit), 0),
    ).filter(
        JournalEntry.entry_date >= prev_start,
        JournalEntry.entry_date <= prev_end,
    ).scalar()
    prev_mga = _dec(prev_totals)

    if prev_mga > 0:
        evol_mga_pct = float((month_mga - prev_mga) / prev_mga * 100)
    elif month_mga > 0:
        evol_mga_pct = 100.0
    else:
        evol_mga_pct = 0.0

    # Ticket moyen (MGA) du mois
    if month_entries_count > 0:
        avg_ticket = month_mga / month_entries_count
    else:
        avg_ticket = Decimal('0')

    # Taux de validation global
    closed = drafts_count + posted_count
    if closed > 0:
        validation_rate = float(posted_count) / closed * 100
    else:
        validation_rate = 0.0

    # Budgets
    budget_total_mga = _dec(
        db.session.query(func.coalesce(func.sum(Budget.total_mga), 0)).scalar()
    )
    budgets_month_count = Budget.query.filter(
        Budget.created_at >= datetime.combine(month_start, datetime.min.time())
    ).count()

    # Budget vs réel (mois) : exécution = réel / budget * 100
    if budget_total_mga > 0:
        execution_rate = float(month_mga / budget_total_mga * 100)
        budget_remaining = budget_total_mga - month_mga
    else:
        execution_rate = 0.0
        budget_remaining = Decimal('0')

    # Écritures non équilibrées
    unbalanced_count = JournalEntry.query.filter_by(is_balanced=False).count()

    month_label = today.strftime('%m/%Y')
    prev_label = prev_start.strftime('%m/%Y')

    return render_template(
        'main/dashboard.html',
        total_entries=total_entries,
        total_accounts=total_accounts,
        current_period=current_period,
        total_users=total_users,
        total_budgets=total_budgets,
        month_entries_count=month_entries_count,
        month_mga=month_mga,
        month_usd=month_usd,
        month_eur=month_eur,
        month_mga_fmt=_fmt_mga(month_mga),
        month_usd_fmt=_fmt_fx(month_usd),
        month_eur_fmt=_fmt_fx(month_eur),
        budget_total_mga=budget_total_mga,
        budget_total_mga_fmt=_fmt_mga(budget_total_mga),
        budgets_month_count=budgets_month_count,
        drafts_count=drafts_count,
        posted_count=posted_count,
        month_label=month_label,
        prev_label=prev_label,
        today=today,
        # Performance financière
        prev_mga=prev_mga,
        prev_mga_fmt=_fmt_mga(prev_mga),
        evol_mga_pct=evol_mga_pct,
        evol_mga_pct_fmt=_fmt_pct(evol_mga_pct),
        avg_ticket=avg_ticket,
        avg_ticket_fmt=_fmt_mga(avg_ticket),
        validation_rate=validation_rate,
        validation_rate_fmt=_fmt_pct(validation_rate),
        execution_rate=execution_rate,
        execution_rate_fmt=_fmt_pct(execution_rate),
        budget_remaining=budget_remaining,
        budget_remaining_fmt=_fmt_mga(budget_remaining),
        unbalanced_count=unbalanced_count,
    )


@main_bp.route('/import-demo-data', methods=['POST'])
@login_required
def import_demo_data():
    """Importe les écritures du Brouillard + le budget (réservé à l'admin)."""
    if not current_user.is_admin():
        abort(403)

    try:
        from app.utils.import_excel import import_brouillard_sample, import_budget_antsirabe
        import_brouillard_sample(admin_user_id=current_user.id)
        import_budget_antsirabe(admin_user_id=current_user.id)
        flash('Données de démonstration importées avec succès (Brouillard + Budget).', 'success')
    except Exception as e:
        flash(f'Erreur lors de l\'import : {str(e)}', 'danger')

    return redirect(url_for('main.dashboard'))
