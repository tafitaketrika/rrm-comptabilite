from datetime import datetime
from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.models.budget import Budget, BudgetLine
from app.models.entry import JournalLine, JournalEntry
from app.models.account import Account
from app.models.cost_center import CostCenter
from app.models.period import Period
from app import db
from sqlalchemy import func

budgets_bp = Blueprint('budgets', __name__)


def _can_edit():
    return current_user.is_admin() or current_user.role in ('comptable', 'responsable_site')


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
    
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        name = request.form.get('name', '').strip()
        start_str = request.form.get('start_date', '').strip()
        end_str = request.form.get('end_date', '').strip()
        cost_center_id = request.form.get('cost_center_id') or None
        
        if not code or not name:
            flash('Code et nom du budget sont obligatoires.', 'danger')
            return render_template('budgets/form.html', cost_centers=cost_centers, periods=periods, budget=None)
        
        if Budget.query.filter_by(code=code).first():
            flash('Ce code budget existe déjà.', 'danger')
            return render_template('budgets/form.html', cost_centers=cost_centers, periods=periods, budget=None)
        
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
        cats = request.form.getlist('line_category')
        qtys = request.form.getlist('line_quantity')
        qty_units = request.form.getlist('line_quantity_unit')
        occs = request.form.getlist('line_occurrence')
        occ_units = request.form.getlist('line_occurrence_unit')
        costs = request.form.getlist('line_unit_cost')
        
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
            line = BudgetLine(
                budget_id=budget.id,
                category=(cats[i] if i < len(cats) else '') or None,
                description=desc,
                quantity=qty,
                quantity_unit=(qty_units[i] if i < len(qty_units) else '') or None,
                occurrence=occ,
                occurrence_unit=(occ_units[i] if i < len(occ_units) else '') or None,
                unit_cost_mga=unit_cost,
                total_cost_mga=line_total,
                is_ordinary=True
            )
            db.session.add(line)
        
        budget.total_mga = total_mga
        db.session.commit()
        flash(f'Budget {code} créé avec succès.', 'success')
        return redirect(url_for('budgets.view_budget', budget_id=budget.id))
    
    return render_template('budgets/form.html', cost_centers=cost_centers, periods=periods, budget=None)


@budgets_bp.route('/<int:budget_id>')
@login_required
def view_budget(budget_id):
    budget = Budget.query.get_or_404(budget_id)
    lines = BudgetLine.query.filter_by(budget_id=budget.id).order_by(BudgetLine.id).all()
    ordinary = [l for l in lines if l.is_ordinary]
    extraordinary = [l for l in lines if not l.is_ordinary]
    return render_template(
        'budgets/view.html',
        budget=budget,
        ordinary=ordinary,
        extraordinary=extraordinary,
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
        cats = request.form.getlist('line_category')
        qtys = request.form.getlist('line_quantity')
        qty_units = request.form.getlist('line_quantity_unit')
        occs = request.form.getlist('line_occurrence')
        occ_units = request.form.getlist('line_occurrence_unit')
        costs = request.form.getlist('line_unit_cost')
        
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
            db.session.add(BudgetLine(
                budget_id=budget.id,
                category=(cats[i] if i < len(cats) else '') or None,
                description=desc,
                quantity=qty,
                quantity_unit=(qty_units[i] if i < len(qty_units) else '') or None,
                occurrence=occ,
                occurrence_unit=(occ_units[i] if i < len(occ_units) else '') or None,
                unit_cost_mga=unit_cost,
                total_cost_mga=line_total,
                is_ordinary=True
            ))
        
        budget.total_mga = total_mga
        db.session.commit()
        flash('Budget mis à jour.', 'success')
        return redirect(url_for('budgets.view_budget', budget_id=budget.id))
    
    return render_template('budgets/form.html', budget=budget, lines=lines,
                           cost_centers=cost_centers, periods=periods)


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
