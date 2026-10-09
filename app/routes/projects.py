from datetime import datetime, date
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.project import Site, Project, Task, TaskAssignment, TaskDependency, TaskChangeLog
from app.models.user import User

projects_bp = Blueprint('projects', __name__)

STATUSES = ['a_faire', 'en_cours', 'bloque', 'termine']
PRIORITIES = ['basse', 'normale', 'haute']
PROJECT_STATUSES = ['planifie', 'en_cours', 'clos']


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


def _can_manage():
    return current_user.is_admin() or current_user.role in ('comptable', 'responsable_site')


@projects_bp.route('/')
@login_required
def list_projects():
    q = Project.query
    status = request.args.get('status') or ''
    site_id = request.args.get('site_id') or ''
    responsible_id = request.args.get('responsible_id') or ''
    if status:
        q = q.filter_by(status=status)
    if site_id:
        try:
            q = q.filter_by(site_id=int(site_id))
        except ValueError:
            pass
    if responsible_id:
        try:
            q = q.filter_by(responsible_id=int(responsible_id))
        except ValueError:
            pass
    projects = q.order_by(Project.created_at.desc()).all()
    sites = Site.query.filter_by(is_active=True).order_by(Site.name).all()
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    return render_template(
        'projects/list.html',
        projects=projects,
        sites=sites,
        users=users,
        can_manage=_can_manage(),
        filter_status=status,
        filter_site_id=site_id,
        filter_responsible_id=responsible_id,
    )


@projects_bp.route('/sites', methods=['GET', 'POST'])
@login_required
def manage_sites():
    if not _can_manage():
        abort(403)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        location = request.form.get('location', '').strip() or None
        if name:
            db.session.add(Site(name=name, location=location))
            db.session.commit()
            flash(f'Site « {name} » créé.', 'success')
        return redirect(url_for('projects.manage_sites'))
    sites = Site.query.order_by(Site.name).all()
    return render_template('projects/sites.html', sites=sites)


@projects_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_project():
    if not _can_manage():
        abort(403)
    sites = Site.query.filter_by(is_active=True).order_by(Site.name).all()
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        site_id = request.form.get('site_id')
        if not name or not site_id:
            flash('Nom et site obligatoires.', 'danger')
            return render_template('projects/form.html', project=None, sites=sites, users=users)
        p = Project(
            name=name,
            site_id=int(site_id),
            description=request.form.get('description', '').strip() or None,
            start_date=_parse_date(request.form.get('start_date')),
            end_date=_parse_date(request.form.get('end_date')),
            status=request.form.get('status') or 'planifie',
            responsible_id=int(request.form['responsible_id']) if request.form.get('responsible_id') else None,
            created_by_id=current_user.id,
        )
        db.session.add(p)
        db.session.commit()
        flash('Projet créé.', 'success')
        return redirect(url_for('projects.view_project', project_id=p.id))
    return render_template('projects/form.html', project=None, sites=sites, users=users)


@projects_bp.route('/<int:project_id>')
@login_required
def view_project(project_id):
    project = Project.query.get_or_404(project_id)
    tasks = Task.query.filter_by(project_id=project.id).order_by(Task.start_date.asc(), Task.id).all()
    by_status = {s: [t for t in tasks if t.status == s] for s in STATUSES}
    # Plage Gantt
    from datetime import timedelta
    dated = [t for t in tasks if t.start_date and t.end_date]
    today = date.today()
    if dated:
        gantt_start = min(t.start_date for t in dated)
        gantt_end = max(t.end_date for t in dated)
        # marge 2 jours
        gantt_start = gantt_start - timedelta(days=2)
        gantt_end = gantt_end + timedelta(days=2)
        # plafonner à 90 jours d'affichage
        if (gantt_end - gantt_start).days > 90:
            gantt_end = gantt_start + timedelta(days=90)
    else:
        gantt_start = today - timedelta(days=7)
        gantt_end = today + timedelta(days=30)
    gantt_days = []
    d = gantt_start
    while d <= gantt_end:
        gantt_days.append(d)
        d += timedelta(days=1)
    return render_template(
        'projects/view.html',
        project=project,
        tasks=tasks,
        by_status=by_status,
        statuses=STATUSES,
        can_manage=_can_manage(),
        gantt_days=gantt_days,
        gantt_start=gantt_start,
        gantt_end=gantt_end,
        today_iso=today.isoformat(),
    )


@projects_bp.route('/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    if not _can_manage():
        abort(403)
    project = Project.query.get_or_404(project_id)
    sites = Site.query.filter_by(is_active=True).order_by(Site.name).all()
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    if request.method == 'POST':
        project.name = request.form.get('name', '').strip() or project.name
        if request.form.get('site_id'):
            project.site_id = int(request.form.get('site_id'))
        project.description = request.form.get('description', '').strip() or None
        project.start_date = _parse_date(request.form.get('start_date')) or project.start_date
        project.end_date = _parse_date(request.form.get('end_date')) or project.end_date
        project.status = request.form.get('status') or project.status
        rid = request.form.get('responsible_id')
        project.responsible_id = int(rid) if rid else None
        db.session.commit()
        flash('Projet mis à jour.', 'success')
        return redirect(url_for('projects.view_project', project_id=project.id))
    return render_template('projects/form.html', project=project, sites=sites, users=users)


@projects_bp.route('/<int:project_id>/tasks/new', methods=['GET', 'POST'])
@login_required
def new_task(project_id):
    project = Project.query.get_or_404(project_id)
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    other_tasks = Task.query.filter_by(project_id=project.id).order_by(Task.title).all()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Titre obligatoire.', 'danger')
            return render_template(
                'projects/task_form.html', project=project, task=None,
                users=users, other_tasks=other_tasks, statuses=STATUSES, priorities=PRIORITIES,
            )
        t = Task(
            project_id=project.id,
            title=title,
            description=request.form.get('description', '').strip() or None,
            start_date=_parse_date(request.form.get('start_date')),
            end_date=_parse_date(request.form.get('end_date')),
            status=request.form.get('status') or 'a_faire',
            priority=request.form.get('priority') or 'normale',
            created_by_id=current_user.id,
        )
        db.session.add(t)
        db.session.flush()
        for uid in request.form.getlist('assignees'):
            try:
                db.session.add(TaskAssignment(task_id=t.id, user_id=int(uid)))
            except ValueError:
                pass
        for dep in request.form.getlist('depends_on'):
            try:
                db.session.add(TaskDependency(task_id=t.id, depends_on_id=int(dep)))
            except ValueError:
                pass
        db.session.commit()
        flash('Tâche créée.', 'success')
        return redirect(url_for('projects.view_project', project_id=project.id))
    return render_template(
        'projects/task_form.html', project=project, task=None,
        users=users, other_tasks=other_tasks, statuses=STATUSES, priorities=PRIORITIES,
    )


@projects_bp.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    project = task.project
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    other_tasks = Task.query.filter(
        Task.project_id == project.id, Task.id != task.id
    ).order_by(Task.title).all()
    if request.method == 'POST':
        # Employé peut allonger ses propres tâches (P2-ready)
        is_assignee = any(a.user_id == current_user.id for a in task.assignments)
        can_full = _can_manage() or current_user.is_admin()
        if not can_full and not is_assignee:
            abort(403)

        if can_full:
            task.title = request.form.get('title', '').strip() or task.title
            task.description = request.form.get('description', '').strip() or None
            task.status = request.form.get('status') or task.status
            task.priority = request.form.get('priority') or task.priority
            TaskAssignment.query.filter_by(task_id=task.id).delete()
            for uid in request.form.getlist('assignees'):
                try:
                    db.session.add(TaskAssignment(task_id=task.id, user_id=int(uid)))
                except ValueError:
                    pass
            TaskDependency.query.filter_by(task_id=task.id).delete()
            for dep in request.form.getlist('depends_on'):
                try:
                    db.session.add(TaskDependency(task_id=task.id, depends_on_id=int(dep)))
                except ValueError:
                    pass

        task.start_date = _parse_date(request.form.get('start_date')) or task.start_date
        task.end_date = _parse_date(request.form.get('end_date')) or task.end_date
        if request.form.get('status') and is_assignee:
            task.status = request.form.get('status') or task.status
        db.session.commit()
        flash('Tâche mise à jour.', 'success')
        return redirect(url_for('projects.view_project', project_id=project.id))

    selected_assignees = {a.user_id for a in task.assignments}
    selected_deps = {d.depends_on_id for d in task.dependencies}
    return render_template(
        'projects/task_form.html', project=project, task=task,
        users=users, other_tasks=other_tasks, statuses=STATUSES, priorities=PRIORITIES,
        selected_assignees=selected_assignees, selected_deps=selected_deps,
        can_manage=_can_manage(),
    )


@projects_bp.route('/tasks/<int:task_id>/status', methods=['POST'])
@login_required
def update_task_status(task_id):
    task = Task.query.get_or_404(task_id)
    status = request.form.get('status') or (request.json or {}).get('status')
    if status in STATUSES:
        task.status = status
        db.session.commit()
    # JSON pour drag & drop AJAX
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json or request.accept_mimetypes.best == 'application/json':
        from flask import jsonify
        return jsonify({'ok': True, 'status': task.status, 'task_id': task.id})
    return redirect(url_for('projects.view_project', project_id=task.project_id))



def _impacted_tasks(source: Task, days: int):
    """P3 A+B+C : tâches à décaler si source est allongée de `days`."""
    from datetime import timedelta
    if not source.end_date or days < 1:
        return []
    old_end = source.end_date
    impacted = {}  # id -> (task, reason)

    # A – dépendances explicites (tâches qui dépendent de source)
    deps = TaskDependency.query.filter_by(depends_on_id=source.id).all()
    for d in deps:
        t = Task.query.get(d.task_id)
        if t and t.id != source.id:
            impacted[t.id] = (t, 'dépendance')

    # B – mêmes assignés, tâches qui commencent >= ancienne fin de source
    assignee_ids = [a.user_id for a in source.assignments]
    if assignee_ids:
        q = Task.query.join(TaskAssignment).filter(
            TaskAssignment.user_id.in_(assignee_ids),
            Task.id != source.id,
            Task.start_date.isnot(None),
            Task.start_date >= old_end,
        )
        for t in q.all():
            if t.id not in impacted:
                impacted[t.id] = (t, 'même employé')

    # C – même projet, début >= ancienne fin
    q = Task.query.filter(
        Task.project_id == source.project_id,
        Task.id != source.id,
        Task.start_date.isnot(None),
        Task.start_date >= old_end,
    )
    for t in q.all():
        if t.id not in impacted:
            impacted[t.id] = (t, 'même projet/site')

    return list(impacted.values())


@projects_bp.route('/tasks/<int:task_id>/extend', methods=['GET', 'POST'])
@login_required
def extend_task(task_id):
    """P2–P3 : allonger + aperçu / application du décalage A+B+C."""
    from datetime import timedelta
    import uuid
    task = Task.query.get_or_404(task_id)
    is_assignee = any(a.user_id == current_user.id for a in task.assignments)
    if not (_can_manage() or is_assignee or current_user.is_admin()):
        abort(403)

    if request.method == 'GET':
        try:
            days = int(request.args.get('days') or 1)
        except ValueError:
            days = 1
        days = max(1, min(days, 365))
        impacts = _impacted_tasks(task, days)
        from datetime import timedelta as _td
        return render_template(
            'projects/extend_confirm.html',
            task=task, days=days, impacts=impacts,
            new_end=(task.end_date or date.today()) + _td(days=days),
            timedelta=_td,
        )

    try:
        days = int(request.form.get('extra_days') or 0)
    except ValueError:
        days = 0
    if days < 1:
        flash('Indiquez un nombre de jours ≥ 1.', 'warning')
        return redirect(url_for('projects.edit_task', task_id=task.id))

    confirm = request.form.get('confirm') == '1'
    impacts = _impacted_tasks(task, days)

    if impacts and not confirm:
        from datetime import timedelta as _td
        return render_template(
            'projects/extend_confirm.html',
            task=task, days=days, impacts=impacts,
            new_end=(task.end_date or date.today()) + _td(days=days),
            timedelta=_td,
        )

    batch_id = str(uuid.uuid4())
    if not task.end_date:
        task.end_date = date.today()
    old_start, old_end = task.start_date, task.end_date
    task.end_date = task.end_date + timedelta(days=days)
    db.session.add(TaskChangeLog(
        batch_id=batch_id, task_id=task.id, user_id=current_user.id,
        action='extend', old_start=old_start, old_end=old_end,
        new_start=task.start_date, new_end=task.end_date, days=days,
        reason=f'Allongement +{days}j',
    ))

    apply_shift = request.form.get('apply_shift') == '1'
    if apply_shift and impacts:
        for t, reason in impacts:
            os, oe = t.start_date, t.end_date
            if t.start_date:
                t.start_date = t.start_date + timedelta(days=days)
            if t.end_date:
                t.end_date = t.end_date + timedelta(days=days)
            db.session.add(TaskChangeLog(
                batch_id=batch_id, task_id=t.id, user_id=current_user.id,
                action='shift', old_start=os, old_end=oe,
                new_start=t.start_date, new_end=t.end_date, days=days,
                reason=reason,
            ))

    db.session.commit()
    msg = f'Tâche allongée de {days} jour(s) → fin {task.end_date.strftime("%d/%m/%y")}.'
    if apply_shift and impacts:
        msg += f' {len(impacts)} autre(s) tâche(s) décalée(s).'
    flash(msg, 'success')
    return redirect(url_for('projects.view_project', project_id=task.project_id))


@projects_bp.route('/batches/<batch_id>/undo', methods=['POST'])
@login_required
def undo_batch(batch_id):
    """P4 : annuler le dernier lot d'allongement/décalage."""
    logs = TaskChangeLog.query.filter_by(batch_id=batch_id, undone=False).all()
    if not logs:
        flash('Aucune modification à annuler.', 'warning')
        return redirect(request.referrer or url_for('projects.list_projects'))
    # seul admin / manager / auteur
    if not (current_user.is_admin() or _can_manage() or any(l.user_id == current_user.id for l in logs)):
        abort(403)
    project_id = None
    for log in logs:
        t = Task.query.get(log.task_id)
        if not t:
            continue
        project_id = t.project_id
        t.start_date = log.old_start
        t.end_date = log.old_end
        log.undone = True
    db.session.commit()
    flash('Modifications annulées.', 'success')
    if project_id:
        return redirect(url_for('projects.view_project', project_id=project_id))
    return redirect(url_for('projects.list_projects'))


@projects_bp.route('/tasks/<int:task_id>/history')
@login_required
def task_history(task_id):
    task = Task.query.get_or_404(task_id)
    logs = TaskChangeLog.query.filter_by(task_id=task.id).order_by(TaskChangeLog.created_at.desc()).all()
    return render_template('projects/history.html', task=task, logs=logs)
