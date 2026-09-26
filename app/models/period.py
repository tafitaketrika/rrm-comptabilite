from datetime import datetime
from app import db


class Period(db.Model):
    """
    Périodes comptables.
    """
    __tablename__ = 'periods'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_open = db.Column(db.Boolean, default=True)  # Seule une période ouverte permet la saisie
    is_current = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Period {self.name} ({self.start_date} → {self.end_date})>'
