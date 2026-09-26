from datetime import datetime
from app import db


class JournalEntry(db.Model):
    """
    En-tête d'une écriture comptable.
    Clé primaire : id (auto-incrément)
    Code métier unique : entry_code (ECR-AAAA-MM-JJ-XXXX)
    """
    __tablename__ = 'journal_entries'

    id = db.Column(db.Integer, primary_key=True)
    
    # Code métier unique et stable
    entry_code = db.Column(db.String(30), unique=True, nullable=False, index=True)
    
    entry_date = db.Column(db.Date, nullable=False, index=True)
    description = db.Column(db.String(500), nullable=False)
    
    # Opérateur qui a saisi l'écriture
    operator_id = db.Column(db.Integer, db.ForeignKey('operators.id'), nullable=False)
    operator = db.relationship('Operator', backref='entries')
    
    # Utilisateur connecté qui a saisi
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_by = db.relationship('User', backref='journal_entries')
    
    period_id = db.Column(db.Integer, db.ForeignKey('periods.id'), nullable=True)
    period = db.relationship('Period', backref='entries')
    
    # Centre de coût optionnel
    cost_center_id = db.Column(db.Integer, db.ForeignKey('cost_centers.id'), nullable=True)
    cost_center = db.relationship('CostCenter', backref='entries')
    
    # Totaux calculés (pour validation d'équilibre)
    total_mga_debit = db.Column(db.Numeric(18, 2), default=0)
    total_mga_credit = db.Column(db.Numeric(18, 2), default=0)
    total_usd_debit = db.Column(db.Numeric(18, 2), default=0)
    total_usd_credit = db.Column(db.Numeric(18, 2), default=0)
    total_eur_debit = db.Column(db.Numeric(18, 2), default=0)
    total_eur_credit = db.Column(db.Numeric(18, 2), default=0)
    
    is_balanced = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='draft')  # draft, posted, cancelled
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lines = db.relationship('JournalLine', backref='entry', cascade='all, delete-orphan', lazy='joined')
    attachments = db.relationship('Attachment', backref='entry', cascade='all, delete-orphan', lazy='joined')

    def __repr__(self):
        return f'<JournalEntry {self.entry_code}>'

    def recalculate_totals(self):
        self.total_mga_debit = sum(l.amount_mga or 0 for l in self.lines if l.side == 'debit')
        self.total_mga_credit = sum(l.amount_mga or 0 for l in self.lines if l.side == 'credit')
        self.total_usd_debit = sum(l.amount_usd or 0 for l in self.lines if l.side == 'debit')
        self.total_usd_credit = sum(l.amount_usd or 0 for l in self.lines if l.side == 'credit')
        self.total_eur_debit = sum(l.amount_eur or 0 for l in self.lines if l.side == 'debit')
        self.total_eur_credit = sum(l.amount_eur or 0 for l in self.lines if l.side == 'credit')
        
        self.is_balanced = (
            self.total_mga_debit == self.total_mga_credit and
            self.total_usd_debit == self.total_usd_credit and
            self.total_eur_debit == self.total_eur_credit
        )


class JournalLine(db.Model):
    """
    Ligne d'écriture (Crédit ou Débit).
    """
    __tablename__ = 'journal_lines'

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'), nullable=False)
    
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    account = db.relationship('Account', backref='journal_lines')
    
    side = db.Column(db.String(10), nullable=False)  # 'debit' ou 'credit'
    
    amount_mga = db.Column(db.Numeric(18, 2), default=0)
    amount_usd = db.Column(db.Numeric(18, 2), default=0)
    amount_eur = db.Column(db.Numeric(18, 2), default=0)
    
    line_description = db.Column(db.String(300), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<JournalLine {self.side} {self.account.code if self.account else "?"}>'


class Attachment(db.Model):
    """
    Pièces justificatives (photos / documents) liées à une écriture.
    """
    __tablename__ = 'attachments'

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'), nullable=False)
    
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)  # nom unique sur disque
    file_type = db.Column(db.String(50), nullable=True)          # image/jpeg, application/pdf...
    file_size = db.Column(db.Integer, nullable=True)             # en octets
    
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_by = db.relationship('User', backref='uploaded_attachments')
    
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f'<Attachment {self.original_filename} for {self.entry_id}>'
