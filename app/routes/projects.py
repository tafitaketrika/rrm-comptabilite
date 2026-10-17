"""Module Projets – API type Trello."""
import os
import uuid
from datetime import datetime, date, timedelta
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    abort, jsonify, current_app
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.project import (
    Site, Board, BoardList, Card, CardMember, CardLabel,
    CardChecklist, CardChecklistItem, CardComment, CardAttachment,
    DEFAULT_LISTS,
)
from app.models.user import User

projects_bp = Blueprint('projects', __name__)

@projects_bp.before_request
@login_required
def _projects_access():
    if not current_user.is_admin() and not current_user.has_module('projects'):
        flash("Vous n'avez pas accès au module Projets.", 'warning')
        return redirect(current_user.first_allowed_url())


LABEL_COLORS = list(CardLabel.COLORS.keys())


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


# ─── Sites ───────────────────────────────────────────────
@projects_bp.route('/sites', methods=['GET', 'POST'])
@login_required
def manage_sites():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        code = (request.form.get('code') or '').strip() or None
        if name:
            db.session.add(Site(name=name, code=code))
            db.session.commit()
            flash('Site créé.', 'success')
        return redirect(url_for('projects.manage_sites'))
    sites = Site.query.order_by(Site.name).all()
    return render_template('projects/sites.html', sites=sites)


# ─── Boards (liste des tableaux) ─────────────────────────
@projects_bp.route('/')
@login_required
def list_boards():
    boards = Board.query.filter_by(is_archived=False).order_by(Board.created_at.desc()).all()
    sites = Site.query.filter_by(is_active=True).order_by(Site.name).all()
    return render_template('projects/list.html', boards=boards, sites=sites)


@projects_bp.route('/new', methods=['POST'])
@login_required
def new_board():
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Le nom du tableau est obligatoire.', 'danger')
        return redirect(url_for('projects.list_boards'))
    site_id = request.form.get('site_id') or None
    board = Board(
        name=name,
        description=request.form.get('description') or None,
        site_id=int(site_id) if site_id else None,
        background=request.form.get('background') or 'dark',
        created_by_id=current_user.id,
    )
    db.session.add(board)
    db.session.flush()
    for i, ln in enumerate(DEFAULT_LISTS):
        db.session.add(BoardList(board_id=board.id, name=ln, position=i))
    db.session.commit()
    return redirect(url_for('projects.view_board', board_id=board.id))


# ─── Board Kanban ────────────────────────────────────────
@projects_bp.route('/<int:board_id>')
@login_required
def view_board(board_id):
    board = Board.query.get_or_404(board_id)
    lists = board.lists.filter_by(is_archived=False).order_by(BoardList.position).all()
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    return render_template(
        'projects/board.html',
        board=board,
        lists=lists,
        users=users,
        label_colors=LABEL_COLORS,
        label_hex=CardLabel.COLORS,
    )


# ─── Lists ───────────────────────────────────────────────
@projects_bp.route('/<int:board_id>/lists', methods=['POST'])
@login_required
def add_list(board_id):
    board = Board.query.get_or_404(board_id)
    name = (request.form.get('name') or '').strip() or 'Nouvelle liste'
    pos = board.lists.count()
    lst = BoardList(board_id=board.id, name=name, position=pos)
    db.session.add(lst)
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True, 'id': lst.id, 'name': lst.name})
    return redirect(url_for('projects.view_board', board_id=board.id))


@projects_bp.route('/lists/<int:list_id>/rename', methods=['POST'])
@login_required
def rename_list(list_id):
    lst = BoardList.query.get_or_404(list_id)
    name = (request.form.get('name') or '').strip()
    if name:
        lst.name = name
        db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True})
    return redirect(url_for('projects.view_board', board_id=lst.board_id))


@projects_bp.route('/lists/<int:list_id>/archive', methods=['POST'])
@login_required
def archive_list(list_id):
    lst = BoardList.query.get_or_404(list_id)
    bid = lst.board_id
    lst.is_archived = True
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True})
    return redirect(url_for('projects.view_board', board_id=bid))


# ─── Cards ───────────────────────────────────────────────
@projects_bp.route('/lists/<int:list_id>/cards', methods=['POST'])
@login_required
def add_card(list_id):
    lst = BoardList.query.get_or_404(list_id)
    title = (request.form.get('title') or '').strip()
    if not title:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': False, 'error': 'Titre requis'}), 400
        return redirect(url_for('projects.view_board', board_id=lst.board_id))
    pos = lst.cards.count()
    card = Card(
        list_id=lst.id,
        title=title,
        position=pos,
        created_by_id=current_user.id,
    )
    db.session.add(card)
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True, 'id': card.id, 'title': card.title})
    return redirect(url_for('projects.view_board', board_id=lst.board_id))


@projects_bp.route('/cards/<int:card_id>')
@login_required
def get_card(card_id):
    """JSON détail carte pour le modal."""
    card = Card.query.get_or_404(card_id)
    return jsonify({
        'ok': True,
        'id': card.id,
        'title': card.title,
        'description': card.description or '',
        'list_id': card.list_id,
        'list_name': card.list.name,
        'board_id': card.list.board_id,
        'start_date': card.start_date.strftime('%d/%m/%y') if card.start_date else '',
        'due_date': card.due_date.strftime('%d/%m/%y') if card.due_date else '',
        'cover_color': card.cover_color or '',
        'is_overdue': card.is_overdue(),
        'members': [{'id': m.user_id, 'name': m.user.full_name if m.user else ''} for m in card.members],
        'labels': [{'id': l.id, 'name': l.name, 'color': l.color, 'hex': l.color_hex()} for l in card.labels],
        'checklists': [{
            'id': cl.id,
            'title': cl.title,
            'items': [{'id': it.id, 'text': it.text, 'is_done': it.is_done} for it in cl.items],
        } for cl in card.checklists],
        'comments': [{
            'id': c.id,
            'body': c.body,
            'user': c.user.full_name if c.user else '—',
            'date': c.created_at.strftime('%d/%m/%y %H:%M') if c.created_at else '',
        } for c in card.comments],
        'attachments': [{
            'id': a.id,
            'name': a.original_name or a.filename,
            'url': url_for('static', filename='uploads/cards/' + a.filename),
        } for a in card.attachments],
    })


@projects_bp.route('/cards/<int:card_id>/update', methods=['POST'])
@login_required
def update_card(card_id):
    card = Card.query.get_or_404(card_id)
    data = request.get_json(silent=True) or request.form
    if 'title' in data:
        t = (data.get('title') or '').strip()
        if t:
            card.title = t
    if 'description' in data:
        card.description = data.get('description') or ''
    if 'start_date' in data:
        card.start_date = _parse_date(data.get('start_date'))
    if 'due_date' in data:
        card.due_date = _parse_date(data.get('due_date'))
    if 'cover_color' in data:
        card.cover_color = data.get('cover_color') or None
    db.session.commit()
    return jsonify({'ok': True})


@projects_bp.route('/cards/<int:card_id>/move', methods=['POST'])
@login_required
def move_card(card_id):
    """Déplacer une carte vers une autre liste (drag & drop)."""
    card = Card.query.get_or_404(card_id)
    data = request.get_json(silent=True) or request.form
    new_list_id = data.get('list_id')
    new_pos = data.get('position')
    if new_list_id:
        new_list_id = int(new_list_id)
        lst = BoardList.query.get_or_404(new_list_id)
        # same board check
        if lst.board_id != card.list.board_id:
            return jsonify({'ok': False, 'error': 'Board mismatch'}), 400
        card.list_id = new_list_id
    if new_pos is not None:
        card.position = int(new_pos)
    db.session.commit()
    return jsonify({'ok': True})


@projects_bp.route('/cards/<int:card_id>/archive', methods=['POST'])
@login_required
def archive_card(card_id):
    card = Card.query.get_or_404(card_id)
    card.is_archived = True
    db.session.commit()
    return jsonify({'ok': True})


# ─── Members ─────────────────────────────────────────────
@projects_bp.route('/cards/<int:card_id>/members', methods=['POST'])
@login_required
def toggle_member(card_id):
    card = Card.query.get_or_404(card_id)
    user_id = int(request.form.get('user_id') or (request.get_json(silent=True) or {}).get('user_id') or 0)
    if not user_id:
        return jsonify({'ok': False}), 400
    existing = CardMember.query.filter_by(card_id=card.id, user_id=user_id).first()
    if existing:
        db.session.delete(existing)
        added = False
    else:
        db.session.add(CardMember(card_id=card.id, user_id=user_id))
        added = True
    db.session.commit()
    return jsonify({'ok': True, 'added': added})


# ─── Labels ──────────────────────────────────────────────
@projects_bp.route('/cards/<int:card_id>/labels', methods=['POST'])
@login_required
def add_label(card_id):
    card = Card.query.get_or_404(card_id)
    data = request.get_json(silent=True) or request.form
    name = (data.get('name') or '').strip() or ''
    color = data.get('color') or 'blue'
    if color not in LABEL_COLORS:
        color = 'blue'
    lab = CardLabel(card_id=card.id, name=name, color=color)
    db.session.add(lab)
    db.session.commit()
    return jsonify({'ok': True, 'id': lab.id, 'name': lab.name, 'color': lab.color, 'hex': lab.color_hex()})


@projects_bp.route('/labels/<int:label_id>', methods=['DELETE', 'POST'])
@login_required
def delete_label(label_id):
    lab = CardLabel.query.get_or_404(label_id)
    db.session.delete(lab)
    db.session.commit()
    return jsonify({'ok': True})


# ─── Checklists ──────────────────────────────────────────
@projects_bp.route('/cards/<int:card_id>/checklists', methods=['POST'])
@login_required
def add_checklist(card_id):
    card = Card.query.get_or_404(card_id)
    title = (request.form.get('title') or (request.get_json(silent=True) or {}).get('title') or 'Checklist').strip()
    pos = len(card.checklists)
    cl = CardChecklist(card_id=card.id, title=title, position=pos)
    db.session.add(cl)
    db.session.commit()
    return jsonify({'ok': True, 'id': cl.id, 'title': cl.title})


@projects_bp.route('/checklists/<int:cl_id>/items', methods=['POST'])
@login_required
def add_checklist_item(cl_id):
    cl = CardChecklist.query.get_or_404(cl_id)
    text = (request.form.get('text') or (request.get_json(silent=True) or {}).get('text') or '').strip()
    if not text:
        return jsonify({'ok': False}), 400
    pos = len(cl.items)
    it = CardChecklistItem(checklist_id=cl.id, text=text, position=pos)
    db.session.add(it)
    db.session.commit()
    return jsonify({'ok': True, 'id': it.id, 'text': it.text})


@projects_bp.route('/checklist-items/<int:item_id>/toggle', methods=['POST'])
@login_required
def toggle_checklist_item(item_id):
    it = CardChecklistItem.query.get_or_404(item_id)
    it.is_done = not it.is_done
    db.session.commit()
    return jsonify({'ok': True, 'is_done': it.is_done})


@projects_bp.route('/checklist-items/<int:item_id>', methods=['DELETE', 'POST'])
@login_required
def delete_checklist_item(item_id):
    it = CardChecklistItem.query.get_or_404(item_id)
    if request.method == 'POST' and request.form.get('_action') != 'delete' and not request.headers.get('X-Requested-With'):
        # allow POST with toggle only via dedicated route
        pass
    db.session.delete(it)
    db.session.commit()
    return jsonify({'ok': True})


# ─── Comments ────────────────────────────────────────────
@projects_bp.route('/cards/<int:card_id>/comments', methods=['POST'])
@login_required
def add_comment(card_id):
    card = Card.query.get_or_404(card_id)
    body = (request.form.get('body') or (request.get_json(silent=True) or {}).get('body') or '').strip()
    if not body:
        return jsonify({'ok': False}), 400
    c = CardComment(card_id=card.id, user_id=current_user.id, body=body)
    db.session.add(c)
    db.session.commit()
    return jsonify({
        'ok': True,
        'id': c.id,
        'body': c.body,
        'user': current_user.full_name,
        'date': c.created_at.strftime('%d/%m/%y %H:%M'),
    })


# ─── Attachments ─────────────────────────────────────────
@projects_bp.route('/cards/<int:card_id>/attachments', methods=['POST'])
@login_required
def add_attachment(card_id):
    card = Card.query.get_or_404(card_id)
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'ok': False, 'error': 'Fichier manquant'}), 400
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'cards')
    os.makedirs(upload_dir, exist_ok=True)
    original = secure_filename(f.filename)
    ext = os.path.splitext(original)[1]
    stored = f'{uuid.uuid4().hex}{ext}'
    f.save(os.path.join(upload_dir, stored))
    att = CardAttachment(
        card_id=card.id,
        filename=stored,
        original_name=original,
        created_by_id=current_user.id,
    )
    db.session.add(att)
    db.session.commit()
    return jsonify({
        'ok': True,
        'id': att.id,
        'name': original,
        'url': url_for('static', filename='uploads/cards/' + stored),
    })


# ─── Boîte de réception ─────────────────────────────────
@projects_bp.route('/inbox')
@login_required
def inbox():
    """Cartes non classées (list_id is None)."""
    items = (
        Card.query
        .filter(Card.list_id.is_(None), Card.is_archived.is_(False))
        .order_by(Card.created_at.desc())
        .all()
    )
    boards = Board.query.filter_by(is_archived=False).order_by(Board.name).all()
    board_lists = {}
    for b in boards:
        board_lists[b.id] = [
            {'id': l.id, 'name': l.name}
            for l in b.lists.filter_by(is_archived=False).order_by(BoardList.position).all()
        ]
    return render_template(
        'projects/inbox.html',
        items=items,
        boards=boards,
        board_lists=board_lists,
    )


@projects_bp.route('/inbox', methods=['POST'])
@login_required
def inbox_add():
    title = (request.form.get('title') or '').strip()
    if not title:
        flash('Titre obligatoire.', 'danger')
        return redirect(url_for('projects.inbox'))
    card = Card(
        list_id=None,
        title=title,
        description=(request.form.get('description') or '').strip() or None,
        created_by_id=current_user.id,
        position=0,
    )
    db.session.add(card)
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True, 'id': card.id})
    return redirect(url_for('projects.inbox'))


@projects_bp.route('/inbox/<int:card_id>/move', methods=['POST'])
@login_required
def inbox_move(card_id):
    """Envoyer une carte de la réception vers une liste d'un tableau."""
    card = Card.query.get_or_404(card_id)
    if card.list_id is not None:
        return jsonify({'ok': False, 'error': 'Déjà classée'}), 400
    data = request.get_json(silent=True) or request.form
    list_id = data.get('list_id')
    if not list_id:
        return jsonify({'ok': False, 'error': 'Liste requise'}), 400
    lst = BoardList.query.get_or_404(int(list_id))
    card.list_id = lst.id
    card.position = lst.cards.count()
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({
            'ok': True,
            'board_id': lst.board_id,
            'redirect': url_for('projects.view_board', board_id=lst.board_id),
        })
    flash('Carte envoyée vers le tableau.', 'success')
    return redirect(url_for('projects.view_board', board_id=lst.board_id))


@projects_bp.route('/inbox/<int:card_id>/dismiss', methods=['POST'])
@login_required
def inbox_dismiss(card_id):
    card = Card.query.get_or_404(card_id)
    card.is_archived = True
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True})
    return redirect(url_for('projects.inbox'))




# ─── Tableau de bord (dashboard) ─────────────────────────
@projects_bp.route('/<int:board_id>/dashboard')
@login_required
def board_dashboard(board_id):
    """Vue tableau de bord type Trello : graphiques par liste, échéance, membre, étiquette."""
    from datetime import date, timedelta
    board = Board.query.get_or_404(board_id)
    lists = board.lists.filter_by(is_archived=False).order_by(BoardList.position).all()

    # Collect active cards
    all_cards = []
    for lst in lists:
        for c in lst.active_cards():
            all_cards.append(c)

    today = date.today()
    in_7 = today + timedelta(days=7)

    # 1) Par liste
    by_list_labels = [lst.name for lst in lists]
    by_list_counts = [len(lst.active_cards()) for lst in lists]

    # 2) Par date limite
    completed = 0  # cards in list named Terminé
    due_soon = 0
    due_now = 0
    overdue = 0
    no_date = 0
    termine_names = {'terminé', 'terminee', 'terminée', 'done', 'fini'}
    for c in all_cards:
        list_name = (c.list.name or '').strip().lower()
        if list_name in termine_names:
            completed += 1
            continue
        if not c.due_date:
            no_date += 1
        elif c.due_date < today:
            overdue += 1
        elif c.due_date <= in_7:
            due_soon += 1
        else:
            due_now += 1  # échéance plus loin
    by_due_labels = ['Complétées', 'Dû prochainement', 'Échéance à venir', 'En retard', 'Aucune date']
    by_due_counts = [completed, due_soon, due_now, overdue, no_date]
    by_due_colors = ['#61bd4f', '#f2d600', '#ff9f1a', '#eb5a46', '#c1c7d0']

    # 3) Par membre
    member_map = {}  # name -> count
    unassigned = 0
    for c in all_cards:
        if not c.members:
            unassigned += 1
        else:
            for m in c.members:
                name = m.user.full_name if m.user else '?'
                member_map[name] = member_map.get(name, 0) + 1
    if unassigned:
        member_map['Non attribué'] = unassigned
    by_member_labels = list(member_map.keys()) or ['—']
    by_member_counts = list(member_map.values()) or [0]

    # 4) Par étiquette
    label_map = {}  # (name or color) -> count
    for c in all_cards:
        if not c.labels:
            continue
        for lab in c.labels:
            key = lab.name.strip() if lab.name and lab.name.strip() else lab.color
            label_map[key] = label_map.get(key, 0) + 1
    by_label_labels = list(label_map.keys()) or ['Aucune']
    by_label_counts = list(label_map.values()) or [0]
    # colors for labels chart
    color_lookup = CardLabel.COLORS
    by_label_colors = []
    for key in by_label_labels:
        by_label_colors.append(color_lookup.get(key, '#5e6c84'))

    return render_template(
        'projects/dashboard.html',
        board=board,
        total_cards=len(all_cards),
        by_list_labels=by_list_labels,
        by_list_counts=by_list_counts,
        by_due_labels=by_due_labels,
        by_due_counts=by_due_counts,
        by_due_colors=by_due_colors,
        by_member_labels=by_member_labels,
        by_member_counts=by_member_counts,
        by_label_labels=by_label_labels,
        by_label_counts=by_label_counts,
        by_label_colors=by_label_colors,
    )



# ─── Chronogramme (timeline) ─────────────────────────────
@projects_bp.route('/<int:board_id>/timeline')
@login_required
def board_timeline(board_id):
    """Vue chronogramme : cartes avec dates sur une frise."""
    from datetime import date, timedelta
    board = Board.query.get_or_404(board_id)
    lists = board.lists.filter_by(is_archived=False).order_by(BoardList.position).all()

    cards = []
    for lst in lists:
        for c in lst.active_cards():
            start = c.start_date or c.due_date
            end = c.due_date or c.start_date
            if not start and not end:
                continue
            if start and end and end < start:
                start, end = end, start
            if not start:
                start = end
            if not end:
                end = start
            cards.append({
                'id': c.id,
                'title': c.title,
                'list_name': lst.name,
                'start': start.isoformat(),
                'end': end.isoformat(),
                'start_fmt': start.strftime('%d/%m/%y'),
                'end_fmt': end.strftime('%d/%m/%y'),
                'overdue': bool(c.due_date and c.due_date < date.today()),
                'cover': c.cover_color or '',
            })

    # range of timeline
    today = date.today()
    if cards:
        all_dates = []
        for c in cards:
            all_dates.append(date.fromisoformat(c['start']))
            all_dates.append(date.fromisoformat(c['end']))
        range_start = min(all_dates) - timedelta(days=3)
        range_end = max(all_dates) + timedelta(days=7)
    else:
        range_start = today - timedelta(days=7)
        range_end = today + timedelta(days=21)

    # cap to ~60 days for display
    if (range_end - range_start).days > 60:
        range_end = range_start + timedelta(days=60)

    days = []
    d = range_start
    while d <= range_end:
        days.append({
            'iso': d.isoformat(),
            'label': d.strftime('%d/%m'),
            'dow': ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'][d.weekday()],
            'is_today': d == today,
            'weekend': d.weekday() >= 5,
        })
        d += timedelta(days=1)

    total_days = max(len(days), 1)

    # position each card as % of timeline
    for c in cards:
        s = date.fromisoformat(c['start'])
        e = date.fromisoformat(c['end'])
        left = max(0, (s - range_start).days) / total_days * 100
        width = max(1, (e - s).days + 1) / total_days * 100
        c['left'] = round(left, 2)
        c['width'] = round(min(width, 100 - left), 2)

    return render_template(
        'projects/timeline.html',
        board=board,
        cards=cards,
        days=days,
        today=today,
    )

# ─── Mes cartes ──────────────────────────────────────────
@projects_bp.route('/my-cards')
@login_required
def my_cards():
    """Cartes où l'utilisateur courant est membre."""
    memberships = CardMember.query.filter_by(user_id=current_user.id).all()
    card_ids = [m.card_id for m in memberships]
    cards = []
    if card_ids:
        cards = (
            Card.query
            .filter(Card.id.in_(card_ids), Card.is_archived.is_(False), Card.list_id.isnot(None))
            .order_by(Card.due_date.asc(), Card.updated_at.desc())
            .all()
        )
    return render_template('projects/my_cards.html', cards=cards)


# ─── Calendrier des échéances ────────────────────────────
@projects_bp.route('/calendar')
@login_required
def calendar():
    """Vue calendrier simple : cartes avec due_date sur le mois courant (ou ?month=YYYY-MM)."""
    from calendar import monthcalendar
    q = request.args.get('month')  # YYYY-MM
    today = date.today()
    if q:
        try:
            y, m = map(int, q.split('-'))
            ref = date(y, m, 1)
        except Exception:
            ref = date(today.year, today.month, 1)
    else:
        ref = date(today.year, today.month, 1)

    # previous / next month
    if ref.month == 1:
        prev_m = date(ref.year - 1, 12, 1)
    else:
        prev_m = date(ref.year, ref.month - 1, 1)
    if ref.month == 12:
        next_m = date(ref.year + 1, 1, 1)
    else:
        next_m = date(ref.year, ref.month + 1, 1)

    # last day of month
    if ref.month == 12:
        end = date(ref.year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(ref.year, ref.month + 1, 1) - timedelta(days=1)

    cards = (
        Card.query
        .filter(
            Card.is_archived.is_(False),
            Card.list_id.isnot(None),
            Card.due_date.isnot(None),
            Card.due_date >= ref,
            Card.due_date <= end,
        )
        .order_by(Card.due_date)
        .all()
    )
    by_day = {}
    for c in cards:
        d = c.due_date.day
        by_day.setdefault(d, []).append(c)

    weeks = monthcalendar(ref.year, ref.month)
    month_label = f"{ref.month:02d}/{ref.year}"

    return render_template(
        'projects/calendar.html',
        weeks=weeks,
        by_day=by_day,
        ref=ref,
        today=today,
        prev_m=prev_m,
        next_m=next_m,
        month_label=month_label,
    )


# ─── Dupliquer une carte ─────────────────────────────────
@projects_bp.route('/cards/<int:card_id>/duplicate', methods=['POST'])
@login_required
def duplicate_card(card_id):
    """Copie titre, description, labels, checklist (items non cochés), membres — dans la même liste."""
    src = Card.query.get_or_404(card_id)
    if src.list_id is None:
        return jsonify({'ok': False, 'error': 'Carte inbox'}), 400
    pos = src.list.cards.count()
    new_card = Card(
        list_id=src.list_id,
        title=src.title + ' (copie)',
        description=src.description,
        position=pos,
        start_date=src.start_date,
        due_date=src.due_date,
        cover_color=src.cover_color,
        created_by_id=current_user.id,
    )
    db.session.add(new_card)
    db.session.flush()
    for lab in src.labels:
        db.session.add(CardLabel(card_id=new_card.id, name=lab.name, color=lab.color))
    for m in src.members:
        db.session.add(CardMember(card_id=new_card.id, user_id=m.user_id))
    for cl in src.checklists:
        ncl = CardChecklist(card_id=new_card.id, title=cl.title, position=cl.position)
        db.session.add(ncl)
        db.session.flush()
        for it in cl.items:
            db.session.add(CardChecklistItem(
                checklist_id=ncl.id, text=it.text, is_done=False, position=it.position
            ))
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({'ok': True, 'id': new_card.id, 'title': new_card.title})
    return redirect(url_for('projects.view_board', board_id=src.list.board_id))
