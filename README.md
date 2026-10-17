# RRM Antsirabe – Application de Gestion Comptable & Financière

Application web développée à partir des fichiers Excel :
- `260905 RRM Planification et Résumé de Finances.xlsx`
- `260905 RRM Antsirabe -Instrument Comptable Interne.xlsx`

## Fonctionnalités

- **Authentification** avec rôles (Administrateur, Comptable, Lecteur, Responsable site)
- **Utilisateur administrateur par défaut** : `admin` / `AdminRRM2026!`
- L’administrateur crée les autres utilisateurs et leur attribue un niveau d’accès
- **Plan Comptable** hiérarchique (4 niveaux) multi-devises (MGA, USD, EUR)
- **Brouillard (Journal)** en partie double
  - Code unique automatique : `ECR-AAAA-MM-JJ-XXXX`
  - Validation d’équilibre Débit = Crédit par devise
  - **Upload de pièces justificatives** (photos / PDF) lors de la saisie
- Opérateurs (Chr, Grg, Lcn, Odl, Rvk, Tsr, Lyd)
- Centres de coût / Sites
- Périodes comptables
- Tableau de bord et rapports (Balance des comptes)
- Module Budgets (structure prête)

## Installation & Lancement

```bash
cd rrm_comptabilite
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run.py
```

Puis ouvrir : http://127.0.0.1:5000

## Identifiants par défaut

| Utilisateur | Mot de passe     | Rôle            |
|-------------|------------------|-----------------|
| admin       | AdminRRM2026!    | Administrateur  |

## Structure technique

- Backend : Flask + SQLAlchemy + Flask-Login
- Base de données : SQLite (fichier `instance/rrm_finance.db`)
- Frontend : Bootstrap 5
- Fichiers uploadés : `app/static/uploads/`

## Sécurité

- Mot de passe hashé (Werkzeug)
- Contrôle d’accès par rôle (RBAC)
- Taille max des fichiers : 16 Mo
- Extensions autorisées : png, jpg, jpeg, gif, pdf, webp

## Import des données Excel

Après le premier lancement, exécutez :

```bash
cd rrm_comptabilite
python3 -m app.utils.import_excel
```

Cela importe :
- Les 4 écritures du Brouillard (solde initial + 3 virements sites)
- Le budget de fonctionnement Antsirabe (lignes ordinaires + extraordinaires)

## Structure des codes d'écriture

Chaque écriture possède :
- `id` : clé primaire technique (auto-incrément)
- `entry_code` : identifiant métier unique `ECR-AAAA-MM-JJ-XXXX`

## Pièces justificatives

Lors de la création d'une écriture, l'opérateur peut joindre plusieurs fichiers image ou PDF.
Ils sont stockés dans `app/static/uploads/` et liés à l'écriture.
