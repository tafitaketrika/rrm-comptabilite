from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app.models.entry import JournalEntry
from app.models.account import Account
from app.models.period import Period
from app.models.user import User
from app import db

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    total_entries = JournalEntry.query.count()
    total_accounts = Account.query.filter_by(is_active=True).count()
    current_period = Period.query.filter_by(is_current=True).first()
    total_users = User.query.filter_by(is_active=True).count()
    recent_entries = JournalEntry.query.order_by(JournalEntry.created_at.desc()).limit(8).all()
    
    return render_template(
        'main/dashboard.html',
        total_entries=total_entries,
        total_accounts=total_accounts,
        current_period=current_period,
        total_users=total_users,
        recent_entries=recent_entries
    )


@main_bp.route('/import-demo-data', methods=['POST'])
@login_required
def import_demo_data():
    """Importe les écritures du Brouillard + le budget (réservé à l'admin)."""
    if not current_user.is_admin():
        abort(403)
    
    try:
        from app.utils.import_excel import import_brouillard_sample, import_budget_antsirabe
        import_brouillard_sample(admin_user_id=current_user.id)
        import_budget_antsirabe(admin_user_id=current_user.id)
        flash('Données de démonstration importées avec succès (Brouillard + Budget).', 'success')
    except Exception as e:
        flash(f'Erreur lors de l\'import : {str(e)}', 'danger')
    
    return redirect(url_for('main.dashboard'))
