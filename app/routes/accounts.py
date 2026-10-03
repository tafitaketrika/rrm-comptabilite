from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, Response
from flask_login import login_required, current_user
from app.models.account import Account
from app import db
import csv
import io

accounts_bp = Blueprint('accounts', __name__)

def _accounts_json():
    """Liste des comptes avec ancêtres pour le formulaire."""
    accounts = Account.query.order_by(Account.code).all()
    # Précharger parents
    result = []
    for a in accounts:
        ancestors = []
        parent = a.parent
        while parent is not None:
            ancestors.append({
                'id': parent.id,
                'code': parent.code,
                'name': parent.name,
                'level': parent.level,
            })
            parent = parent.parent
        result.append({
            'id': a.id,
            'code': a.code,
            'name': a.name,
            'level': a.level,
            'parent_id': a.parent_id,
            'ancestors': ancestors,
        })
    return result


def _can_edit():
    return current_user.is_admin() or (
        current_user.has_module('accounts') and current_user.role in ('comptable', 'admin')
    )


def _allowed_ids():
    """None = tous les comptes ; sinon set d'IDs autorisés."""
    return current_user.allowed_account_ids()


def _filter_tree(accounts, allowed):
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
        class Node:
            pass
        n = Node()
        n.id = acc.id
        n.code = acc.code
        n.name = acc.name
        n.level = acc.level
        n.is_active = acc.is_active
        n.parent_id = acc.parent_id
        kids = []
        for c in sorted(acc.children or [], key=lambda x: x.code):
            child = filter_node(c)
            if child is not None:
                kids.append(child)
        n.children = kids
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


def _level_from_code(code):
    n = len(code)
    if n <= 2:
        return 1
    if n <= 4:
        return 2
    if n <= 6:
        return 3
    return 4


def _find_or_resolve_parent(code):
    """Trouve le parent le plus proche existant selon le préfixe du code."""
    # préfixes possibles : 6, 4, 2
    for length in (6, 4, 2):
        if len(code) > length:
            prefix = code[:length]
            parent = Account.query.filter_by(code=prefix).first()
            if parent:
                return parent
    return None


@accounts_bp.route('/')
@login_required
def list_accounts():
    if not current_user.is_admin() and not current_user.has_module('accounts'):
        abort(403)
    roots = _build_tree()
    allowed = _allowed_ids()
    roots = _filter_tree(roots, allowed)
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
    accounts_data = _accounts_json()

    if request.method == 'POST':
        code = request.form.get('code', '').strip().replace(' ', '').replace('-', '').replace('.', '')
        name = request.form.get('name', '').strip()
        parent_id_form = request.form.get('parent_id') or None
        account_class = request.form.get('account_class', 'finances')

        if not code or not name:
            flash('Code et intitulé sont obligatoires.', 'danger')
            return render_template('accounts/form.html', parent=parent, all_accounts=all_accounts, accounts_data=accounts_data, account=None)

        if Account.query.filter_by(code=code).first():
            flash('Ce code existe déjà.', 'danger')
            return render_template('accounts/form.html', parent=parent, all_accounts=all_accounts, accounts_data=accounts_data, account=None)

        parent_obj = None
        if parent_id_form:
            try:
                parent_obj = Account.query.get(int(parent_id_form))
            except (TypeError, ValueError):
                parent_obj = None
        if not parent_obj:
            parent_obj = _find_or_resolve_parent(code)

        level = _level_from_code(code)
        if parent_obj:
            level = max(level, parent_obj.level + 1)

        # Classe auto depuis section
        if code.startswith('01'):
            account_class = 'finances'
        elif code.startswith('02'):
            account_class = 'fonctionnement'

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

    return render_template('accounts/form.html', parent=parent, all_accounts=all_accounts, accounts_data=accounts_data, account=None)


@accounts_bp.route('/<int:account_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_account(account_id):
    if not current_user.is_admin():
        abort(403)

    account = Account.query.get_or_404(account_id)
    all_accounts = Account.query.filter(Account.id != account.id).order_by(Account.code).all()
    accounts_data = _accounts_json()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        account_class = request.form.get('account_class', account.account_class)
        is_active = request.form.get('is_active') == 'on'

        if not name:
            flash('Intitulé obligatoire.', 'danger')
            return render_template('accounts/form.html', account=account, all_accounts=all_accounts, accounts_data=accounts_data, parent=account.parent)

        account.name = name
        account.account_class = account_class
        account.is_active = is_active
        db.session.commit()
        flash('Compte mis à jour.', 'success')
        return redirect(url_for('accounts.list_accounts'))

    return render_template('accounts/form.html', account=account, all_accounts=all_accounts, accounts_data=accounts_data, parent=account.parent)


def _deactivate_recursive(account):
    account.is_active = False
    for child in list(account.children or []):
        _deactivate_recursive(child)


@accounts_bp.route('/<int:account_id>/deactivate', methods=['POST'])
@login_required
def deactivate_account(account_id):
    if not current_user.is_admin():
        abort(403)
    account = Account.query.get_or_404(account_id)
    _deactivate_recursive(account)
    db.session.commit()
    flash(f'Compte {account.code} (et sous-comptes) désactivé(s).', 'warning')
    return redirect(url_for('accounts.list_accounts'))


@accounts_bp.route('/<int:account_id>/delete', methods=['POST'])
@login_required
def delete_account(account_id):
    if not current_user.is_admin():
        abort(403)

    account = Account.query.get_or_404(account_id)
    code = account.code

    # Suppression récursive des enfants d'abord
    def delete_recursive(acc):
        for child in list(acc.children or []):
            delete_recursive(child)
        db.session.delete(acc)

    try:
        delete_recursive(account)
        db.session.commit()
        flash(f'Compte {code} supprimé définitivement.', 'success')
    except Exception as e:
        db.session.rollback()
        # Fallback: désactiver si contrainte FK (écritures liées)
        account = Account.query.get(account_id)
        if account:
            _deactivate_recursive(account)
            db.session.commit()
            flash(
                f'Impossible de supprimer {code} (écritures liées). '
                f'Le compte a été désactivé à la place.',
                'warning'
            )
        else:
            flash(f'Erreur lors de la suppression : {e}', 'danger')
    return redirect(url_for('accounts.list_accounts'))


@accounts_bp.route('/export')
@login_required
def export_accounts():
    if not current_user.is_admin() and not current_user.has_module('accounts'):
        abort(403)
    accounts = Account.query.order_by(Account.code).all()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Code', 'Intitulé', 'Niveau', 'Classe', 'Actif', 'Parent'])
    for a in accounts:
        writer.writerow([
            a.code,
            a.name,
            a.level,
            a.account_class or '',
            'Oui' if a.is_active else 'Non',
            a.parent.code if a.parent else ''
        ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=plan_comptable.csv'}
    )
