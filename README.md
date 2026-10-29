# Malewa back-office

Webapp interne de Malewa Sàrl : gestion des demandes, puis devis, acomptes et paiements.
Accès privé, sur invitation uniquement (3 comptes).

## État de la v1 (étape 4)

- Connexion avec Supabase Auth (e-mail et mot de passe)
- Rôles : `admin` (modifie), `lecture` (consulte)
- Demandes : liste filtrable, fiche, création, modification, changement de statut
- Alerte « date déjà prise » (anti-doubles réservations)
- Devis : formulaire avec calculs en direct, TVA en option, services au tarif horaire ou au forfait, échéancier, texte d'introduction à cocher, fiche et modification
- PDF du devis en 3 pages (lettre, détail, paiement), téléchargeable depuis la fiche du devis
- Mode démo avec données fictives
- Stratégie : plan d'actions 2027, pistes (festivals, wedding planners, salons, entreprises), suivi KPI en direct depuis les devis, journal de ce qui est entrepris, lien demande vers piste, coûts par événement, bilan et frais d'inscription par piste, charges fixes et seuil de rentabilité, rappels « À compléter »

## Stack

- Python, Flask
- Supabase : base PostgreSQL, authentification, règles d'accès par ligne (RLS)
- Render : hébergement

## Fichiers

| Fichier | Rôle |
|---|---|
| `app.py` | Pages, sécurité, règles de l'app |
| `donnees_supabase.py` | Échanges avec la base Supabase |
| `donnees_demo.py` | Données fictives pour tester sans base |
| `calcul.py` | Calculs du devis (lignes, TVA, acomptes), avec des Decimal pour des montants exacts |
| `pdf_devis.py` | PDF du devis en 3 pages (ReportLab, sans programme système), polices dans `polices/` |
| `strategie.py` | Listes de choix et calcul des KPI (demandes, devis, CA par axe, origine) |
| `strategie_donnees.json` | Plan d'actions et pistes de l'Excel, utilisés par le mode démo |
| `phrases.py` | Phrases proposées pour la lettre du devis |
| `templates/` | Pages HTML |
| `static/` | Style, logo, polices (hébergées ici, aucun service externe) |

## Tester en local, sans Supabase

```bash
pip install -r requirements.txt
DEMO_MODE=1 python app.py
```

Ouvrir http://localhost:5000, puis se connecter avec :

- `admin@malewa.demo` (modification) ou `lecture@malewa.demo` (consultation)
- mot de passe `Demo-1234`

## Variables d'environnement

| Nom | Valeur |
|---|---|
| `SUPABASE_URL` | Adresse du projet (Supabase, Project Settings, API) |
| `SUPABASE_KEY` | Clé **publique** (publishable ou anon). Jamais la clé secrète ni `service_role`. |
| `SECRET_KEY` | Longue suite aléatoire qui signe les sessions |

Elles se saisissent dans Render (Environment). Aucun secret n'est écrit dans le dépôt.

## Mise en ligne sur Render

1. New, Web Service, relier le dépôt GitHub `malewa-backoffice`.
2. Region : Frankfurt (Europe).
3. Build Command : `pip install -r requirements.txt`
4. Start Command : `gunicorn app:app`
5. Environment : ajouter `SUPABASE_URL`, `SUPABASE_KEY`, `SECRET_KEY`, et `PYTHON_VERSION` = `3.12.7`.
6. Health Check Path : `/sante`

Plan gratuit : le service se met en veille après une période d'inactivité, et le premier chargement est alors plus lent.

## Sécurité

- Les requêtes à la base portent l'identité de la personne : la base applique elle-même les droits (RLS).
- Cookie de session HTTPS, non lisible par le JavaScript, durée de 8 h.
- Jeton anti-falsification (CSRF) sur tous les formulaires.
- Pages non indexables, aucun cache des données client.
- Rôle `lecture` : boutons masqués et actions refusées par l'app et par la base.

## Suite prévue

acomptes, calendrier, dépenses et remboursements, tâches de préparation.
