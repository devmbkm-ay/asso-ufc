# Assos-UFC — Fonctionnalités de l'application

Application de gestion d'une association sportive (UFC). API REST construite avec **FastAPI** (Python), une base de données **PostgreSQL**, et des emails transactionnels via **Brevo**.

---

## Architecture générale

```
assos-ufc/
├── models.py                  # Structure de la base de données (tables)
├── app/
│   ├── main.py                # Point d'entrée de l'application
│   ├── core/
│   │   ├── config.py          # Variables d'environnement (.env)
│   │   ├── database.py        # Connexion PostgreSQL
│   │   ├── security.py        # Hachage de mots de passe + tokens JWT
│   │   ├── deps.py            # Authentification + contrôle des rôles (RBAC)
│   │   ├── email.py           # Envoi d'emails via Brevo
│   │   └── tasks.py           # Tâches planifiées (rappels cotisations)
│   └── api/v1/routes/
│       ├── auth.py            # Login, refresh token, profil courant
│       ├── members.py         # Gestion des membres
│       ├── cotisations.py     # Paiements, plans, dashboard trésorier
│       ├── events.py          # Événements, inscriptions, présences
│       └── notifications.py   # Envoi d'emails manuels
└── tests/
    └── test_smoke.py          # Tests de bon fonctionnement de base
```

**Toutes les routes sont accessibles sous le préfixe `/api/v1`.**  
La documentation interactive est disponible sur `/docs` (Swagger) et `/redoc`.

---

## Modèle de données (base de données)

### Tables principales

| Table                | Rôle                                                        |
|----------------------|-------------------------------------------------------------|
| `members`            | Membres de l'association                                    |
| `roles`              | Rôles disponibles (super_admin, treasurer, secretary, member)|
| `member_roles`       | Association membre ↔ rôle (table de liaison)                |
| `cotisation_plans`   | Plans de cotisation (mensuel, annuel, unique)                |
| `payments`           | Paiements enregistrés par le trésorier                      |
| `events`             | Événements organisés par l'association                      |
| `event_registrations`| Inscriptions aux événements + présence                      |
| `notifications`      | Historique des emails envoyés                               |
| `audit_logs`         | Journal de toutes les modifications (qui a fait quoi)       |

### Statuts possibles

- **Membre** : `active` · `inactive` · `suspended` · `honorary`
- **Paiement** : `pending` (en attente) · `confirmed` · `cancelled`
- **Événement** : `draft` · `published` · `cancelled` · `completed`
- **Méthode de paiement** : `cash` · `bank_transfer` · `lydia` · `sumeria` · `other`

---

## Module 1 — Authentification (`/auth`)

### Fonctionnement

L'authentification repose sur des **tokens JWT** (JSON Web Token) — un système de jetons signés qui évite de stocker des sessions côté serveur.

- **Access token** : durée courte (ex. 30 min), utilisé pour chaque requête API
- **Refresh token** : durée longue (ex. 7 jours), utilisé uniquement pour obtenir un nouvel access token

```
Client → POST /auth/login (email + mot de passe)
       ← { access_token, refresh_token }

Client → GET /api/v1/... (Header: Authorization: Bearer <access_token>)
       ← Données protégées

Client → POST /auth/refresh (refresh_token)
       ← { nouveau access_token, nouveau refresh_token }
```

### Endpoints

| Méthode | Route            | Description                                           | Accès |
|---------|------------------|-------------------------------------------------------|-------|
| POST    | `/auth/login`    | Connexion email + mot de passe → tokens               | Public |
| POST    | `/auth/refresh`  | Renouveler les tokens via le refresh token            | Authentifié |
| GET     | `/auth/me`       | Profil du membre connecté (avec ses rôles)            | Authentifié |
| POST    | `/auth/setup`    | Créer le premier super-admin (désactivé ensuite)      | Public (1 seule fois) |

---

## Module 2 — Membres (`/members`)

Gestion du cycle de vie des membres de l'association.

### Endpoints

| Méthode | Route                       | Description                                        | Rôle requis         |
|---------|-----------------------------|---------------------------------------------------|---------------------|
| GET     | `/members`                  | Liste paginée avec filtres (statut, recherche)    | secretary+          |
| POST    | `/members`                  | Créer un membre (envoie un email de bienvenue)    | secretary+          |
| GET     | `/members/{id}`             | Détail d'un membre                                | Soi-même ou rôle+   |
| PATCH   | `/members/{id}`             | Modifier les informations                         | Soi-même ou secretary+ |
| PATCH   | `/members/{id}/status`      | Changer le statut (activer, suspendre…)           | super_admin         |
| DELETE  | `/members/{id}`             | Désactivation (*soft delete*, pas de suppression) | super_admin         |

### Comportements notables

- **Soft delete** : un membre "supprimé" passe simplement au statut `inactive` — ses données sont conservées.
- **Email de bienvenue** automatique à la création (via Brevo, non bloquant si non configuré).
- **Audit trail** : chaque création/modification/suppression est enregistrée dans `audit_logs` avec les valeurs avant/après.
- Un membre peut modifier son propre profil mais pas son statut.

---

## Module 3 — Cotisations (`/cotisation-plans`, `/payments`, `/dashboard`, `/payments/grid`)

Module financier complet pour le trésorier.

### Plans de cotisation

Un plan définit le montant et la fréquence (mensuelle, annuelle, unique).

| Méthode | Route                        | Description                              | Rôle requis  |
|---------|------------------------------|------------------------------------------|--------------|
| GET     | `/cotisation-plans`          | Liste des plans (actifs par défaut)      | Authentifié  |
| POST    | `/cotisation-plans`          | Créer un plan                            | treasurer+   |
| PATCH   | `/cotisation-plans/{id}`     | Modifier un plan                         | treasurer+   |

### Paiements

| Méthode | Route                 | Description                                          | Rôle requis  |
|---------|-----------------------|------------------------------------------------------|--------------|
| GET     | `/payments`           | Liste paginée (filtres : membre, année, mois, statut)| treasurer+   |
| POST    | `/payments`           | Enregistrer un paiement                              | treasurer+   |
| GET     | `/payments/{id}`      | Détail d'un paiement                                 | treasurer+   |
| PATCH   | `/payments/{id}`      | Modifier statut/notes/référence                      | treasurer+   |
| DELETE  | `/payments/{id}`      | Annuler (passe à `cancelled`)                        | super_admin  |

**Comportement spécial** : quand un paiement est enregistré pour un membre `inactive`, ce dernier est automatiquement remis à `active`.

### Dashboard trésorier

`GET /dashboard/treasurer` retourne en une seule requête :

- Nombre total de membres / membres actifs
- Nombre de membres ayant payé ce mois / n'ayant pas payé
- Revenus du mois courant et depuis le début de l'année (YTD)
- Nombre de paiements en attente (`pending`)

### Grille mensuelle

`GET /payments/grid?year=2026` — vue calendrier 12 colonnes × N membres.  
Chaque cellule indique le statut du paiement pour ce mois (`none`, `pending`, `confirmed`, `cancelled`).

### Export CSV

`GET /payments/export?year=2026` — télécharge un fichier `.csv` de tous les paiements confirmés, compatible Excel (encodage UTF-8 BOM).

---

## Module 4 — Événements (`/events`)

| Méthode | Route                                       | Description                                        | Rôle requis   |
|---------|---------------------------------------------|----------------------------------------------------|---------------|
| GET     | `/events`                                   | Liste (filtres : upcoming, statut)                 | Authentifié   |
| POST    | `/events`                                   | Créer un événement (statut `draft` par défaut)     | secretary+    |
| GET     | `/events/{id}`                              | Détail + nombre d'inscrits                         | Authentifié   |
| PATCH   | `/events/{id}`                              | Modifier (impossible si `cancelled`)               | secretary+    |
| DELETE  | `/events/{id}`                              | Annuler l'événement                                | super_admin   |
| POST    | `/events/{id}/registrations`                | Inscrire un membre                                 | Authentifié   |
| GET     | `/events/{id}/registrations`                | Liste des inscrits                                 | secretary+    |
| POST    | `/events/{id}/registrations/{reg_id}/checkin` | Marquer un membre comme présent                | secretary+    |
| GET     | `/events/{id}/attendance`                   | Rapport de présence (inscrits / présents / %)      | secretary+    |

### Comportements notables

- Un événement ne peut pas être modifié s'il est annulé.
- La capacité est vérifiée à l'inscription — si l'événement est complet, l'inscription est refusée.
- Le rapport de présence calcule automatiquement le taux de participation.

---

## Module 5 — Notifications (`/notifications`)

Envoi manuel d'emails et historique.

| Méthode | Route                                    | Description                                          | Rôle requis  |
|---------|------------------------------------------|------------------------------------------------------|--------------|
| GET     | `/notifications`                         | Historique (filtres : membre, envoyé/non)            | Authentifié  |
| POST    | `/notifications/welcome/{member_id}`     | Renvoyer l'email de bienvenue                        | secretary+   |
| POST    | `/notifications/remind-overdue`          | Envoyer rappels aux membres sans paiement ce mois    | treasurer+   |
| POST    | `/notifications/event-invite/{event_id}` | Inviter tous les membres actifs à un événement       | secretary+   |

Chaque envoi retourne un résumé : `{ targeted, sent, failed, skipped }`.

---

## Infrastructure transversale

### Sécurité

- **Mots de passe** : hachés en bcrypt (algorithme à sens unique — impossible de retrouver le mot de passe original).
- **Tokens JWT** : signés avec une clé secrète `SECRET_KEY`. Contiennent l'ID du membre et ses rôles.
- **Comptes suspendus** : bloqués à chaque requête, même avec un token valide.

### Contrôle des rôles (RBAC)

Hiérarchie des droits :

```
super_admin  ←  accès total
  treasurer  ←  finances + dashboard
  secretary  ←  membres + événements + notifications
     member  ←  lecture seule (son propre profil, événements)
```

Un `super_admin` a automatiquement accès à tout ce que peuvent faire `treasurer` et `secretary`.

### Tâches planifiées

Un **scheduler** (APScheduler) tourne en arrière-plan dans le même processus que l'API :

- **Rappels cotisations** : le `REMINDER_DAY` du mois à `REMINDER_HOUR`h UTC, un email est envoyé automatiquement à tous les membres actifs n'ayant pas de paiement confirmé pour le mois courant.
- Tolère 1h de retard (si le serveur redémarre au mauvais moment).

### Emails (Brevo)

Trois types d'emails avec template HTML :
1. **Bienvenue** — à la création d'un compte
2. **Rappel cotisation** — mois + montant dû
3. **Invitation événement** — titre, date, lieu

Si `BREVO_API_KEY` n'est pas configuré, les envois échouent silencieusement (non bloquant).

### Journal d'audit

Toute modification importante (création/modification/suppression d'un membre, changement de statut) est enregistrée dans `audit_logs` avec :
- L'ID de l'acteur (qui a fait l'action)
- L'action (`member.create`, `member.update`, etc.)
- Un diff JSON `{ "before": {...}, "after": {...} }`

---

## Tests

`tests/test_smoke.py` — vérifications de bon fonctionnement sans base de données :

- `/health` répond 200
- `/docs` est accessible
- Une tentative de login avec des données invalides retourne 422
- Les routes protégées refusent les requêtes sans token valide

---

## Variables d'environnement requises (`.env`)

```env
DATABASE_URL=postgresql+psycopg2://user:pass@host/dbname
SECRET_KEY=une-clé-secrète-longue-et-aléatoire
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
BREVO_API_KEY=xkeysib-...          # optionnel
EMAIL_FROM=contact@association.fr  # optionnel
REMINDER_DAY=5                     # 5e jour du mois
REMINDER_HOUR=8                    # 8h UTC
ALLOWED_ORIGINS=["http://localhost:3000"]
```
