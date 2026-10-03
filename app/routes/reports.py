from flask import Blueprint, render_template
from flask_login import login_required
from app.models.entry import JournalEntry, JournalLine
from app.models.account import Account
from app import db
from sqlalchemy import func

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/')
@login_required
def index():
    return render_template('reports/index.html')


@reports_bp.route('/trial-balance')
@login_required
def trial_balance():
    """Résumé des comptes (solde par compte)."""
    # Agrégation simple
    results = db.session.query(
        Account.code,
        Account.name,
        func.sum(JournalLine.amount_mga).filter(JournalLine.side == 'debit').label('debit_mga'),
        func.sum(JournalLine.amount_mga).filter(JournalLine.side == 'credit').label('credit_mga'),
        func.sum(JournalLine.amount_usd).filter(JournalLine.side == 'debit').label('debit_usd'),
        func.sum(JournalLine.amount_usd).filter(JournalLine.side == 'credit').label('credit_usd'),
        func.sum(JournalLine.amount_eur).filter(JournalLine.side == 'debit').label('debit_eur'),
        func.sum(JournalLine.amount_eur).filter(JournalLine.side == 'credit').label('credit_eur'),
    ).join(JournalLine, JournalLine.account_id == Account.id)\
     .group_by(Account.id)\
     .order_by(Account.code)\
     .all()
    
    return render_template('reports/trial_balance.html', results=results)
