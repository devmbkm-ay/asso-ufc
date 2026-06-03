# Migrations Alembic — Guide d'utilisation

## Setup (une seule fois)

```bash
# 1. Copier le fichier d'environnement
cp .env.example .env
# Renseigner DATABASE_URL dans .env :
# DATABASE_URL=postgresql://user:password@localhost:5432/asso_db

# 2. Installer les dépendances Python
pip install -r requirements.txt

# 3. Mettre à jour alembic.ini avec l'URL de la DB
# (ou utiliser une variable d'env — voir env.py)
```

## Commandes quotidiennes

```bash
# Appliquer toutes les migrations (état initial ou mise à jour)
alembic upgrade head

# Voir l'état actuel
alembic current

# Voir l'historique complet
alembic history --verbose

# Revenir à la migration précédente (rollback)
alembic downgrade -1

# Revenir à zéro (⚠️ détruit toutes les données)
alembic downgrade base
```

## Créer une nouvelle migration

```bash
# Après avoir modifié models.py, générer automatiquement la migration
alembic revision --autogenerate -m "description_du_changement"

# Exemple : ajouter un champ city à members
alembic revision --autogenerate -m "add_city_to_members"
```

Alembic compare le modèle SQLAlchemy avec l'état réel de la base
et génère les instructions SQL nécessaires dans `alembic/versions/`.

## Structure des fichiers

```
backend/
├── alembic/
│   ├── env.py              # Config — pointe vers nos models
│   ├── script.py.mako      # Template des fichiers de migration
│   └── versions/
│       ├── 0001_initial_schema.py   # Création des 9 tables
│       └── 0002_seed_roles.py       # Données initiales (4 rôles)
├── alembic.ini             # Config Alembic (URL de la DB)
└── models.py               # Modèles SQLAlchemy (source de vérité)
```

## Déploiement sur Hetzner/Coolify

Dans le Dockerfile ou le script de démarrage :
```bash
alembic upgrade head && uvicorn api:app --host 0.0.0.0 --port 8000
```

La migration s'exécute automatiquement à chaque déploiement.
Si rien n'a changé, Alembic ne fait rien (idempotent).
