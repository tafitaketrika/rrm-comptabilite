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
    from app.routes.projects import projects_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(users_bp, url_prefix='/users')
    app.register_blueprint(accounts_bp, url_prefix='/accounts')
    app.register_blueprint(journal_bp, url_prefix='/journal')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(budgets_bp, url_prefix='/budgets')
    app.register_blueprint(projects_bp, url_prefix='/projects')

    def _code_body(code):
        """Corps du code sans préfixe année : 01.02.01.001"""
        if not code:
            return ''
        s = str(code).replace(' ', '').replace('-', '').replace('.', '')
        # retirer préfixe année 2 chiffres si collé (ex. 26010201001)
        if len(s) >= 4 and s[:2].isdigit():
            yy = int(s[:2])
            if 20 <= yy <= 40 and len(s) in (4, 6, 8, 9, 10, 11):
                # ne pas striper si code naturel commence par 20-40 sans être année
                # on strip seulement si longueur suggère année+corps
                if len(s) in (10, 11):  # 26 + 8/9
                    s = s[2:]
        if len(s) == 8 and not s.startswith('0'):
            s = '0' + s
        elif len(s) % 2 == 1 and len(s) < 7:
            s = '0' + s
        if len(s) == 9:
            return f'{s[0:2]}.{s[2:4]}.{s[4:6]}.{s[6:9]}'
        if len(s) == 7:
            s = '0' + s
            return f'{s[0:2]}.{s[2:4]}.{s[4:6]}.{s[6:8]}'
        if len(s) == 6:
            return f'{s[0:2]}.{s[2:4]}.{s[4:6]}'
        if len(s) == 4:
            return f'{s[0:2]}.{s[2:4]}'
        if len(s) == 2:
            return s
        parts = [s[i:i+2] for i in range(0, len(s), 2)]
        return '.'.join(parts)

    @app.template_filter('format_code')
    def format_account_code(code, year=None):
        """Affichage écran : code SANS préfixe année (01.02.01.001).
        Passer year=26 pour export / détail avec préfixe."""
        body = _code_body(code)
        if not body:
            return ''
        if year is None or year == '':
            return body
        try:
            yy = int(year) % 100
            return f'{yy:02d}.{body}'
        except (TypeError, ValueError):
            return body

    @app.template_filter('format_code_year')
    def format_account_code_year(code, year=None):
        """Code AVEC préfixe année (détail écriture, export CSV)."""
        from datetime import date as _d
        if year is None or year == '':
            year = _d.today().year % 100
        return format_account_code(code, year)

    @app.template_filter('format_code_acc')
    def format_account_code_acc(account):
        """Affichage plan comptable : SANS préfixe année."""
        if account is None:
            return ''
        code = getattr(account, 'code', account)
        return format_account_code(code, None)

    with app.app_context():
        from app.models import project as _project_models  # noqa: F401
        db.create_all()
        try:
            from sqlalchemy import text, inspect
            insp = inspect(db.engine)
            if 'budgets' in insp.get_table_names():
                cols = [c['name'] for c in insp.get_columns('budgets')]
                with db.engine.begin() as conn:
                    if 'currency' not in cols:
                        conn.execute(text("ALTER TABLE budgets ADD COLUMN currency VARCHAR(3) DEFAULT 'MGA'"))
                    if 'assigned_to_json' not in cols:
                        conn.execute(text("ALTER TABLE budgets ADD COLUMN assigned_to_json TEXT"))
                    if 'cc_to_json' not in cols:
                        conn.execute(text("ALTER TABLE budgets ADD COLUMN cc_to_json TEXT"))
        except Exception as _e:
            print('budget cols migrate:', _e)
        from app.utils.init_data import init_default_data
        init_default_data()

    return app
