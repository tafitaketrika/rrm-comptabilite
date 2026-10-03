from datetime import datetime
from app import db


class Account(db.Model):
    """
    Plan Comptable hiérarchique (niveaux 1 à 4).
    Code unique = clé primaire métier.
    """
    __tablename__ = 'accounts'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)  # ex: 10201001
    name = db.Column(db.String(200), nullable=False)                          # Intitulé
    level = db.Column(db.Integer, nullable=False)                             # 1, 2, 3 ou 4
    parent_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    
    # Type de compte pour faciliter les rapports
    account_class = db.Column(db.String(20))  # 'finances' ou 'fonctionnement'
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    parent = db.relationship('Account', remote_side=[id], backref='children')

    def __repr__(self):
        return f'<Account {self.code} - {self.name}>'

    @property
    def full_label(self):
        return f"{self.code} - {self.name}"
