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


def _allowed_accounts():
    """Comptes accessibles selon les droits de l'utilisateur connecté."""
    q = Account.query.filter_by(is_active=True).order_by(Account.code)
    accounts = q.all()
    allowed = current_user.allowed_account_ids()
    if allowed is not None:
        accounts = [a for a in accounts if a.id in allowed]
    return accounts


@budgets_bp.route('/')
@login_required
def list_budgets():
    budgets = Budget.query.order_by(Budget.created_at.desc()).all()
    return render_template('budgets/list.html', budgets=budgets, can_edit=_can_edit())


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
        code = request.form.get('code', '').strip()
        name = request.form.get('name', '').strip()
        start_str = request.form.get('start_date', '').strip()
        end_str = request.form.get('end_date', '').strip()
        cost_center_id = request.form.get('cost_center_id') or None
        
        if not code or not name:
            flash('Code et nom du budget sont obligatoires.', 'danger')
            return render_template('budgets/form.html', cost_centers=cost_centers, periods=periods, accounts=accounts, operators=operators, budget=None, lines=None, today=date.today().strftime('%d/%m/%y'))
        
        if Budget.query.filter_by(code=code).first():
            flash('Ce code budget existe déjà.', 'danger')
            return render_template('budgets/form.html', cost_centers=cost_centers, periods=periods, accounts=accounts, operators=operators, budget=None, lines=None, today=date.today().strftime('%d/%m/%y'))
        
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
        flash(f'Budget {code} créé avec succès.', 'success')
        return redirect(url_for('budgets.view_budget', budget_id=budget.id))
    
    return render_template('budgets/form.html', cost_centers=cost_centers, periods=periods, accounts=accounts, operators=operators, budget=None, lines=None, today=date.today().strftime('%d/%m/%y'))


@budgets_bp.route('/<int:budget_id>')
@login_required
def view_budget(budget_id):
    budget = Budget.query.get_or_404(budget_id)
    lines = BudgetLine.query.filter_by(budget_id=budget.id).order_by(BudgetLine.id).all()
    # Trier par code compte si lié
    lines = sorted(lines, key=lambda l: (l.category or (l.account.code if l.account else 'zzz'), l.id))
    return render_template(
        'budgets/view.html',
        budget=budget,
        lines=lines,
        can_edit=_can_edit()
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
