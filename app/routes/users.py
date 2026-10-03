from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models.user import User, UserModulePermission, UserAccountPermission, AVAILABLE_MODULES
from app.models.operator import Operator
from app.models.cost_center import CostCenter
from app.models.account import Account

users_bp = Blueprint('users', __name__)


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _get_accounts_tree():
    """Retourne les comptes ordonnés pour l'arbre de permissions."""
    return Account.query.filter_by(is_active=True).order_by(Account.code).all()


def _save_permissions(user, form):
    """Enregistre les droits modules et comptes depuis le formulaire."""
    # Modules
    UserModulePermission.query.filter_by(user_id=user.id).delete()
    for code, _ in AVAILABLE_MODULES:
        if form.get(f'module_{code}') == 'on':
            db.session.add(UserModulePermission(user_id=user.id, module_code=code, allowed=True))
    
    # Comptes
    UserAccountPermission.query.filter_by(user_id=user.id).delete()
    for key, val in form.items():
        if key.startswith('account_') and val == 'on':
            try:
                acc_id = int(key.replace('account_', ''))
                db.session.add(UserAccountPermission(user_id=user.id, account_id=acc_id, allowed=True))
            except ValueError:
                pass


@users_bp.route('/')
@login_required
@admin_required
def list_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('users/list.html', users=users)


@users_bp.route('/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    operators = Operator.query.filter_by(is_active=True).all()
    cost_centers = CostCenter.query.filter_by(is_active=True).all()
    accounts = _get_accounts_tree()
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        full_name = request.form.get('full_name', '').strip()
        password = request.form.get('password', '')
        
        if not username or not full_name or not password:
            flash('Identifiant, nom complet et mot de passe sont obligatoires.', 'danger')
            return render_template('users/form.html', operators=operators, cost_centers=cost_centers,
                                   accounts=accounts, modules=AVAILABLE_MODULES, user=None)
        
        if User.query.filter_by(username=username).first():
            flash('Ce nom d\'utilisateur existe déjà.', 'danger')
            return render_template('users/form.html', operators=operators, cost_centers=cost_centers,
                                   accounts=accounts, modules=AVAILABLE_MODULES, user=None)
        
        user = User(
            username=username,
            email=f'{username}@lefourmi.local',
            full_name=full_name,
            role='comptable',
            created_by_id=current_user.id
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        _save_permissions(user, request.form)
        db.session.commit()
        flash(f'Utilisateur {username} créé avec succès.', 'success')
        return redirect(url_for('users.list_users'))
    
    return render_template('users/form.html', operators=operators, cost_centers=cost_centers,
                           accounts=accounts, modules=AVAILABLE_MODULES, user=None)


@users_bp.route('/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    operators = Operator.query.filter_by(is_active=True).all()
    cost_centers = CostCenter.query.filter_by(is_active=True).all()
    accounts = _get_accounts_tree()
    
    if request.method == 'POST':
        user.full_name = request.form.get('full_name', '').strip()
        user.is_active = request.form.get('is_active') == 'on'
        
        new_password = request.form.get('password', '').strip()
        if new_password:
            user.set_password(new_password)
        
        _save_permissions(user, request.form)
        db.session.commit()
        flash('Utilisateur mis à jour.', 'success')
        return redirect(url_for('users.list_users'))
    
    selected_modules = {p.module_code for p in user.module_permissions if p.allowed}
    selected_accounts = {p.account_id for p in user.account_permissions if p.allowed}
    
    return render_template('users/form.html', user=user, operators=operators, cost_centers=cost_centers,
                           accounts=accounts, modules=AVAILABLE_MODULES,
                           selected_modules=selected_modules, selected_accounts=selected_accounts)
