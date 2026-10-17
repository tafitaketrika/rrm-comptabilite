from datetime import datetime, date
from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.models.budget import Budget, BudgetLine
from app.models.entry import JournalLine, JournalEntry
from app.models.account import Account
from app.models.cost_center import CostCenter
from app.models.period import Period
from app.models.operator import Operator
from app import db
from sqlalchemy import func

budgets_bp = Blueprint('budgets', __name__)


def _can_edit():
    return current_user.is_admin() or current_user.role in ('comptable', 'responsable_site')


def _leaf_accounts(accounts):
    """Comptes feuilles uniquement (ex. 01.02.01.005).
    Utilise level >= 4 si présent, sinon longueur code >= 8,
    et exclut tout compte parent d'un autre."""
    def norm(c):
        d = str(c or '').replace(' ', '').replace('.', '').replace('-', '')
        if len(d) == 8 and not d.startswith('0'):
            d = '0' + d
        return d
    norm_list = [norm(a.code) for a in accounts]
    leaf = []
    for a, n in zip(accounts, norm_list):
        lvl = getattr(a, 'level', None) or 0
        if lvl and lvl < 4:
            continue
        if len(n) < 8:
            continue
        if any(other != n and other.startswith(n) for other in norm_list):
            continue
        leaf.append(a)
    return leaf


def _allowed_accounts():
    """Comptes feuilles accessibles selon les droits de l'utilisateur connecté."""
    q = Account.query.filter_by(is_active=True).order_by(Account.code)
    accounts = q.all()
    allowed = current_user.allowed_account_ids()
    if allowed is not None:
        accounts = [a for a in accounts if a.id in allowed]
    accounts = _leaf_accounts(accounts)
    return accounts


@budgets_bp.route('/')
@login_required
def list_budgets():
    budgets = Budget.query.order_by(Budget.created_at.desc()).all()
    grand_total = sum(float(b.total_mga or 0) for b in budgets)
    return render_template('budgets/list.html', budgets=budgets, can_edit=_can_edit(), grand_total=grand_total)


@budgets_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_budget():
    if not _can_edit():
        abort(403)
    
    cost_centers = CostCenter.query.filter_by(is_active=True).all()
    periods = Period.query.order_by(Period.start_date.desc()).all()
    accounts = _allowed_accounts()
    operators = Operator.query.filter_by(is_active=True).order_by(Operator.name).all()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        start_str = request.form.get('start_date', '').strip()
        end_str = request.form.get('end_date', '').strip()
        cost_center_id = request.form.get('cost_center_id') or None
        
        if not name:
            flash('Le titre du budget est obligatoire.', 'danger')
            return render_template('budgets/form.html', cost_centers=cost_centers, periods=periods, accounts=accounts, operators=operators, budget=None, lines=None, today=date.today().strftime('%d/%m/%y'))
        
        # Code auto : BUD-AAMMJJ-NNN
        today_d = date.today()
        prefix = f"BUD-{today_d.strftime('%y%m%d')}-"
        existing = Budget.query.filter(Budget.code.like(prefix + '%')).count()
        code = f"{prefix}{existing + 1:03d}"
        
        start_date = end_date = None
        for fmt in ('%d/%m/%y', '%d/%m/%Y', '%Y-%m-%d'):
            try:
                if start_str:
                    start_date = datetime.strptime(start_str, fmt).date()
                if end_str:
                    end_date = datetime.strptime(end_str, fmt).date()
                break
            except ValueError:
                continue
        
        budget = Budget(
            code=code,
            name=name,
            currency=request.form.get('currency') or 'MGA',
            assigned_to_json=__import__('json').dumps([int(x) for x in request.form.getlist('assigned_to') if x.isdigit()]),
            cc_to_json=__import__('json').dumps([int(x) for x in request.form.getlist('cc_to') if x.isdigit()]),
            start_date=start_date,
            end_date=end_date,
            cost_center_id=int(cost_center_id) if cost_center_id else None,
            created_by_id=current_user.id
        )
        db.session.add(budget)
        db.session.flush()
        
        # Lignes dynamiques
        descs = request.form.getlist('line_description')
        qtys = request.form.getlist('line_quantity')
        qty_units = request.form.getlist('line_quantity_unit')
        occs = request.form.getlist('line_occurrence')
        occ_units = request.form.getlist('line_occurrence_unit')
        costs = request.form.getlist('line_unit_cost')
        acc_ids = request.form.getlist('line_account_id')
        
        total_mga = Decimal('0')
        for i, desc in enumerate(descs):
            desc = desc.strip()
            if not desc:
                continue
            try:
                qty = Decimal(str(qtys[i] or '1').replace(',', '.'))
                occ = Decimal(str(occs[i] or '1').replace(',', '.'))
                unit_cost = Decimal(str(costs[i] or '0').replace(',', '.').replace(' ', ''))
            except Exception:
                qty, occ, unit_cost = Decimal('1'), Decimal('1'), Decimal('0')
            line_total = qty * occ * unit_cost
            total_mga += line_total
            aid = None
            if i < len(acc_ids) and acc_ids[i]:
                try:
                    aid = int(acc_ids[i])
                except ValueError:
                    aid = None
            if not aid:
                continue  # compte obligatoire
            if not aid:
                continue
            line = BudgetLine(
                budget_id=budget.id,
                category=None,
                description=desc,
                quantity=qty,
                quantity_unit=(qty_units[i] if i < len(qty_units) else '') or None,
                occurrence=occ,
                occurrence_unit=(occ_units[i] if i < len(occ_units) else '') or None,
                unit_cost_mga=unit_cost,
                total_cost_mga=line_total,
                account_id=aid,
                is_ordinary=True
            )
            db.session.add(line)
        
        budget.total_mga = total_mga
        db.session.commit()
        # pas de message flash de création
        return redirect(url_for('budgets.view_budget', budget_id=budget.id))
    
    return render_template('budgets/form.html', cost_centers=cost_centers, periods=periods, accounts=accounts, operators=operators, budget=None, lines=None, today=date.today().strftime('%d/%m/%y'))


def _norm_code(c):
    d = str(c or '').replace(' ', '').replace('.', '').replace('-', '')
    if len(d) == 8 and not d.startswith('0'):
        d = '0' + d
    return d


@budgets_bp.route('/<int:budget_id>')
@login_required
def view_budget(budget_id):
    budget = Budget.query.get_or_404(budget_id)
    lines = BudgetLine.query.filter_by(budget_id=budget.id).all()
    def sort_key(l):
        if l.account:
            return (_norm_code(l.account.code), l.id)
        return ('zzz' + (l.category or ''), l.id)
    lines = sorted(lines, key=sort_key)

    # Noms hiérarchie + sommes partielles
    accounts = {a.code: a for a in Account.query.all()}
    # index also by normalized
    by_norm = {}
    for a in accounts.values():
        by_norm[_norm_code(a.code)] = a

    section_names, chapter_names, paragraph_names = {}, {}, {}
    section_totals, chapter_totals, paragraph_totals = {}, {}, {}
    for l in lines:
        code = _norm_code(l.account.code) if l.account else ''
        tot = float(l.total_cost_mga or 0)
        if len(code) >= 2:
            sec = code[:2]
            section_totals[sec] = section_totals.get(sec, 0) + tot
            if sec not in section_names:
                acc = by_norm.get(sec)
                section_names[sec] = acc.name if acc else 'Section'
        if len(code) >= 4:
            chap = code[:4]
            chapter_totals[chap] = chapter_totals.get(chap, 0) + tot
            if chap not in chapter_names:
                acc = by_norm.get(chap)
                chapter_names[chap] = acc.name if acc else 'Chapitre'
        if len(code) >= 6:
            par = code[:6]
            paragraph_totals[par] = paragraph_totals.get(par, 0) + tot
            if par not in paragraph_names:
                acc = by_norm.get(par)
                paragraph_names[par] = acc.name if acc else 'Paragraphe'

    return render_template(
        'budgets/view.html',
        budget=budget,
        lines=lines,
        can_edit=_can_edit(),
        section_names=section_names,
        chapter_names=chapter_names,
        paragraph_names=paragraph_names,
        section_totals=section_totals,
        chapter_totals=chapter_totals,
        paragraph_totals=paragraph_totals,
    )


@budgets_bp.route('/<int:budget_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_budget(budget_id):
    if not _can_edit():
        abort(403)
    budget = Budget.query.get_or_404(budget_id)
    cost_centers = CostCenter.query.filter_by(is_active=True).all()
    periods = Period.query.order_by(Period.start_date.desc()).all()
    accounts = _allowed_accounts()
    operators = Operator.query.filter_by(is_active=True).order_by(Operator.name).all()
    lines = BudgetLine.query.filter_by(budget_id=budget.id).order_by(BudgetLine.id).all()
    
    if request.method == 'POST':
        budget.name = request.form.get('name', '').strip() or budget.name
        budget.currency = request.form.get('currency') or budget.currency or 'MGA'
        import json as _json
        budget.assigned_to_json = _json.dumps([int(x) for x in request.form.getlist('assigned_to') if str(x).isdigit()])
        budget.cc_to_json = _json.dumps([int(x) for x in request.form.getlist('cc_to') if str(x).isdigit()])
        start_str = request.form.get('start_date', '').strip()
        end_str = request.form.get('end_date', '').strip()
        cost_center_id = request.form.get('cost_center_id') or None
        budget.cost_center_id = int(cost_center_id) if cost_center_id else None
        
        for fmt in ('%d/%m/%y', '%d/%m/%Y', '%Y-%m-%d'):
            try:
                if start_str:
                    budget.start_date = datetime.strptime(start_str, fmt).date()
                if end_str:
                    budget.end_date = datetime.strptime(end_str, fmt).date()
                break
            except ValueError:
                continue
        
        # Remplacer les lignes
        BudgetLine.query.filter_by(budget_id=budget.id).delete()
        descs = request.form.getlist('line_description')
        qtys = request.form.getlist('line_quantity')
        qty_units = request.form.getlist('line_quantity_unit')
        occs = request.form.getlist('line_occurrence')
        occ_units = request.form.getlist('line_occurrence_unit')
        costs = request.form.getlist('line_unit_cost')
        acc_ids = request.form.getlist('line_account_id')
        
        total_mga = Decimal('0')
        for i, desc in enumerate(descs):
            desc = desc.strip()
            if not desc:
                continue
            try:
                qty = Decimal(str(qtys[i] or '1').replace(',', '.'))
                occ = Decimal(str(occs[i] or '1').replace(',', '.'))
                unit_cost = Decimal(str(costs[i] or '0').replace(',', '.').replace(' ', ''))
            except Exception:
                qty, occ, unit_cost = Decimal('1'), Decimal('1'), Decimal('0')
            line_total = qty * occ * unit_cost
            total_mga += line_total
            aid = None
            if i < len(acc_ids) and acc_ids[i]:
                try:
                    aid = int(acc_ids[i])
                except ValueError:
                    aid = None
            db.session.add(BudgetLine(
                budget_id=budget.id,
                category=None,
                description=desc,
                quantity=qty,
                quantity_unit=(qty_units[i] if i < len(qty_units) else '') or None,
                occurrence=occ,
                occurrence_unit=(occ_units[i] if i < len(occ_units) else '') or None,
                unit_cost_mga=unit_cost,
                total_cost_mga=line_total,
                account_id=aid,
                is_ordinary=True
            ))
        
        budget.total_mga = total_mga
        db.session.commit()
        flash('Budget mis à jour.', 'success')
        return redirect(url_for('budgets.view_budget', budget_id=budget.id))
    
    return render_template('budgets/form.html', budget=budget, lines=lines,
                           cost_centers=cost_centers, periods=periods, accounts=accounts, operators=operators, today=date.today().strftime('%d/%m/%y'))


@budgets_bp.route('/vs-reel')
@login_required
def budget_vs_actual():
    budget = Budget.query.order_by(Budget.created_at.desc()).first()
    real_by_account = db.session.query(
        Account.code,
        Account.name,
        func.sum(JournalLine.amount_mga).filter(JournalLine.side == 'debit').label('debit'),
        func.sum(JournalLine.amount_mga).filter(JournalLine.side == 'credit').label('credit'),
    ).join(JournalLine, JournalLine.account_id == Account.id)\
     .group_by(Account.id)\
     .order_by(Account.code)\
     .all()
    return render_template('budgets/vs_reel.html', budget=budget, real_by_account=real_by_account)
