"""
Import des données des fichiers Excel RRM Antsirabe
- Brouillard (écritures)
- Plan Comptable (complément)
- Budget Antsirabe
"""
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
import openpyxl
from app import db
from app.models.entry import JournalEntry, JournalLine
from app.models.account import Account
from app.models.operator import Operator
from app.models.period import Period
from app.models.cost_center import CostCenter
from app.models.budget import Budget, BudgetLine
from app.models.user import User
from app.routes.journal import generate_entry_code


def get_or_create_account(code, name, level=4, parent_code=None, account_class='finances'):
    acc = Account.query.filter_by(code=str(code)).first()
    if acc:
        return acc
    parent_id = None
    if parent_code:
        parent = Account.query.filter_by(code=str(parent_code)).first()
        if parent:
            parent_id = parent.id
    acc = Account(
        code=str(code),
        name=name,
        level=level,
        parent_id=parent_id,
        account_class=account_class
    )
    db.session.add(acc)
    db.session.flush()
    return acc


def import_brouillard_sample(admin_user_id=1):
    """
    Importe les 4 écritures présentes dans le fichier Brouillard
    (période du 27/07/2026).
    """
    # S'assurer que les comptes existent
    get_or_create_account('10201001', "Caisse MGA Bureau d'Antsirabe", 4, '10201')
    get_or_create_account('19901001', 'Reporté de la période précédente', 4, '19901')
    get_or_create_account('10501002', "Virements aux activités d'Ambavaloza en MGA", 4, '10501')
    get_or_create_account('10501003', "Virements aux activités d'Anjanabonoina en MGA", 4, '10501')
    get_or_create_account('10501004', 'Virements aux activités de Benono en MGA', 4, '10501')

    operator = Operator.query.filter_by(code='Grg').first() or Operator.query.first()
    period = Period.query.filter_by(is_current=True).first()
    entry_date = date(2026, 7, 27)

    # Vérifier si déjà importé
    if JournalEntry.query.filter_by(entry_code='ECR-2026-07-27-0001').first():
        print("Écritures du Brouillard déjà importées.")
        return

    entries_data = [
        {
            'desc': 'Solde de la période précédente',
            'lines': [
                {'code': '10201001', 'side': 'credit', 'mga': 28614000},
                {'code': '19901001', 'side': 'debit', 'mga': 28614000},
            ]
        },
        {
            'desc': 'Approvisionnement de la caisse Ambavaloza',
            'lines': [
                {'code': '10501002', 'side': 'credit', 'mga': 670000},
                {'code': '10201001', 'side': 'debit', 'mga': 670000},
            ]
        },
        {
            'desc': 'Approvisionnement de la caisse Anjanabonoina',
            'lines': [
                {'code': '10501003', 'side': 'credit', 'mga': 4372300},
                {'code': '10201001', 'side': 'debit', 'mga': 4372300},
            ]
        },
        {
            'desc': 'Approvisionnement à la caisse de Benono',
            'lines': [
                {'code': '10501004', 'side': 'credit', 'mga': 14175500},
                {'code': '10201001', 'side': 'debit', 'mga': 14175500},
            ]
        },
    ]

    for data in entries_data:
        code = generate_entry_code(entry_date)
        entry = JournalEntry(
            entry_code=code,
            entry_date=entry_date,
            description=data['desc'],
            operator_id=operator.id,
            created_by_id=admin_user_id,
            period_id=period.id if period else None,
            status='posted'
        )
        db.session.add(entry)
        db.session.flush()

        for ln in data['lines']:
            acc = Account.query.filter_by(code=ln['code']).first()
            if not acc:
                continue
            line = JournalLine(
                entry_id=entry.id,
                account_id=acc.id,
                side=ln['side'],
                amount_mga=Decimal(ln['mga']),
                amount_usd=Decimal('0'),
                amount_eur=Decimal('0')
            )
            db.session.add(line)

        entry.recalculate_totals()
        print(f"  ✓ {entry.entry_code} – {entry.description}")

    db.session.commit()
    print("Import Brouillard terminé.")


def import_budget_antsirabe(admin_user_id=1):
    """
    Importe le budget de fonctionnement du bureau d'Antsirabe
    à partir de la structure du fichier Excel.
    """
    if Budget.query.filter_by(code='BudFoTsi09_01').first():
        print("Budget Antsirabe déjà importé.")
        return

    cc = CostCenter.query.filter_by(code='ANT').first()
    period = Period.query.filter_by(is_current=True).first()

    budget = Budget(
        code='BudFoTsi09_01',
        name="Budget de fonctionnement du bureau annexe d'Antsirabe – Septembre 2026",
        cost_center_id=cc.id if cc else None,
        period_id=period.id if period else None,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        created_by_id=admin_user_id
    )
    db.session.add(budget)
    db.session.flush()

    # Lignes extraites du fichier Antsirabe Budget
    lines = [
        # Ordinaires - Logement
        ('Logement du personnel expatrié', 'Logement de Giorgio', 1, 'forfait', 1, 'mois', True),
        ('Logement du personnel expatrié', 'Logement du personnel congolais', 1, 'forfait', 1, 'mois', True),
        # Salaires expatriés
        ('Salaire du personnel expatrié', 'Lucien', 1, 'forfait', 1, 'mois', True),
        ('Salaire du personnel expatrié', 'Lydia', 1, 'forfait', 1, 'mois', True),
        ('Salaire du personnel expatrié', 'Christian', 1, 'forfait', 1, 'mois', True),
        # Salaire local
        ('Salaire du personnel local', 'Hery', 1, 'forfait', 1, 'mois', True),
        # Nourriture
        ('Nourriture du personnel', 'Nourriture du personnel Congolais', 3, 'Personne', 30, 'jour', True),
        ('Nourriture du personnel', 'Nourriture de Giorgio', 1, 'Personne', 30, 'jour', True),
        # Consommables
        ('Consommables', 'Gaz pour réchaud', 1, 'forfait', 1, 'fois', True),
        ('Consommables', 'Papiers de toilette, savons, matériels de nettoyage…', 1, 'forfait', 1, 'fois', True),
        # Communication
        ('Communication du personnel', 'Téléphone et internet de Giorgio', 1, 'forfait', 1, 'mois', True),
        ('Communication du personnel', 'Téléphone et internet de Lucien', 1, 'forfait', 1, 'mois', True),
        ('Communication du personnel', 'Téléphone et internet de Lydia', 1, 'forfait', 1, 'mois', True),
        ('Communication du personnel', 'Téléphone et internet de Christian', 1, 'forfait', 1, 'mois', True),
        ('Communication du personnel', 'Téléphone et internet de Hery', 1, 'forfait', 1, 'mois', True),
        ('Communication du personnel', 'Téléphone et internet de Dany', 1, 'forfait', 1, 'mois', True),
        # Bureau
        ("Bureau d'Antsirabe", "Location du bureau d'Antsirabe", 1, 'forfait', 1, 'mois', True),
        ('Papeterie et consommables de bureau', 'Papeterie et consommables de bureau', 1, 'forfait', 1, 'mois', True),
        # Véhicules
        ('Entretien des véhicules', 'Entretien des motos', 1, 'forfait', 1, 'fois', True),
        # Transport
        ('Transport à Antsirabe', 'Carburant pour véhicules propres à Antsirabe', 1, 'forfait', 1, 'mois', True),
        ('Transport à Antsirabe', 'Pousse pousse', 1, 'forfait', 1, 'mois', True),
        # Activités
        ('Activités', 'Mission hors bureau', 1, 'forfait', 1, 'fois', True),
        # Extraordinaires
        ('Visas (Lucien et Christian)', 'Visa transformable pour Lucien et Christian', 2, 'forfait', 1, 'fois', False),
        ('Visas (Lucien et Christian)', 'Visas long séjour de deux ans pour Lucien et Christian', 2, 'Personne', 1, 'fois', False),
        ('Création de la société Le Fourmi', 'Capital social de la nouvelle société (Le Fourmi)', 1, 'forfait', 1, 'fois', False),
        ('Création de la société Le Fourmi', 'Frais de création de la nouvelle société (Le Fourmi)', 1, 'forfait', 1, 'fois', False),
        # Avances
        ('Avances', 'Avances de Giorgio', 1, 'forfait', 1, 'fois', False),
        # Arriérés
        ('Factures arriérées', 'Réparation de la Land Rover', 1, 'forfait', 1, 'fois', False),
        # Imprévus
        ('Imprévus', 'Imprévus', 1, 'forfait', 1, 'fois', False),
    ]

    for cat, desc, qty, qty_u, occ, occ_u, ordinary in lines:
        bl = BudgetLine(
            budget_id=budget.id,
            category=cat,
            description=desc,
            quantity=Decimal(qty),
            quantity_unit=qty_u,
            occurrence=Decimal(occ),
            occurrence_unit=occ_u,
            unit_cost_mga=Decimal('0'),
            total_cost_mga=Decimal('0'),
            unit_cost_usd=Decimal('0'),
            total_cost_usd=Decimal('0'),
            is_ordinary=ordinary
        )
        db.session.add(bl)

    db.session.commit()
    print(f"✓ Budget {budget.code} importé avec {len(lines)} lignes.")


def run_all_imports():
    """Point d'entrée pour importer toutes les données de base."""
    from app import create_app
    app = create_app()
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        admin_id = admin.id if admin else 1
        print("=== Import des données Excel ===")
        import_brouillard_sample(admin_id)
        import_budget_antsirabe(admin_id)
        print("=== Fin de l'import ===")


if __name__ == '__main__':
    run_all_imports()
