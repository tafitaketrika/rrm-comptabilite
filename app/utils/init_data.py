from datetime import date
from app import db
from app.models.user import User
from app.models.operator import Operator
from app.models.account import Account
from app.models.cost_center import CostCenter
from app.models.period import Period


def init_default_data():
    """Initialise les données de base au premier démarrage."""
    
    # 1. Utilisateur Administrateur par défaut
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@rrm-antsirabe.mg',
            full_name='Administrateur Système',
            role='admin',
            is_active=True
        )
        db.session.add(admin)
        print("✓ Utilisateur administrateur créé")
    admin.set_password('Tafita2026!!')
    admin.role = 'admin'
    admin.is_active = True
    print("✓ Mot de passe admin mis à jour (admin / Tafita2026!!)")

    # 2. Opérateurs
    operators_data = [
        ('Chr', 'Christian'),
        ('Grg', 'Giorgio'),
        ('Lcn', 'Lucien'),
        ('Odl', 'Odile'),
        ('Rvk', 'Ravaka'),
        ('Tsr', 'Tsiry'),
        ('Lyd', 'Lydia'),
    ]
    for code, name in operators_data:
        if not Operator.query.filter_by(code=code).first():
            db.session.add(Operator(code=code, name=name))
    print("✓ Opérateurs créés")

    # 3. Centres de coût
    cost_centers_data = [
        ('ANT', 'Antsirabe - Bureau'),
        ('AMB', 'Ambanja'),
        ('AVL', 'Ambavaloza'),
        ('ANJ', 'Anjanabonoina'),
        ('BEN', 'Benono'),
        ('TSA', 'Tsarafara'),
        ('FOU', 'Fourmi'),
    ]
    for code, name in cost_centers_data:
        if not CostCenter.query.filter_by(code=code).first():
            db.session.add(CostCenter(code=code, name=name))
    print("✓ Centres de coût créés")

    # 4. Période initiale
    if not Period.query.first():
        period = Period(
            name='Période 2026-07-27 → 2026-09-30',
            start_date=date(2026, 7, 27),
            end_date=date(2026, 9, 30),
            is_open=True,
            is_current=True
        )
        db.session.add(period)
        print("✓ Période initiale créée")

    # 5. Plan Comptable (extrait principal)
    accounts_data = [
        # Niveau 1
        (1, '1', 'Finances', None, 'finances'),
        (1, '2', 'Fonctionnement ordinaire', None, 'fonctionnement'),
        
        # Niveau 2 - Finances
        (2, '101', 'Banques', '1', 'finances'),
        (2, '102', 'Caisses', '1', 'finances'),
        (2, '103', 'Transferts', '1', 'finances'),
        (2, '104', 'Prêts et Emprunts', '1', 'finances'),
        (2, '105', 'Virements des fonds', '1', 'finances'),
        (2, '192', 'Opérations comptables de répartition des dépenses', '1', 'finances'),
        (2, '199', 'Opérations comptables de commencement et fin d\'exercice', '1', 'finances'),
        
        # Niveau 3 & 4 - Caisses
        (3, '10201', 'Caisses MGA', '102', 'finances'),
        (4, '10201001', "Caisse MGA Bureau d'Antsirabe", '10201', 'finances'),
        (4, '10201002', 'Caisse MGA Ambanja', '10201', 'finances'),
        (4, '10201003', 'Caisse MGA Ambavaloza', '10201', 'finances'),
        (4, '10201004', 'Caisse MGA Anjanabonoina', '10201', 'finances'),
        (4, '10201005', 'Caisse MGA Benono', '10201', 'finances'),
        (4, '10201006', 'Caisse MGA Tsarafara', '10201', 'finances'),
        (4, '10201007', 'Caisse MGA Fourmi', '10201', 'finances'),
        (4, '10201101', 'Caisse MGA Hery', '10201', 'finances'),
        (4, '10201102', 'Caisse MGA Danis', '10201', 'finances'),
        (4, '10201201', 'Caisse MGA Giorgio', '10201', 'finances'),
        (4, '10201202', 'Caisse MGA Lucien', '10201', 'finances'),
        (4, '10201203', 'Caisse MGA Christian', '10201', 'finances'),
        (4, '10201204', 'Caisse MGA Lydia', '10201', 'finances'),
        
        (3, '10202', 'Caisses EUR', '102', 'finances'),
        (4, '10202001', "Caisse EUR Bureau d'Antsirabe", '10202', 'finances'),
        (4, '10202005', 'Caisse EUR Benono', '10202', 'finances'),
        
        (3, '10203', 'Caisses USD', '102', 'finances'),
        (4, '10203001', "Caisse USD Bureau d'Antsirabe", '10203', 'finances'),
        
        # Banques
        (3, '10101', 'Banques MGA', '101', 'finances'),
        (4, '10101001', 'BMOI', '10101', 'finances'),
        (3, '10102', 'Banques USD', '101', 'finances'),
        (4, '10102001', 'BK', '10102', 'finances'),
        
        # Virements
        (3, '10501', 'Virements des fonds aux activités en MGA', '105', 'finances'),
        (4, '10501001', "Virements aux activités d'Ambanja en MGA", '10501', 'finances'),
        (4, '10501002', "Virements aux activités d'Ambavaloza en MGA", '10501', 'finances'),
        (4, '10501003', "Virements aux activités d'Anjanabonoina en MGA", '10501', 'finances'),
        (4, '10501004', 'Virements aux activités de Benono en MGA', '10501', 'finances'),
        (4, '10501005', 'Virements aux activités de Tsarafara en MGA', '10501', 'finances'),
        (4, '10501006', 'Virements aux activités de Fourmi en MGA', '10501', 'finances'),
        
        # Report à nouveau
        (3, '19901', 'Report à nouveau', '199', 'finances'),
        (4, '19901001', 'Reporté de la période précédente', '19901', 'finances'),
        (4, '19901002', 'A reporter à la période suivante', '19901', 'finances'),
        
        # Fonctionnement - Personnel
        (2, '201', 'Personnel', '2', 'fonctionnement'),
        (3, '20101', 'Rétributions du personnel local malgache', '201', 'fonctionnement'),
        (4, '20101101', 'Hery', '20101', 'fonctionnement'),
        (4, '20101102', 'Danis', '20101', 'fonctionnement'),
        (3, '20102', 'Rétributions du personnel expatrié', '201', 'fonctionnement'),
        (4, '20102202', 'Lucien', '20102', 'fonctionnement'),
        (4, '20102203', 'Christian', '20102', 'fonctionnement'),
        (4, '20102204', 'Lydia', '20102', 'fonctionnement'),
        (3, '20103', 'Avance sur salaire', '201', 'fonctionnement'),
        (4, '20103201', 'Giorgio', '20103', 'fonctionnement'),
        
        # Logement, Nourriture, Communication
        (3, '20114', 'Logement du personnel expatrié à Madagascar', '201', 'fonctionnement'),
        (4, '20114201', 'Logement de Giorgio', '20114', 'fonctionnement'),
        (4, '20114211', 'Logement du personnel congolais', '20114', 'fonctionnement'),
        (3, '20115', 'Nourriture du personnel expatrié à Madagascar', '201', 'fonctionnement'),
        (4, '20115201', 'Nourriture de Giorgio', '20115', 'fonctionnement'),
        (4, '20115211', 'Nourriture des Congolais', '20115', 'fonctionnement'),
        (3, '20116', 'Communication du personnel expatrié à Madagascar', '201', 'fonctionnement'),
        (4, '20116201', 'Téléphone et internet de Giorgio', '20116', 'fonctionnement'),
        (4, '20116202', 'Téléphone et internet de Lucien', '20116', 'fonctionnement'),
        (4, '20116203', 'Téléphone et internet de Christian', '20116', 'fonctionnement'),
        (4, '20116204', 'Téléphone et internet de Lydia', '20116', 'fonctionnement'),
        
        # Locaux
        (2, '203', 'Locaux', '2', 'fonctionnement'),
        (3, '20301', "Bureau d'Antsirabe", '203', 'fonctionnement'),
        (4, '20301001', "Location du bureau d'Antsirabe", '20301', 'fonctionnement'),
        
        # Véhicules
        (2, '206', 'Véhicules propres', '2', 'fonctionnement'),
        (3, '20601', 'Voitures', '206', 'fonctionnement'),
        (4, '20601003', 'Land Rover 5538TAB Entretien', '20601', 'fonctionnement'),
        (3, '20602', 'Motos', '206', 'fonctionnement'),
        (4, '20602003', 'Entretien', '20602', 'fonctionnement'),
        
        # Imprévus
        (2, '295', 'Imprévus', '2', 'fonctionnement'),
        (3, '29501', 'Imprévus', '295', 'fonctionnement'),
        (4, '29501001', 'Imprévus', '29501', 'fonctionnement'),
    ]

    # Création des comptes avec résolution des parents
    code_to_id = {}
    for level, code, name, parent_code, account_class in accounts_data:
        if Account.query.filter_by(code=code).first():
            continue
        parent_id = code_to_id.get(parent_code) if parent_code else None
        acc = Account(
            code=code,
            name=name,
            level=level,
            parent_id=parent_id,
            account_class=account_class
        )
        db.session.add(acc)
        db.session.flush()  # pour obtenir l'id
        code_to_id[code] = acc.id

    print("✓ Plan Comptable initialisé")

    db.session.commit()
    print("=== Initialisation terminée ===")
