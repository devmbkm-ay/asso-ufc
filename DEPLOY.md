# Guide de déploiement — Hetzner + Coolify

## Prérequis

- VPS Hetzner actif avec Coolify installé (tu as déjà ça avec OpenClaw)
- Repo GitHub : `devmbkm-ay/asso-backend` (à créer)
- Nom de domaine avec accès DNS (ex: `api.mboka.fr`)

---

## Étape 1 — Préparer le repo GitHub

```bash
# Dans le dossier backend/
cd backend/
git init
git add .
git commit -m "feat: initial backend — FastAPI + auth JWT + CRUD membres"

# Créer le repo sur GitHub puis :
git remote add origin https://github.com/devmbkm-ay/asso-backend.git
git push -u origin main
```

**Fichiers à ne PAS committer** (vérifie le .gitignore) :
- `.env` (jamais en clair dans le repo)
- `__pycache__/`, `*.pyc`

---

## Étape 2 — Créer le service PostgreSQL sur Coolify

Dans Coolify → **New Resource** → **Database** → **PostgreSQL 16**

| Champ | Valeur |
|---|---|
| Name | `asso-db` |
| DB Name | `asso_db` |
| User | `asso_user` |
| Password | *(générer un mot de passe fort)* |
| Port | `5432` (interne uniquement) |

→ Cliquer **Deploy**. Coolify crée le conteneur et génère l'URL interne :
```
postgresql://asso_user:MOTDEPASSE@asso-db:5432/asso_db
```
**Copier cette URL** — tu en auras besoin à l'étape 4.

---

## Étape 3 — Créer le service API sur Coolify

Dans Coolify → **New Resource** → **Application** → **Docker**

| Champ | Valeur |
|---|---|
| Name | `asso-api` |
| Source | GitHub → repo `asso-backend` |
| Branch | `main` |
| Build Pack | **Dockerfile** (Coolify détecte automatiquement) |
| Port | `8000` |
| Domain | `api.mboka.fr` (ou ton sous-domaine) |
| HTTPS | ✅ activé (Traefik + Let's Encrypt automatique) |

---

## Étape 4 — Variables d'environnement dans Coolify

Dans le service `asso-api` → onglet **Environment Variables** → ajouter :

```
DATABASE_URL=postgresql://asso_user:MOTDEPASSE@asso-db:5432/asso_db
SECRET_KEY=                  # python -c "import secrets; print(secrets.token_hex(32))"
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7
DEBUG=false
ALLOWED_ORIGINS=https://mboka.fr,https://www.mboka.fr
EMAIL_FROM=noreply@mboka.fr
EMAIL_FROM_NAME=Association Mboka
BREVO_API_KEY=               # à remplir quand tu crées le compte Brevo
```

> ⚠️ Ne pas mettre `.env` dans le repo — Coolify injecte ces variables
> directement dans le conteneur au moment du build.

---

## Étape 5 — Premier déploiement

Dans Coolify → service `asso-api` → **Deploy**

Coolify va :
1. Cloner le repo depuis GitHub
2. Construire l'image Docker (multi-stage)
3. Lancer `entrypoint.sh` qui attend PostgreSQL, applique les migrations, démarre uvicorn
4. Configurer Traefik pour router `api.mboka.fr` → port 8000 avec HTTPS

**Suivre les logs en direct** dans Coolify → onglet **Logs** :
```
⏳ Attente de PostgreSQL...
✅ PostgreSQL prêt.
🔄 Application des migrations Alembic...
INFO  [alembic.runtime.migration] Running upgrade -> 0001, Initial schema
INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, Seed roles
🚀 Démarrage de l'API...
INFO:     Application startup complete.
```

---

## Étape 6 — Vérification

```bash
# Health check
curl https://api.mboka.fr/health
# → {"status":"ok","version":"1.0.0"}

# Documentation Swagger (désactiver en prod après validation)
# https://api.mboka.fr/docs
```

---

## Déploiements suivants (CD automatique)

Dans Coolify → service `asso-api` → **Webhooks** :
Activer **Auto-deploy on push** → chaque `git push origin main` déclenche
un rebuild et redéploiement automatique.

```bash
# Workflow quotidien
git add .
git commit -m "feat: routes cotisations"
git push origin main
# → Coolify rebuild + redéploie automatiquement
```

---

## Commandes utiles en cas de problème

```bash
# Depuis le terminal Coolify (ou SSH sur le VPS)

# Voir les logs du conteneur API
docker logs asso-api --tail 100 -f

# Accéder au conteneur pour debugger
docker exec -it asso-api sh

# Relancer les migrations manuellement
docker exec asso-api alembic upgrade head

# Vérifier l'état des migrations
docker exec asso-api alembic current

# Rollback d'une migration
docker exec asso-api alembic downgrade -1
```

---

## Architecture finale sur le VPS

```
VPS Hetzner (46.224.160.205)
├── Coolify
│   ├── Traefik (reverse proxy + HTTPS automatique)
│   ├── asso-db      (PostgreSQL 16)
│   ├── asso-api     (FastAPI → api.mboka.fr)
│   └── openclaw     (ton assistant Telegram — déjà en place)
└── Docker network interne
    └── asso-api → asso-db (connexion directe, sans passer par internet)
```
