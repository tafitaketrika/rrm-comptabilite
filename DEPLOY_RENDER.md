# Déploiement sur Render – RRM Antsirabe

## Étapes simples

### 1. Créer un compte Render
Allez sur : https://render.com  
Inscrivez-vous (avec GitHub de préférence).

### 2. Mettre le code sur GitHub
1. Créez un nouveau dépôt privé ou public sur GitHub
2. Dans le Terminal (sur votre Mac) :

```bash
cd ~/Desktop/rrm_comptabilite
git init
git add .
git commit -m "RRM Antsirabe - première version"
git branch -M main
git remote add origin https://github.com/VOTRE_NOM/rrm-comptabilite.git
git push -u origin main
```

(Remplacez `VOTRE_NOM` par votre nom d’utilisateur GitHub)

### 3. Créer le service Web sur Render
1. Dans Render → **New** → **Web Service**
2. Connectez votre dépôt GitHub `rrm-comptabilite`
3. Paramètres :
   - **Name** : `rrm-antsirabe` (ou autre)
   - **Runtime** : Python 3
   - **Build Command** : `pip install -r requirements.txt`
   - **Start Command** : `gunicorn run:app --bind 0.0.0.0:$PORT`
4. Cliquez sur **Advanced** et ajoutez les variables d’environnement :
   - `SECRET_KEY` → mettez une longue phrase secrète (ex. : `RRM-Antsirabe-2026-Secret-Key-ChangeMe`)
   - `FLASK_DEBUG` → `0`

### 4. Ajouter une base de données PostgreSQL (recommandé)
1. Dans Render → **New** → **PostgreSQL**
2. Créez-la (plan gratuit)
3. Une fois créée, copiez l’**Internal Database URL**
4. Retournez dans votre Web Service → **Environment**
5. Ajoutez :
   - `DATABASE_URL` → collez l’URL PostgreSQL

### 5. Déployer
Cliquez sur **Create Web Service**.  
Render va installer les dépendances et lancer l’application (2-5 minutes).

Quand c’est prêt, vous aurez une adresse du type :
`https://rrm-antsirabe.onrender.com`

Connectez-vous avec :
- Identifiant : `admin`
- Mot de passe : `AdminRRM2026!`

---

## Notes importantes
- Le plan gratuit de Render met l’application en veille après 15 min d’inactivité (le premier chargement peut prendre 30-50 secondes).
- Les fichiers uploadés (pièces justificatives) sont perdus au redémarrage sur le plan gratuit. On pourra ajouter un stockage cloud plus tard si besoin.
- Changez le mot de passe admin dès la première connexion en production.
EOF
echo "DEPLOY guide created"