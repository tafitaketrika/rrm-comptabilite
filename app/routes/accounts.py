from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.models.account import Account
from app import db

accounts_bp = Blueprint('accounts', __name__)


def _can_edit():
    return current_user.is_admin() or (
        current_user.has_module('accounts') and current_user.role in ('comptable', 'admin')
    )


def _allowed_ids():
    """None = tous les comptes ; sinon set d'IDs autorisés."""
    return current_user.allowed_account_ids()


def _filter_tree(accounts, allowed):
    """
    Filtre l'arbre : ne garde que les nœuds autorisés
    ou les parents nécessaires pour afficher un descendant autorisé.
    """
    if allowed is None:
        return accounts

    allowed_set = set(allowed)

    def node_visible(acc):
        if acc.id in allowed_set:
            return True
        return any(node_visible(c) for c in (acc.children or []))

    def filter_node(acc):
        if not node_visible(acc):
            return None
        # Copie légère pour ne pas muter la session SQLAlchemy
        class Node:
            pass
        n = Node()
        n.id = acc.id
        n.code = acc.code
        n.name = acc.name
        n.level = acc.level
        n.is_active = acc.is_active
        n.parent_id = acc.parent_id
        # Enfants filtrés
        kids = []
        for c in sorted(acc.children or [], key=lambda x: x.code):
            if not c.is_active and acc.id not in allowed_set:
                # masquer inactifs sauf si explicitement autorisé
                continue
            child = filter_node(c)
            if child is not None:
                kids.append(child)
        n.children = kids
        # Visible si autorisé directement OU a des enfants visibles
        if acc.id in allowed_set or kids:
            return n
        return None

    result = []
    for root in accounts:
        filtered = filter_node(root)
        if filtered is not None:
            result.append(filtered)
    return result


def _build_tree():
    return Account.query.filter_by(parent_id=None).order_by(Account.code).all()


@accounts_bp.route('/')
@login_required
def list_accounts():
    if not current_user.is_admin() and not current_user.has_module('accounts'):
        abort(403)
    roots = _build_tree()
    allowed = _allowed_ids()
    roots = _filter_tree(roots, allowed)
    # Édition réservée admin ou si accès module + rôle
    can_edit = current_user.is_admin()
    return render_template('accounts/list.html', roots=roots, can_edit=can_edit)


@accounts_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_account():
    if not current_user.is_admin():
        abort(403)

    parent_id = request.args.get('parent_id', type=int)
    parent = Account.query.get(parent_id) if parent_id else None
    all_accounts = Account.query.order_by(Account.code).all()

    if request.method == 'POST':
        code = request.form.get('code', '').strip().replace(' ', '').replace('-', '')
        name = request.form.get('name', '').strip()
        parent_id_form = request.form.get('parent_id') or None
        account_class = request.form.get('account_class', 'finances')

        if not code or not name:
            flash('Code et intitulé sont obligatoires.', 'danger')
            return render_template('accounts/form.html', parent=parent, all_accounts=all_accounts, account=None)

        if Account.query.filter_by(code=code).first():
            flash('Ce code existe déjà.', 'danger')
            return render_template('accounts/form.html', parent=parent, all_accounts=all_accounts, account=None)

        parent_obj = Account.query.get(int(parent_id_form)) if parent_id_form else None
        level = (parent_obj.level + 1) if parent_obj else 1

        acc = Account(
            code=code,
            name=name,
            level=level,
            parent_id=parent_obj.id if parent_obj else None,
            account_class=account_class,
            is_active=True
        )
        db.session.add(acc)
        db.session.commit()
        flash(f'Compte {code} créé.', 'success')
        return redirect(url_for('accounts.list_accounts'))

    return render_template('accounts/form.html', parent=parent, all_accounts=all_accounts, account=None)


@accounts_bp.route('/<int:account_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_account(account_id):
    if not current_user.is_admin():
        abort(403)

    account = Account.query.get_or_404(account_id)
    all_accounts = Account.query.filter(Account.id != account.id).order_by(Account.code).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        account_class = request.form.get('account_class', account.account_class)
        is_active = request.form.get('is_active') == 'on'

        if not name:
            flash('Intitulé obligatoire.', 'danger')
            return render_template('accounts/form.html', account=account, all_accounts=all_accounts, parent=account.parent)

        account.name = name
        account.account_class = account_class
        account.is_active = is_active
        db.session.commit()
        flash('Compte mis à jour.', 'success')
        return redirect(url_for('accounts.list_accounts'))

    return render_template('accounts/form.html', account=account, all_accounts=all_accounts, parent=account.parent)


@accounts_bp.route('/<int:account_id>/delete', methods=['POST'])
@login_required
def delete_account(account_id):
    if not current_user.is_admin():
        abort(403)

    account = Account.query.get_or_404(account_id)

    if account.children:
        flash('Impossible de supprimer : ce compte a des sous-comptes.', 'danger')
        return redirect(url_for('accounts.list_accounts'))

    account.is_active = False
    db.session.commit()
    flash(f'Compte {account.code} désactivé.', 'success')
    return redirect(url_for('accounts.list_accounts'))
