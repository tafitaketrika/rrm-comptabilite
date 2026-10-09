from datetime import datetime, date
from app import db


class Site(db.Model):
    """Site minier / chantier (1 projet = 1 site)."""
    __tablename__ = 'sites'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    location = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    projects = db.relationship('Project', backref='site', lazy='dynamic')

    def __repr__(self):
        return f'<Site {self.name}>'


class Project(db.Model):
    """Projet / chantier lié à un site unique."""
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=False)
    description = db.Column(db.Text, nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(30), default='planifie')  # planifie, en_cours, clos
    responsible_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    responsible = db.relationship('User', foreign_keys=[responsible_id])
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tasks = db.relationship('Task', backref='project', cascade='all, delete-orphan', lazy='dynamic')

    STATUS_LABELS = {
        'planifie': 'Planifié',
        'en_cours': 'En cours',
        'clos': 'Clos',
    }

    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    def task_progress(self):
        total = self.tasks.count()
        if total == 0:
            return 0
        done = self.tasks.filter_by(status='termine').count()
        return int(100 * done / total)

    def __repr__(self):
        return f'<Project {self.name}>'


class Task(db.Model):
    """Tâche planifiée, assignable à un ou plusieurs employés."""
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(30), default='a_faire')  # a_faire, en_cours, bloque, termine
    priority = db.Column(db.String(20), default='normale')  # basse, normale, haute
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assignments = db.relationship('TaskAssignment', backref='task', cascade='all, delete-orphan')
    dependencies = db.relationship(
        'TaskDependency',
        foreign_keys='TaskDependency.task_id',
        backref='task',
        cascade='all, delete-orphan',
    )

    STATUS_LABELS = {
        'a_faire': 'À faire',
        'en_cours': 'En cours',
        'bloque': 'Bloqué',
        'termine': 'Terminé',
    }
    PRIORITY_LABELS = {
        'basse': 'Basse',
        'normale': 'Normale',
        'haute': 'Haute',
    }

    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    def priority_label(self):
        return self.PRIORITY_LABELS.get(self.priority, self.priority)

    def assignee_names(self):
        return ', '.join(a.user.full_name for a in self.assignments if a.user)

    def duration_days(self):
        if self.start_date and self.end_date:
            return max(1, (self.end_date - self.start_date).days + 1)
        return None

    def __repr__(self):
        return f'<Task {self.title[:40]}>'


class TaskAssignment(db.Model):
    """Assignation d'un utilisateur à une tâche (multi-sites possible)."""
    __tablename__ = 'task_assignments'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User')

    __table_args__ = (db.UniqueConstraint('task_id', 'user_id', name='uq_task_user'),)


class TaskDependency(db.Model):
    """Tâche qui doit être terminée avant task_id (depends_on_id)."""
    __tablename__ = 'task_dependencies'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    depends_on_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    depends_on = db.relationship('Task', foreign_keys=[depends_on_id])

    __table_args__ = (db.UniqueConstraint('task_id', 'depends_on_id', name='uq_task_dep'),)


class TaskChangeLog(db.Model):
    """Historique d'allongement / décalage (P3–P4)."""
    __tablename__ = 'task_change_logs'

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(36), nullable=False, index=True)  # même lot = un allongement + décalages
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    task = db.relationship('Task', backref=db.backref('change_logs', lazy='dynamic'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    user = db.relationship('User')
    action = db.Column(db.String(30), default='extend')  # extend, shift, undo
    old_start = db.Column(db.Date, nullable=True)
    old_end = db.Column(db.Date, nullable=True)
    new_start = db.Column(db.Date, nullable=True)
    new_end = db.Column(db.Date, nullable=True)
    days = db.Column(db.Integer, default=0)
    reason = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    undone = db.Column(db.Boolean, default=False)
