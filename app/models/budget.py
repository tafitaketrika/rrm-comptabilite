from datetime import datetime
from app import db


class Budget(db.Model):
    """
    Budget de fonctionnement (ex. BudFoTsi09 01).
    """
    __tablename__ = 'budgets'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)  # ex: BudFoTsi09_01
    name = db.Column(db.String(200), nullable=False)
    cost_center_id = db.Column(db.Integer, db.ForeignKey('cost_centers.id'), nullable=True)
    cost_center = db.relationship('CostCenter', backref='budgets')
    
    period_id = db.Column(db.Integer, db.ForeignKey('periods.id'), nullable=True)
    period = db.relationship('Period', backref='budgets')
    
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    
    total_mga = db.Column(db.Numeric(18, 2), default=0)
    total_usd = db.Column(db.Numeric(18, 2), default=0)
    currency = db.Column(db.String(3), default='MGA')
    # JSON listes d'IDs opérateurs : destinataires / copies
    assigned_to_json = db.Column(db.Text, nullable=True)
    cc_to_json = db.Column(db.Text, nullable=True)
    
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    lines = db.relationship('BudgetLine', backref='budget', cascade='all, delete-orphan')

    def recipient_names(self):
        """Noms des destinataires (À)."""
        import json
        from app.models.operator import Operator
        try:
            ids = json.loads(self.assigned_to_json or '[]')
        except Exception:
            ids = []
        if not ids:
            return ''
        ops = Operator.query.filter(Operator.id.in_(ids)).all()
        return ', '.join(o.name for o in ops)

    def cc_names(self):
        import json
        from app.models.operator import Operator
        try:
            ids = json.loads(self.cc_to_json or '[]')
        except Exception:
            ids = []
        if not ids:
            return ''
        ops = Operator.query.filter(Operator.id.in_(ids)).all()
        return ', '.join(o.name for o in ops)

    def __repr__(self):
        return f'<Budget {self.code}>'


class BudgetLine(db.Model):
    """
    Ligne de budget (détail des dépenses prévues).
    """
    __tablename__ = 'budget_lines'

    id = db.Column(db.Integer, primary_key=True)
    budget_id = db.Column(db.Integer, db.ForeignKey('budgets.id'), nullable=False)
    
    category = db.Column(db.String(100), nullable=True)       # Logement, Salaire, etc.
    description = db.Column(db.String(300), nullable=False)
    
    quantity = db.Column(db.Numeric(12, 2), default=1)
    quantity_unit = db.Column(db.String(30), nullable=True)   # forfait, Personne, etc.
    occurrence = db.Column(db.Numeric(12, 2), default=1)
    occurrence_unit = db.Column(db.String(30), nullable=True) # mois, jour, fois...
    
    unit_cost_mga = db.Column(db.Numeric(18, 2), default=0)
    total_cost_mga = db.Column(db.Numeric(18, 2), default=0)
    unit_cost_usd = db.Column(db.Numeric(18, 2), default=0)
    total_cost_usd = db.Column(db.Numeric(18, 2), default=0)
    
    # Lien optionnel vers un compte du plan comptable
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    account = db.relationship('Account', backref='budget_lines')
    
    is_ordinary = db.Column(db.Boolean, default=True)  # True = ordinaire, False = extraordinaire
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<BudgetLine {self.description[:40]}>'
