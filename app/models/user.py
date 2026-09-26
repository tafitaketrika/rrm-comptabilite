from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db


# Modules disponibles pour les droits d'accès
AVAILABLE_MODULES = [
    ('dashboard', 'Tableau de bord'),
    ('journal', 'Brouillard'),
    ('accounts', 'Plan Comptable'),
    ('budgets', 'Budgets'),
    ('reports', 'Rapports'),
    ('users', 'Utilisateurs'),
]


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    
    # Rôles : admin, comptable, lecteur, responsable_site
    role = db.Column(db.String(30), nullable=False, default='lecteur')
    
    operator_id = db.Column(db.Integer, db.ForeignKey('operators.id'), nullable=True)
    operator = db.relationship('Operator', backref='users')

    cost_center_id = db.Column(db.Integer, db.ForeignKey('cost_centers.id'), nullable=True)
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)

    created_by = db.relationship('User', remote_side=[id], backref='created_users')
    
    module_permissions = db.relationship('UserModulePermission', backref='user', cascade='all, delete-orphan')
    account_permissions = db.relationship('UserAccountPermission', backref='user', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'

    def is_comptable(self):
        return self.role in ('admin', 'comptable')

    def can_edit_journal(self):
        if self.role == 'admin':
            return True
        return self.has_module('journal') and self.role in ('admin', 'comptable', 'responsable_site')

    def can_manage_users(self):
        return self.role == 'admin'

    def has_module(self, module_code):
        """Vérifie l'accès à un module. Admin a tout."""
        if self.role == 'admin':
            return True
        return any(p.module_code == module_code and p.allowed for p in self.module_permissions)

    def has_account(self, account_id):
        """Vérifie l'accès à un compte. Admin a tout. Si aucun droit compte défini, accès libre."""
        if self.role == 'admin':
            return True
        perms = [p for p in self.account_permissions if p.allowed]
        if not perms:
            return True  # pas de restriction = accès à tout
        return any(p.account_id == account_id for p in perms)

    def allowed_account_ids(self):
        if self.role == 'admin':
            return None  # None = tous
        ids = [p.account_id for p in self.account_permissions if p.allowed]
        return ids if ids else None

    def role_label(self):
        labels = {
            'admin': 'Administrateur',
            'comptable': 'Opérateur',
            'responsable_site': 'Responsable du site',
            'lecteur': 'Lecteur',
        }
        return labels.get(self.role, self.role)

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class UserModulePermission(db.Model):
    """Droit d'accès à un module de l'application."""
    __tablename__ = 'user_module_permissions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    module_code = db.Column(db.String(50), nullable=False)
    allowed = db.Column(db.Boolean, default=True)

    __table_args__ = (db.UniqueConstraint('user_id', 'module_code', name='uq_user_module'),)


class UserAccountPermission(db.Model):
    """Droit d'accès à un compte du plan comptable."""
    __tablename__ = 'user_account_permissions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    allowed = db.Column(db.Boolean, default=True)

    account = db.relationship('Account')

    __table_args__ = (db.UniqueConstraint('user_id', 'account_id', name='uq_user_account'),)
