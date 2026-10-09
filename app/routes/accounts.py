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
    """Peut modifier le plan (boutons + / edit / pause / delete)."""
    if current_user.is_admin():
        return True
    if not current_user.has_module('accounts'):
        return False
    return current_user.can_write_account()


def _allowed_ids():
    """None = tous ; sinon set d'IDs autorisés + ancêtres (pour afficher le chemin)."""
    base = current_user.allowed_account_ids()
    if base is None:
        return None
    allowed = set(base)
    # Ajouter les ancêtres pour le chemin hiérarchique
    from app.models.account import Account as Acc
    for aid in list(allowed):
        acc = Acc.query.get(aid)
        while acc and acc.parent_id:
            allowed.add(acc.parent_id)
            acc = acc.parent
    return allowed


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
        n.exercise_year = getattr(acc, 'exercise_year', None)
        kids = []
        for c in sorted(acc.children or [], key=lambda x: _sort_code_key(x.code)):
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
    roots = Account.query.filter_by(parent_id=None).all()
    return sorted(roots, key=lambda x: _sort_code_key(x.code))



def next_child_code(parent):
    """Prochain code fils (ou frère si feuille). Codes toujours avec 0 initial."""
    if not parent:
        return ''
    # + sur une feuille → frère sous le même parent
    if (getattr(parent, 'level', 0) or 0) >= 4 and parent.parent_id:
        parent = parent.parent or parent

    def norm(c):
        d = str(c or '').replace(' ', '').replace('.', '').replace('-', '')
        if len(d) == 8 and not d.startswith('0'):
            d = '0' + d
        if len(d) in (5, 7) and not d.startswith('0'):
            d = '0' + d
        return d

    prefix = norm(parent.code)
    children = Account.query.filter_by(parent_id=parent.id).all()
    max_n = 0
    for c in children:
        raw = norm(c.code)
        if raw.startswith(prefix) and len(raw) > len(prefix):
            try:
                max_n = max(max_n, int(raw[len(prefix):]))
            except ValueError:
                continue
        else:
            # suffixe numérique de fin
            try:
                max_n = max(max_n, int(raw[-3:]))
            except ValueError:
                continue
    nxt = max_n + 1
    pl = getattr(parent, 'level', None) or (len(prefix) // 2 if prefix else 1)
    if pl >= 3 or len(prefix) >= 6:
        p6 = prefix[:6].ljust(6, '0')
        return f'{p6}{nxt:03d}'
    if pl == 2 or len(prefix) == 4:
        return f'{prefix[:4]}{nxt:02d}'
    return f'{prefix[:2]}{nxt:02d}'


def _sort_code_key(code):
    d = str(code or '').replace(' ', '').replace('.', '').replace('-', '')
    if not d:
        return '0' * 12
    # Toujours normaliser en 9 chiffres pour les feuilles / 6 / 4 / 2
    if len(d) == 8 and not d.startswith('0'):
        d = '0' + d
    if len(d) == 7 and not d.startswith('0'):
        d = '0' + d
    return d.ljust(12, '0')


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


def _sort_tree(nodes):
    """Trie récursivement l'arbre par code normalisé (0 initial)."""
    def key(n):
        return _sort_code_key(getattr(n, 'code', ''))
    nodes = sorted(list(nodes or []), key=key)
    result = []
    for n in nodes:
        # Node léger pour éviter d'écrire sur la relation SQLAlchemy
        class Node:
            pass
        nn = Node()
        for attr in ('id', 'code', 'name', 'level', 'is_active', 'parent_id', 'exercise_year'):
            setattr(nn, attr, getattr(n, attr, None))
        kids = getattr(n, 'children', None) or []
        nn.children = _sort_tree(list(kids))
        result.append(nn)
    return result


def _repair_leaf_parents():
    """Corrige les feuilles rattachées à d'autres feuilles → parent = paragraphe."""
    leaves = Account.query.filter(Account.level >= 4).all()
    changed = False
    for acc in leaves:
        p = acc.parent
        if p and (p.level or 0) >= 4:
            # remonter
            while p and (p.level or 0) >= 4:
                p = p.parent
            if p:
                acc.parent_id = p.id
                changed = True
            else:
                # essayer préfixe code
                code = str(acc.code).replace('.', '').replace(' ', '')
                if len(code) == 8:
                    code = '0' + code
                if len(code) >= 6:
                    pref = Account.query.filter_by(code=code[:6]).first()
                    if pref:
                        acc.parent_id = pref.id
                        changed = True
    if changed:
        db.session.commit()

@accounts_bp.route('/')
@login_required
def list_accounts():
    if not current_user.is_admin() and not current_user.has_module('accounts'):
        abort(403)
    try:
        _repair_leaf_parents()
    except Exception:
        pass
    roots = _build_tree()
    allowed = _allowed_ids()
    roots = _filter_tree(roots, allowed)
    roots = _sort_tree(list(roots))
    can_edit = _can_edit()
    writable_ids = set()
    if current_user.is_admin():
        writable_ids = None  # tous
    else:
        for p in current_user.account_permissions:
            if p.allowed and getattr(p, 'can_write', False):
                writable_ids.add(p.account_id)
                # écriture sur un parent = sous-comptes aussi modifiables
                from app.models.account import Account as Acc
                stack = [p.account_id]
                while stack:
                    pid = stack.pop()
                    for ch in Acc.query.filter_by(parent_id=pid).all():
                        writable_ids.add(ch.id)
                        stack.append(ch.id)
    from datetime import date as _date
    return render_template(
        'accounts/list.html', roots=roots, can_edit=can_edit,
        writable_ids=writable_ids, plan_year=_date.today().year
    )


@accounts_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_account():
    if not _can_edit():
        abort(403)

    parent_id = request.args.get('parent_id', type=int)
    parent = Account.query.get(parent_id) if parent_id else None
    # + sur une feuille → créer un frère sous le paragraphe
    if parent and (parent.level or 0) >= 4 and parent.parent:
        parent = parent.parent
    all_accounts = Account.query.order_by(Account.code).all()
    accounts_data = _accounts_json()
    suggested_code = next_child_code(parent) if parent else ''

    if request.method == 'POST':
        code = request.form.get('code', '').strip().replace(' ', '').replace('-', '').replace('.', '')
        if len(code) == 8 and not code.startswith('0'):
            code = '0' + code
        name = request.form.get('name', '').strip()
        parent_id_form = request.form.get('parent_id') or None
        account_class = request.form.get('account_class', 'finances')

        if not code or not name:
            flash('Code et intitulé sont obligatoires.', 'danger')
            return render_template('accounts/form.html', parent=parent, all_accounts=all_accounts, accounts_data=accounts_data, account=None, suggested_code='')

        parent_obj = None
        if parent_id_form:
            try:
                parent_obj = Account.query.get(int(parent_id_form))
            except (TypeError, ValueError):
                parent_obj = None
        if not parent_obj:
            parent_obj = _find_or_resolve_parent(code)

        from datetime import date as _date2
        _yy = _date2.today().year % 100
        if parent_obj and getattr(parent_obj, 'exercise_year', None):
            _yy = parent_obj.exercise_year
        try:
            exists = Account.query.filter_by(code=code, exercise_year=_yy).first()
        except Exception:
            exists = Account.query.filter_by(code=code).first()
        if exists:
            flash('Ce code existe déjà.', 'danger')
            return render_template('accounts/form.html', parent=parent, all_accounts=all_accounts, accounts_data=accounts_data, account=None, suggested_code='')

        # Un compte feuille (niv.4) ne peut pas être parent d'un autre compte
        # → remonter au paragraphe (niv.3) pour créer un frère
        while parent_obj and (parent_obj.level or 0) >= 4:
            parent_obj = parent_obj.parent

        # Si le code a 9 chiffres, parent = préfixe 6 chiffres
        if len(code) >= 9:
            p6 = code[:6]
            if len(p6) == 5:
                p6 = '0' + p6 if not p6.startswith('0') else p6
            pref = Account.query.filter_by(code=p6).first()
            if not pref and len(code) == 9 and code.startswith('0'):
                pref = Account.query.filter_by(code=code[1:7]).first()
            if pref and (pref.level or 0) < 4:
                parent_obj = pref

        level = _level_from_code(code)
        if parent_obj and (parent_obj.level or 0) < 4:
            level = max(level, parent_obj.level + 1)
        else:
            level = _level_from_code(code)

        # Classe auto depuis section
        if code.startswith('01'):
            account_class = 'finances'
        elif code.startswith('02'):
            account_class = 'fonctionnement'

        from datetime import date as _date
        yy = _date.today().year % 100
        # Hériter l'année du parent si présent
        if parent_obj and getattr(parent_obj, 'exercise_year', None):
            yy = parent_obj.exercise_year
        acc = Account(
            code=code,
            name=name,
            level=level,
            parent_id=parent_obj.id if parent_obj else None,
            account_class=account_class,
            is_active=True,
            exercise_year=yy
        )
        db.session.add(acc)
        db.session.commit()
        flash(f'Compte {code} créé.', 'success')
        return redirect(url_for('accounts.list_accounts'))

    return render_template('accounts/form.html', parent=parent, all_accounts=all_accounts, accounts_data=accounts_data, account=None, suggested_code=suggested_code)


@accounts_bp.route('/<int:account_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_account(account_id):
    if not _can_edit():
        abort(403)
    if not current_user.is_admin() and not current_user.can_write_account(account_id):
        # écriture sur parent ou ce compte
        acc = Account.query.get_or_404(account_id)
        ok = current_user.can_write_account(account_id)
        if not ok and acc.parent_id:
            ok = current_user.can_write_account(acc.parent_id)
        if not ok:
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
            return render_template('accounts/form.html', account=account, all_accounts=all_accounts, accounts_data=accounts_data, parent=account.parent, suggested_code='')

        account.name = name
        account.account_class = account_class
        account.is_active = is_active
        db.session.commit()
        flash('Compte mis à jour.', 'success')
        return redirect(url_for('accounts.list_accounts'))

    return render_template('accounts/form.html', account=account, all_accounts=all_accounts, accounts_data=accounts_data, parent=account.parent, suggested_code='')


def _deactivate_recursive(account):
    account.is_active = False
    for child in list(account.children or []):
        _deactivate_recursive(child)


@accounts_bp.route('/<int:account_id>/deactivate', methods=['POST'])
@login_required
def deactivate_account(account_id):
    if not _can_edit():
        abort(403)
    account = Account.query.get_or_404(account_id)
    _deactivate_recursive(account)
    db.session.commit()
    flash(f'Compte {account.code} (et sous-comptes) désactivé(s).', 'warning')
    return redirect(url_for('accounts.list_accounts'))


@accounts_bp.route('/<int:account_id>/delete', methods=['POST'])
@login_required
def delete_account(account_id):
    if not _can_edit():
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
