from datetime import datetime, date
from flask import Blueprint, render_template, request
from flask_login import login_required
from app.models.entry import JournalEntry, JournalLine
from app.models.account import Account
from app import db
from sqlalchemy import func
from collections import defaultdict

reports_bp = Blueprint('reports', __name__)


def _parse_date(s):
    s = (s or '').strip()
    if not s:
        return None
    for fmt in ('%d/%m/%y', '%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _norm_code(c):
    d = str(c or '').replace(' ', '').replace('.', '').replace('-', '')
    if len(d) == 8 and not d.startswith('0'):
        d = '0' + d
    return d


@reports_bp.route('/')
@login_required
def index():
    return render_template('reports/index.html')


@reports_bp.route('/trial-balance')
@login_required
def trial_balance():
    """Balance des comptes (Résumé) — hiérarchie + filtre dates."""
    date_from = _parse_date(request.args.get('date_from'))
    date_to = _parse_date(request.args.get('date_to'))

    q = db.session.query(
        Account.id,
        Account.code,
        Account.name,
        Account.level,
        func.coalesce(func.sum(JournalLine.amount_mga).filter(JournalLine.side == 'debit'), 0).label('debit_mga'),
        func.coalesce(func.sum(JournalLine.amount_mga).filter(JournalLine.side == 'credit'), 0).label('credit_mga'),
        func.coalesce(func.sum(JournalLine.amount_usd).filter(JournalLine.side == 'debit'), 0).label('debit_usd'),
        func.coalesce(func.sum(JournalLine.amount_usd).filter(JournalLine.side == 'credit'), 0).label('credit_usd'),
        func.coalesce(func.sum(JournalLine.amount_eur).filter(JournalLine.side == 'debit'), 0).label('debit_eur'),
        func.coalesce(func.sum(JournalLine.amount_eur).filter(JournalLine.side == 'credit'), 0).label('credit_eur'),
    ).join(JournalLine, JournalLine.account_id == Account.id)\
     .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)

    if date_from:
        q = q.filter(JournalEntry.entry_date >= date_from)
    if date_to:
        q = q.filter(JournalEntry.entry_date <= date_to)

    results = q.group_by(Account.id).order_by(Account.code).all()

    # Noms des niveaux parents
    all_accounts = { _norm_code(a.code): a for a in Account.query.filter_by(is_active=True).all() }

    def name_for(prefix):
        a = all_accounts.get(prefix)
        if a:
            return a.name
        # fallback labels
        if len(prefix) == 2:
            return 'Section'
        if len(prefix) == 4:
            return 'Chapitre'
        if len(prefix) == 6:
            return 'Paragraphe'
        return ''

    # Agrégation par préfixe (section / chapitre / paragraphe)
    agg = defaultdict(lambda: {
        'debit_mga': 0, 'credit_mga': 0,
        'debit_usd': 0, 'credit_usd': 0,
        'debit_eur': 0, 'credit_eur': 0,
    })
    leaves = []
    for r in results:
        n = _norm_code(r.code)
        row = {
            'code': r.code,
            'norm': n,
            'name': r.name,
            'level': 4,
            'debit_mga': float(r.debit_mga or 0),
            'credit_mga': float(r.credit_mga or 0),
            'debit_usd': float(r.debit_usd or 0),
            'credit_usd': float(r.credit_usd or 0),
            'debit_eur': float(r.debit_eur or 0),
            'credit_eur': float(r.credit_eur or 0),
        }
        leaves.append(row)
        for plen in (2, 4, 6):
            if len(n) >= plen:
                p = n[:plen]
                for k in ('debit_mga', 'credit_mga', 'debit_usd', 'credit_usd', 'debit_eur', 'credit_eur'):
                    agg[p][k] += row[k]

    # Construire arbre ordonné
    rows = []
    seen = set()
    for leaf in sorted(leaves, key=lambda x: x['norm']):
        n = leaf['norm']
        for plen, lvl, cls in ((2, 1, 'sec'), (4, 2, 'chap'), (6, 3, 'par')):
            if len(n) >= plen:
                p = n[:plen]
                if p not in seen:
                    seen.add(p)
                    a = agg[p]
                    rows.append({
                        'code': p,
                        'norm': p,
                        'name': name_for(p),
                        'level': lvl,
                        'cls': cls,
                        **a,
                    })
        leaf['cls'] = 'leaf'
        rows.append(leaf)

    return render_template(
        'reports/trial_balance.html',
        rows=rows,
        date_from=date_from.strftime('%d/%m/%y') if date_from else '',
        date_to=date_to.strftime('%d/%m/%y') if date_to else '',
    )
