"""Module Projets – modèle type Trello (Board / List / Card)."""
from datetime import datetime, date
from app import db


class Site(db.Model):
    """Site minier / chantier (1 tableau = 1 site)."""
    __tablename__ = 'sites'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)
    code = db.Column(db.String(30), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    boards = db.relationship('Board', backref='site', lazy='dynamic')

    def __repr__(self):
        return f'<Site {self.name}>'


class Board(db.Model):
    """Tableau Trello = un projet / un site."""
    __tablename__ = 'boards'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=True)
    background = db.Column(db.String(30), default='dark')
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_archived = db.Column(db.Boolean, default=False)

    lists = db.relationship(
        'BoardList',
        backref='board',
        cascade='all, delete-orphan',
        order_by='BoardList.position',
        lazy='dynamic',
    )

    def __repr__(self):
        return f'<Board {self.name}>'


class BoardList(db.Model):
    """Liste (colonne) d'un tableau."""
    __tablename__ = 'board_lists'

    id = db.Column(db.Integer, primary_key=True)
    board_id = db.Column(db.Integer, db.ForeignKey('boards.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    position = db.Column(db.Integer, default=0)
    is_archived = db.Column(db.Boolean, default=False)

    cards = db.relationship(
        'Card',
        backref='list',
        cascade='all, delete-orphan',
        order_by='Card.position',
        lazy='dynamic',
    )

    def active_cards(self):
        return self.cards.filter_by(is_archived=False).order_by(Card.position).all()

    def __repr__(self):
        return f'<BoardList {self.name}>'


class Card(db.Model):
    """Carte Trello = tâche."""
    __tablename__ = 'cards'

    id = db.Column(db.Integer, primary_key=True)
    list_id = db.Column(db.Integer, db.ForeignKey('board_lists.id'), nullable=True)  # None = boîte de réception
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=True)
    position = db.Column(db.Integer, default=0)
    start_date = db.Column(db.Date, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    cover_color = db.Column(db.String(20), nullable=True)
    is_archived = db.Column(db.Boolean, default=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    members = db.relationship('CardMember', backref='card', cascade='all, delete-orphan')
    labels = db.relationship('CardLabel', backref='card', cascade='all, delete-orphan')
    checklists = db.relationship(
        'CardChecklist',
        backref='card',
        cascade='all, delete-orphan',
        order_by='CardChecklist.position',
    )
    comments = db.relationship(
        'CardComment',
        backref='card',
        cascade='all, delete-orphan',
        order_by='CardComment.created_at.desc()',
    )
    attachments = db.relationship(
        'CardAttachment',
        backref='card',
        cascade='all, delete-orphan',
        order_by='CardAttachment.created_at.desc()',
    )

    def checklist_progress(self):
        total = done = 0
        for cl in self.checklists:
            for it in cl.items:
                total += 1
                if it.is_done:
                    done += 1
        if total == 0:
            return None
        return done, total

    def in_inbox(self):
        return self.list_id is None and not self.is_archived

    def is_overdue(self):
        if self.due_date and self.due_date < date.today():
            return True
        return False

    def member_names(self):
        return ', '.join(m.user.full_name for m in self.members if m.user)

    def __repr__(self):
        return f'<Card {self.title[:40]}>'


class CardMember(db.Model):
    __tablename__ = 'card_members'
    id = db.Column(db.Integer, primary_key=True)
    card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User')
    __table_args__ = (db.UniqueConstraint('card_id', 'user_id', name='uq_card_user'),)


class CardLabel(db.Model):
    __tablename__ = 'card_labels'
    id = db.Column(db.Integer, primary_key=True)
    card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False, default='')
    color = db.Column(db.String(20), default='blue')

    COLORS = {
        'green': '#61bd4f',
        'yellow': '#f2d600',
        'orange': '#ff9f1a',
        'red': '#eb5a46',
        'purple': '#c377e0',
        'blue': '#0079bf',
        'sky': '#00c2e0',
        'lime': '#51e898',
        'pink': '#ff78cb',
        'black': '#344563',
    }

    def color_hex(self):
        return self.COLORS.get(self.color, '#0079bf')


class CardChecklist(db.Model):
    __tablename__ = 'card_checklists'
    id = db.Column(db.Integer, primary_key=True)
    card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=False)
    title = db.Column(db.String(150), default='Checklist')
    position = db.Column(db.Integer, default=0)
    items = db.relationship(
        'CardChecklistItem',
        backref='checklist',
        cascade='all, delete-orphan',
        order_by='CardChecklistItem.position',
    )


class CardChecklistItem(db.Model):
    __tablename__ = 'card_checklist_items'
    id = db.Column(db.Integer, primary_key=True)
    checklist_id = db.Column(db.Integer, db.ForeignKey('card_checklists.id'), nullable=False)
    text = db.Column(db.String(300), nullable=False)
    is_done = db.Column(db.Boolean, default=False)
    position = db.Column(db.Integer, default=0)


class CardComment(db.Model):
    __tablename__ = 'card_comments'
    id = db.Column(db.Integer, primary_key=True)
    card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User')


class CardAttachment(db.Model):
    __tablename__ = 'card_attachments'
    id = db.Column(db.Integer, primary_key=True)
    card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


DEFAULT_LISTS = ['À faire', 'En cours', 'En attente', 'Terminé']
