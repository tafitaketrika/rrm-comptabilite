from datetime import datetime
from app import db


class CostCenter(db.Model):
    """
    Centres de coût / Sites d'activités.
    """
    __tablename__ = 'cost_centers'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<CostCenter {self.code} - {self.name}>'
