import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'


def create_app():
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'rrm-antsirabe-secret-key-2026-change-in-prod')
    
    # Base de données : PostgreSQL sur Render, SQLite en local
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # Render fournit postgres:// → SQLAlchemy attend postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/rrm_finance.db'
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max
    app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'webp'}

    # Créer le dossier uploads s'il n'existe pas
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from app.models.user import User, UserModulePermission, UserAccountPermission
    from app.models.account import Account
    from app.models.operator import Operator
    from app.models.period import Period
    from app.models.entry import JournalEntry, JournalLine, Attachment
    from app.models.budget import Budget, BudgetLine
    from app.models.cost_center import CostCenter

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Blueprints
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.users import users_bp
    from app.routes.accounts import accounts_bp
    from app.routes.journal import journal_bp
    from app.routes.reports import reports_bp
    from app.routes.budgets import budgets_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(users_bp, url_prefix='/users')
    app.register_blueprint(accounts_bp, url_prefix='/accounts')
    app.register_blueprint(journal_bp, url_prefix='/journal')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(budgets_bp, url_prefix='/budgets')

    @app.template_filter('format_code')
    def format_account_code(code):
        """Formate un code compte : 10201001 → 10 20 10 01 (groupes de 2)."""
        if not code:
            return ''
        s = str(code).replace(' ', '').replace('-', '')
        # Groupes de 2 caractères
        parts = [s[i:i+2] for i in range(0, len(s), 2)]
        return ' '.join(parts)

    with app.app_context():
        db.create_all()
        # Initialisation des données de base
        from app.utils.init_data import init_default_data
        init_default_data()

    return app
