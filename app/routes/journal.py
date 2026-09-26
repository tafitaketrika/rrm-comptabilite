import os
import uuid
from datetime import datetime, date
from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, send_from_directory, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.entry import JournalEntry, JournalLine, Attachment
from app.models.account import Account
from app.models.operator import Operator
from app.models.period import Period
from app.models.cost_center import CostCenter

journal_bp = Blueprint('journal', __name__)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def generate_entry_code(entry_date):
    """Génère un code unique ECR-AAAA-MM-JJ-XXXX"""
    date_str = entry_date.strftime('%Y-%m-%d')
    prefix = f"ECR-{date_str}-"
    last = JournalEntry.query.filter(
        JournalEntry.entry_code.like(f"{prefix}%")
    ).order_by(JournalEntry.entry_code.desc()).first()
    if last:
        try:
            last_num = int(last.entry_code.split('-')[-1])
            next_num = last_num + 1
        except ValueError:
            next_num = 1
    else:
        next_num = 1
    return f"{prefix}{next_num:04d}"


@journal_bp.route('/')
@login_required
def list_entries():
    page = request.args.get('page', 1, type=int)
    entries = JournalEntry.query.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc()).paginate(page=page, per_page=20)
    return render_template('journal/list.html', entries=entries)


@journal_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_entry():
    if not current_user.can_edit_journal():
        abort(403)
    
    accounts = Account.query.filter_by(is_active=True, level=4).order_by(Account.code).all()
    # Filtrer selon les droits comptes de l'utilisateur
    allowed = current_user.allowed_account_ids()
    if allowed is not None:
        accounts = [a for a in accounts if a.id in allowed]
    operators = Operator.query.filter_by(is_active=True).all()
    today = date.today()
    today_display = today.strftime('%d/%m/%y')
    
    if request.method == 'POST':
        entry_date_str = request.form.get('entry_date', '').strip()
        description = request.form.get('description', '').strip()
        credit_account_id = request.form.get('credit_account_id')
        debit_account_id = request.form.get('debit_account_id')
        amount_str = request.form.get('amount', '0') or '0'
        amount_debit_str = request.form.get('amount_debit', amount_str) or amount_str
        currency = request.form.get('currency', 'MGA')
        currency_debit = request.form.get('currency_debit', currency)
        
        # Accepte jj/mm/aa ou jj/mm/aaaa ou yyyy-mm-dd
        entry_date = None
        for fmt in ('%d/%m/%y', '%d/%m/%Y', '%Y-%m-%d'):
            try:
                entry_date = datetime.strptime(entry_date_str, fmt).date()
                break
            except (ValueError, TypeError):
                continue
        if entry_date is None:
            flash('Date invalide. Utilisez le format jj/mm/aa (ex. 20/09/26).', 'danger')
            return render_template('journal/form.html', accounts=accounts, operators=operators, today_display=today_display)
        
        if not description or not credit_account_id or not debit_account_id:
            flash('Date, description, compte de crédit et compte de débit sont obligatoires.', 'danger')
            return render_template('journal/form.html', accounts=accounts, operators=operators, today_display=today_display)
        
        try:
            amount = Decimal(str(amount_str).replace(',', '.'))
            amount_debit = Decimal(str(amount_debit_str).replace(',', '.'))
        except Exception:
            flash('Montant invalide.', 'danger')
            return render_template('journal/form.html', accounts=accounts, operators=operators, today_display=today_display)
        
        # Opérateur lié à l'utilisateur ou premier disponible
        operator = current_user.operator
        if not operator:
            operator = Operator.query.filter_by(is_active=True).first()
        if not operator:
            flash('Aucun opérateur configuré. Contactez l\'administrateur.', 'danger')
            return render_template('journal/form.html', accounts=accounts, operators=operators, today_display=today_display)
        
        period = Period.query.filter_by(is_current=True).first()
        
        entry_code = generate_entry_code(entry_date)
        entry = JournalEntry(
            entry_code=entry_code,
            entry_date=entry_date,
            description=description,
            operator_id=operator.id,
            created_by_id=current_user.id,
            period_id=period.id if period else None,
            status='posted'
        )
        db.session.add(entry)
        db.session.flush()
        
        # Ligne crédit
        credit_mga = credit_usd = credit_eur = Decimal('0')
        if currency == 'MGA':
            credit_mga = amount
        elif currency == 'USD':
            credit_usd = amount
        else:
            credit_eur = amount
        
        line_credit = JournalLine(
            entry_id=entry.id,
            account_id=int(credit_account_id),
            side='credit',
            amount_mga=credit_mga,
            amount_usd=credit_usd,
            amount_eur=credit_eur
        )
        db.session.add(line_credit)
        
        # Ligne débit
        debit_mga = debit_usd = debit_eur = Decimal('0')
        if currency_debit == 'MGA':
            debit_mga = amount_debit
        elif currency_debit == 'USD':
            debit_usd = amount_debit
        else:
            debit_eur = amount_debit
        
        line_debit = JournalLine(
            entry_id=entry.id,
            account_id=int(debit_account_id),
            side='debit',
            amount_mga=debit_mga,
            amount_usd=debit_usd,
            amount_eur=debit_eur
        )
        db.session.add(line_debit)
        
        db.session.flush()
        entry.recalculate_totals()
        
        if not entry.is_balanced:
            flash('Attention : l\'écriture n\'est pas équilibrée. Elle a été enregistrée en brouillon.', 'warning')
            entry.status = 'draft'
        else:
            flash(f'Écriture {entry_code} enregistrée avec succès.', 'success')
        
        # Pièces jointes
        files = request.files.getlist('attachments')
        for f in files:
            if f and f.filename and allowed_file(f.filename):
                original = secure_filename(f.filename)
                ext = original.rsplit('.', 1)[1].lower()
                stored = f"{entry.entry_code}_{uuid.uuid4().hex[:8]}.{ext}"
                filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], stored)
                f.save(filepath)
                att = Attachment(
                    entry_id=entry.id,
                    original_filename=original,
                    stored_filename=stored,
                    file_type=f.content_type,
                    file_size=os.path.getsize(filepath),
                    uploaded_by_id=current_user.id
                )
                db.session.add(att)
        
        db.session.commit()
        return redirect(url_for('journal.view_entry', entry_id=entry.id))
    
    return render_template('journal/form.html', accounts=accounts, operators=operators, today_display=today_display)


@journal_bp.route('/<int:entry_id>')
@login_required
def view_entry(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    return render_template('journal/view.html', entry=entry)


@journal_bp.route('/attachment/<int:att_id>')
@login_required
def download_attachment(att_id):
    att = Attachment.query.get_or_404(att_id)
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'],
        att.stored_filename,
        as_attachment=True,
        download_name=att.original_filename
    )
