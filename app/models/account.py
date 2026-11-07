from datetime import datetime, date
from app import db


class Account(db.Model):
    """
    Plan Comptable hiérarchique (niveaux 1 à 4).
    Code métier + année d'exercice (ex. 26 pour 2026) pour identifier le plan.
    """
    __tablename__ = 'accounts'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False, index=True)  # ex: 010201001
    name = db.Column(db.String(200), nullable=False)
    level = db.Column(db.Integer, nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)

    # Année d'exercice sur 2 chiffres (26 = 2026)
    exercise_year = db.Column(db.Integer, nullable=False, default=lambda: date.today().year % 100, index=True)

    account_class = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    parent = db.relationship('Account', remote_side=[id], backref='children')

    __table_args__ = (
        db.UniqueConstraint('exercise_year', 'code', name='uq_account_year_code'),
    )

    def __repr__(self):
        return f'<Account {self.exercise_year}-{self.code} - {self.name}>'

    @property
    def full_label(self):
        yy = self.exercise_year or (date.today().year % 100)
        return f"{yy}.{self.code} - {self.name}"
