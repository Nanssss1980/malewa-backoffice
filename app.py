"""Malewa back-office : application Flask (connexion et gestion des demandes)."""  # description du fichier
import os  # accès aux variables d'environnement
import time  # horodatage pour l'expiration de la session
import secrets  # génération et comparaison sûres du jeton anti-falsification (CSRF)
import datetime  # lecture et formatage des dates
import logging  # journal des erreurs côté serveur
from functools import wraps  # conserve le nom des fonctions décorées
from decimal import Decimal  # montants exacts
import strategie  # listes de choix et calculs de la stratégie (KPI)
import uuid  # contrôle des identifiants de piste
import calcul  # calculs du devis (lignes, TVA, acomptes)
import phrases  # phrases proposées pour la lettre du devis
import pdf_devis  # fabrication du PDF du devis
import re  # nettoyage du nom de fichier
from flask import Flask, render_template, request, redirect, url_for, session, abort, flash, Response  # outils Flask

MODE_DEMO = os.environ.get("DEMO_MODE") == "1"  # vrai pour tester avec des données fictives
if MODE_DEMO:  # version de démonstration
    from donnees_demo import Donnees  # données fictives en mémoire
else:  # version réelle
    from donnees_supabase import Donnees  # base Supabase

app = Flask(__name__)  # crée l'application
cle_secrete = os.environ.get("SECRET_KEY")  # clé qui signe le cookie de session
if not cle_secrete:  # clé absente
    if not MODE_DEMO:  # en production, c'est une erreur grave
        raise RuntimeError("SECRET_KEY manquante : définis-la dans les variables d'environnement")  # arrêt volontaire
    cle_secrete = "cle-de-demo-locale"  # valeur de démonstration, jamais utilisée en ligne
app.config.update(  # réglages de sécurité du cookie de session
    SECRET_KEY=cle_secrete,  # clé de signature
    SESSION_COOKIE_HTTPONLY=True,  # le cookie n'est pas lisible par le JavaScript
    SESSION_COOKIE_SECURE=not MODE_DEMO,  # envoyé uniquement en HTTPS (hors démo locale)
    SESSION_COOKIE_SAMESITE="Lax",  # protège contre les envois depuis d'autres sites
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=8),  # déconnexion automatique après 8 h
)
db = Donnees()  # accès aux données
app.jinja_env.globals["pistes_choix"] = lambda: db.pistes(session["utilisateur"]["jeton"])  # liste des pistes pour le formulaire de demande

STATUTS = [  # étapes d'une demande : code, libellé affiché
    ("nouvelle", "Nouvelle"), ("en_discussion", "En discussion"), ("devis_envoye", "Devis envoyé"),
    ("accepte", "Accepté"), ("acompte_recu", "Acompte reçu"), ("refuse", "Refusé"), ("annule", "Annulé"),
]
LIBELLE_STATUT = dict(STATUTS)  # code vers libellé
SOURCES = [("site", "Site web"), ("whatsapp", "WhatsApp"), ("telephone", "Téléphone"), ("email", "E-mail"), ("autre", "Autre")]  # origines possibles
ORIGINES = [("", "Non précisé"), ("google", "Google"), ("instagram", "Instagram"), ("recommandation", "Recommandation"), ("festival", "Festival"), ("mariage", "Mariage auquel j'ai assisté"), ("autre", "Autre")]  # comment le client a connu Malewa (liste fermée pour comparer les réponses)
TYPES = [("mariage", "Mariage"), ("evenement_prive", "Événement privé"), ("evenement_entreprise", "Événement d'entreprise"), ("festival", "Festival"), ("autre", "Autre")]  # types d'événement
CONTACTS = [("", "Non précisé"), ("email", "E-mail"), ("whatsapp", "WhatsApp"), ("telephone", "Téléphone")]  # canaux préférés
CIVILITES = {"": ("Madame, Monsieur,", ""), "madame": ("Chère Madame,", "Madame"), "monsieur": ("Cher Monsieur,", "Monsieur"), "couple": ("Chère Madame, cher Monsieur,", "Madame et Monsieur")}  # civilité : formule d'appel, titre dans l'adresse
CIVILITE_CHOIX = [("", "Non précisé"), ("madame", "Madame"), ("monsieur", "Monsieur"), ("couple", "Madame et Monsieur")]  # choix proposés dans le formulaire
STATUTS_DEVIS_CHOIX = ("brouillon", "envoye", "accepte", "refuse")  # statuts qu'on peut choisir à la main
AVANCE_DEMANDE = {"envoye": ("devis_envoye", ("nouvelle", "en_discussion")), "accepte": ("accepte", ("nouvelle", "en_discussion", "devis_envoye"))}  # un devis envoyé ou accepté fait avancer la demande (jamais reculer)
STATUTS_DEVIS = {"brouillon": "Brouillon", "envoye": "Envoyé", "accepte": "Accepté", "refuse": "Refusé", "remplace": "Remplacé"}  # statuts autorisés pour un devis
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]  # mois en français


# ---------------------------------------------------------------- filtres d'affichage
@app.template_filter("date_fr")  # filtre utilisable dans les modèles : {{ date|date_fr }}
def date_fr(valeur):  # 2027-06-19 devient 19 juin 2027
    if not valeur:  # pas de date
        return "Date à préciser"  # texte de remplacement
    try:  # lecture de la date
        jour = datetime.date.fromisoformat(str(valeur)[:10])  # garde les 10 premiers caractères
    except ValueError:  # format inattendu
        return str(valeur)  # affiche tel quel
    return f"{jour.day} {MOIS[jour.month - 1]} {jour.year}"  # date lisible


@app.template_filter("chf")  # filtre pour les montants : {{ montant|chf }}
def chf(valeur):  # 12000 devient CHF 12'000
    if valeur is None or valeur == "":  # pas de montant
        return "Non indiqué"  # texte de remplacement
    return "CHF " + f"{float(valeur):,.0f}".replace(",", "'")  # apostrophe suisse pour les milliers


@app.template_filter("chf2")  # filtre pour les montants du devis, avec centimes : {{ montant|chf2 }}
def chf2(valeur):  # 1234.5 devient CHF 1'234.50
    if valeur is None or valeur == "":  # pas de montant
        return ""  # rien à afficher
    return "CHF " + f"{float(valeur):,.2f}".replace(",", "'")  # apostrophe suisse pour les milliers


@app.template_filter("pct")  # filtre pour les pourcentages : {{ 62.5|pct }}
def pct(valeur):  # 62.5 devient 63 %
    if valeur is None or valeur == "":  # pas de valeur
        return ""  # rien à afficher
    return f"{float(valeur):.0f} %"  # arrondi à l'entier


@app.template_filter("saisie")  # filtre pour préremplir un champ de montant : 60000.0 devient 60000
def saisie(valeur):  # écriture sans zéros inutiles
    if valeur is None or valeur == "":  # pas de valeur
        return ""  # champ vide
    return f"{float(valeur):.2f}".rstrip("0").rstrip(".")  # 1200.50 devient 1200.5


@app.template_filter("nom_client")  # filtre : nom affichable du client
def nom_client(client):  # prénom + nom, ou entreprise
    if not client:  # pas de client
        return ""  # rien à afficher
    if client.get("entreprise"):  # client professionnel
        return client["entreprise"]  # nom de l'entreprise
    return " ".join(filter(None, [client.get("prenom"), client.get("nom")]))  # prénom et nom


# ---------------------------------------------------------------- sécurité
@app.context_processor  # variables disponibles dans tous les modèles
def variables_communes():  # définit ces variables
    if "_csrf" not in session:  # première visite
        session["_csrf"] = secrets.token_hex(16)  # crée un jeton anti-falsification
    return {"csrf_token": session["_csrf"], "utilisateur": session.get("utilisateur"), "LIBELLE_STATUT": LIBELLE_STATUT, "STATUTS_DEVIS": STATUTS_DEVIS, "MODE_DEMO": MODE_DEMO, "ORIGINES": ORIGINES, "LIBELLE_ORIGINE": dict(ORIGINES), "LIBELLE_AXE": strategie.LIBELLE_AXE, "LIBELLE_STATUT_ACTION": strategie.LIBELLE_STATUT_ACTION, "LIBELLE_STATUT_PISTE": strategie.LIBELLE_STATUT_PISTE, "LIBELLE_CATEGORIE": strategie.LIBELLE_CATEGORIE, "LIBELLE_DOSSIER": strategie.LIBELLE_DOSSIER}  # variables partagées


@app.before_request  # exécuté avant chaque requête
def verifier_csrf():  # bloque les envois de formulaires falsifiés
    if request.method == "POST":  # seuls les envois de formulaire sont concernés
        envoye = request.form.get("_csrf", "")  # jeton reçu avec le formulaire
        attendu = session.get("_csrf", "")  # jeton attendu
        if not attendu or not secrets.compare_digest(envoye, attendu):  # comparaison sûre
            abort(400)  # requête refusée


@app.after_request  # exécuté après chaque réponse
def entetes_securite(reponse):  # ajoute des en-têtes de sécurité
    reponse.headers["X-Robots-Tag"] = "noindex, nofollow"  # interdit l'indexation par les moteurs de recherche
    reponse.headers["X-Frame-Options"] = "DENY"  # interdit d'afficher l'app dans un cadre d'un autre site
    reponse.headers["X-Content-Type-Options"] = "nosniff"  # empêche le navigateur de deviner les types de fichiers
    reponse.headers["Referrer-Policy"] = "same-origin"  # ne communique pas l'adresse à d'autres sites
    reponse.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; frame-ancestors 'none'"  # n'autorise que les ressources de l'app
    reponse.headers["Cache-Control"] = "no-store"  # évite que des données client restent en cache
    return reponse  # renvoie la réponse modifiée


def session_valide():  # vérifie que la personne est connectée et renouvelle son jeton si besoin
    utilisateur = session.get("utilisateur")  # informations de session
    if not utilisateur:  # personne de connecté
        return False  # accès refusé
    if time.time() < utilisateur["expire"] - 60:  # jeton encore valable
        return True  # tout va bien
    try:  # jeton expiré : tentative de renouvellement
        utilisateur.update(db.rafraichir(utilisateur["refresh"]))  # nouveau jeton
        session["utilisateur"] = utilisateur  # enregistre la session mise à jour
        return True  # accès maintenu
    except Exception:  # renouvellement impossible
        session.clear()  # déconnecte
        return False  # accès refusé


def connexion_requise(fonction):  # décorateur : page réservée aux personnes connectées
    @wraps(fonction)  # conserve le nom de la fonction
    def enveloppe(*args, **kwargs):  # remplace la fonction d'origine
        if not session_valide():  # pas connecté
            return redirect(url_for("connexion"))  # renvoie vers la page de connexion
        return fonction(*args, **kwargs)  # exécute la page
    return enveloppe  # renvoie la fonction protégée


def admin_requis(fonction):  # décorateur : action réservée aux admins
    @wraps(fonction)  # conserve le nom de la fonction
    @connexion_requise  # impose d'abord la connexion
    def enveloppe(*args, **kwargs):  # remplace la fonction d'origine
        if session["utilisateur"]["role"] != "admin":  # rôle lecture
            abort(403)  # interdit : la base refuserait aussi
        return fonction(*args, **kwargs)  # exécute l'action
    return enveloppe  # renvoie la fonction protégée


def jeton():  # jeton de la personne connectée, transmis à la base
    return session["utilisateur"]["jeton"]  # jeton d'accès


# ---------------------------------------------------------------- lecture des formulaires
def texte(form, nom):  # lit un champ texte, renvoie None s'il est vide
    valeur = (form.get(nom) or "").strip()  # retire les espaces autour
    return valeur or None  # None si vide


def entier(form, nom, erreurs, libelle):  # lit un nombre entier positif ou nul
    brut = (form.get(nom) or "").strip()  # texte saisi
    if not brut:  # champ vide
        return 0  # valeur par défaut
    try:  # conversion
        nombre = int(brut)  # texte vers entier
    except ValueError:  # pas un nombre
        erreurs.append(f"{libelle} : nombre entier attendu.")  # message d'erreur
        return 0  # valeur de repli
    if nombre < 0:  # nombre négatif
        erreurs.append(f"{libelle} : le nombre ne peut pas être négatif.")  # message d'erreur
        return 0  # valeur de repli
    return nombre  # nombre valide


def lire_formulaire(form):  # transforme le formulaire en client + demande, avec la liste des erreurs
    erreurs = []  # messages à afficher
    client = {  # champs de la fiche client
        "prenom": texte(form, "client_prenom"), "nom": texte(form, "client_nom"), "entreprise": texte(form, "client_entreprise"),
        "email": texte(form, "client_email"), "telephone": texte(form, "client_telephone"),
        "contact_prefere": texte(form, "client_contact_prefere"), "email_invalide": form.get("client_email_invalide") == "on",
        "adresse": texte(form, "client_adresse"), "code_postal": texte(form, "client_code_postal"), "ville": texte(form, "client_ville"),
    }
    if not client["nom"]:  # nom obligatoire
        erreurs.append("Le nom du client est obligatoire.")  # message d'erreur
    date_evenement = texte(form, "date_evenement")  # date saisie
    if date_evenement:  # si une date est saisie
        try:  # vérifie le format
            datetime.date.fromisoformat(date_evenement)  # lève une erreur si invalide
        except ValueError:  # date invalide
            erreurs.append("La date de l'événement n'est pas valide.")  # message d'erreur
    budget = texte(form, "budget_indique")  # budget saisi
    if budget:  # si un budget est saisi
        try:  # conversion en nombre
            budget = round(float(budget.replace("'", "").replace(",", ".")), 2)  # accepte 12'000 et 12000,50
        except ValueError:  # pas un nombre
            erreurs.append("Le budget doit être un nombre.")  # message d'erreur
            budget = None  # valeur de repli
    source = form.get("source", "autre")  # origine de la demande
    origine = form.get("origine", "")  # comment le client a connu Malewa
    genre = form.get("type_evenement", "autre")  # type d'événement
    cout_total = nombre_saisi(form.get("cout_total"), erreurs, "Autres coûts de l'événement")  # coûts réels hors équipe (facultatif)
    cout_equipe = nombre_saisi(form.get("cout_equipe"), erreurs, "Salaires et équipe")  # salaires et extras de l'événement (facultatif)
    piste_id = texte(form, "piste_id")  # piste d'où vient la demande (facultatif)
    if piste_id:  # un identifiant a été choisi
        try:  # doit être un identifiant valide
            uuid.UUID(piste_id)  # lève une erreur sinon
        except ValueError:  # valeur inattendue
            abort(400)  # requête refusée
    if source not in dict(SOURCES) or genre not in dict(TYPES) or origine not in dict(ORIGINES):  # valeurs inattendues
        abort(400)  # requête refusée
    demande = {  # champs de la demande
        "titre": texte(form, "titre") or "Demande sans titre", "source": source, "origine": origine or None, "piste_id": piste_id, "cout_total": cout_total, "cout_equipe": cout_equipe, "type_evenement": genre,
        "date_evenement": date_evenement, "horaire": texte(form, "horaire"), "lieu": texte(form, "lieu"),
        "adultes": entier(form, "adultes", erreurs, "Adultes"), "enfants": entier(form, "enfants", erreurs, "Enfants"),
        "budget_indique": budget or None, "message_client": texte(form, "message_client"), "notes_internes": texte(form, "notes_internes"),
    }
    return client, demande, erreurs  # renvoie les trois résultats


def aplatir(demande):  # transforme une demande en valeurs de formulaire (pour la modification)
    valeurs = {cle: ("" if valeur is None else valeur) for cle, valeur in demande.items() if cle != "clients"}  # champs de la demande
    for cle, valeur in (demande.get("clients") or {}).items():  # champs du client
        valeurs["client_" + cle] = "" if valeur is None else valeur  # préfixe client_
    return valeurs  # dictionnaire à plat


# ---------------------------------------------------------------- pages
@app.route("/connexion", methods=["GET", "POST"])  # page de connexion
def connexion():  # affiche et traite la connexion
    if request.method == "POST":  # formulaire envoyé
        email = (request.form.get("email") or "").strip().lower()  # adresse saisie
        mot_de_passe = request.form.get("mot_de_passe") or ""  # mot de passe saisi
        try:  # tentative de connexion
            infos = db.connexion(email, mot_de_passe)  # vérifie auprès de Supabase
            profil = db.profil(infos["jeton"], infos["id"])  # lit le rôle dans la table profils
        except ValueError:  # identifiants refusés
            flash("E-mail ou mot de passe incorrect.", "erreur")  # message volontairement vague
            return render_template("connexion.html"), 401  # réaffiche la page
        if not profil:  # compte sans profil : pas de droits
            flash("Ce compte n'a pas encore d'accès à l'application.", "erreur")  # message clair
            return render_template("connexion.html"), 403  # accès refusé
        session.clear()  # nouvelle session propre (évite la fixation de session)
        session["_csrf"] = secrets.token_hex(16)  # nouveau jeton anti-falsification
        session.permanent = True  # applique la durée de 8 h
        session["utilisateur"] = {**infos, "nom": profil["nom"], "role": profil["role"]}  # mémorise la personne
        return redirect(url_for("liste_demandes"))  # va à la liste des demandes
    return render_template("connexion.html")  # affiche le formulaire


@app.route("/deconnexion", methods=["POST"])  # déconnexion (par formulaire, pour la sécurité)
def deconnexion():  # vide la session
    session.clear()  # supprime les informations de connexion
    return redirect(url_for("connexion"))  # retour à la connexion


MOT_DE_PASSE_MIN = 12  # longueur minimale d'un mot de passe


@app.route("/mot-de-passe", methods=["GET", "POST"])  # changer son propre mot de passe
@connexion_requise  # toute personne connectée, admin ou lecture
def changer_mot_de_passe():  # affiche et traite le formulaire
    if request.method == "POST":  # formulaire envoyé
        actuel = request.form.get("actuel") or ""  # mot de passe actuel
        nouveau = request.form.get("nouveau") or ""  # nouveau mot de passe
        confirmation = request.form.get("confirmation") or ""  # nouveau mot de passe retapé
        erreur = None  # message d'erreur éventuel
        if len(nouveau) < MOT_DE_PASSE_MIN:  # trop court
            erreur = f"Le nouveau mot de passe doit faire au moins {MOT_DE_PASSE_MIN} caractères."  # explication
        elif nouveau != confirmation:  # les deux saisies diffèrent
            erreur = "Les deux nouveaux mots de passe ne sont pas identiques."  # explication
        elif nouveau == actuel:  # aucun changement
            erreur = "Le nouveau mot de passe doit être différent de l'actuel."  # explication
        if not erreur:  # saisie correcte : tentative de changement
            try:  # appel à la base
                db.changer_mot_de_passe(session["utilisateur"]["email"], actuel, nouveau)  # vérifie l'ancien puis enregistre
            except ValueError:  # ancien mot de passe faux
                erreur = "Le mot de passe actuel est incorrect."  # explication
            except Exception:  # refus de Supabase (mot de passe trop faible, service indisponible)
                erreur = "Le changement a échoué. Essayez un mot de passe plus long ou plus varié."  # explication
        if erreur:  # affiche l'erreur sans rien enregistrer
            flash(erreur, "erreur")  # message à l'écran
            return render_template("mot_de_passe.html", minimum=MOT_DE_PASSE_MIN), 400  # réaffiche le formulaire
        flash("Mot de passe modifié.", "ok")  # confirmation
        return redirect(url_for("liste_demandes"))  # retour à la liste des demandes
    return render_template("mot_de_passe.html", minimum=MOT_DE_PASSE_MIN)  # affiche le formulaire


@app.route("/")  # page d'accueil
@connexion_requise  # réservée aux personnes connectées
def accueil():  # redirige vers les demandes
    return redirect(url_for("liste_demandes"))  # liste des demandes


@app.route("/demandes")  # liste des demandes
@connexion_requise  # réservée aux personnes connectées
def liste_demandes():  # affiche la liste, filtrable par statut
    statut = request.args.get("statut")  # filtre choisi
    if statut and statut not in LIBELLE_STATUT:  # valeur inattendue
        abort(400)  # requête refusée
    demandes = db.liste_demandes(jeton(), statut)  # lit les demandes
    for demande in demandes:  # repère les doubles réservations
        demande["conflits"] = [] if demande["statut"] in ("refuse", "annule") else db.dates_prises(jeton(), demande["date_evenement"], demande["id"])  # autres demandes actives le même jour (inutile pour une demande refusée ou annulée)
    return render_template("demandes.html", demandes=demandes, statut=statut, statuts=STATUTS, types=dict(TYPES))  # affiche la page


@app.route("/demandes/nouvelle", methods=["GET", "POST"])  # création d'une demande
@admin_requis  # réservée aux admins
def nouvelle_demande():  # affiche et traite le formulaire de création
    if request.method == "POST":  # formulaire envoyé
        client, demande, erreurs = lire_formulaire(request.form)  # lit et vérifie les champs
        if erreurs:  # des erreurs à corriger
            return render_template("demande_form.html", valeurs=request.form, erreurs=erreurs, sources=SOURCES, types=TYPES, contacts=CONTACTS, titre_page="Nouvelle demande", edition=False), 422  # réaffiche le formulaire
        demande["statut"] = "nouvelle"  # étape de départ
        identifiant = db.creer_demande(jeton(), client, demande)  # enregistre
        flash("Demande créée.", "ok")  # confirmation
        return redirect(url_for("fiche_demande", identifiant=identifiant))  # va à la fiche
    return render_template("demande_form.html", valeurs={"source": "whatsapp", "type_evenement": "mariage"}, erreurs=[], sources=SOURCES, types=TYPES, contacts=CONTACTS, titre_page="Nouvelle demande", edition=False)  # formulaire vide


@app.route("/demandes/<identifiant>")  # fiche d'une demande
@connexion_requise  # réservée aux personnes connectées
def fiche_demande(identifiant):  # affiche la fiche
    demande = db.demande(jeton(), identifiant)  # lit la demande
    if not demande:  # introuvable
        abort(404)  # page introuvable
    conflits = db.dates_prises(jeton(), demande["date_evenement"], identifiant)  # autres demandes actives le même jour
    piste = db.piste(jeton(), demande.get("piste_id"))  # piste d'où vient la demande (si renseignée)
    devis_liste = db.devis_de_demande(jeton(), identifiant)  # devis de la demande
    ca_signe = sum((strategie.montant(d.get("total_ht")) for d in devis_liste if d["statut"] == "accepte"), Decimal("0"))  # CA hors taxes des devis acceptés
    couts = strategie.couts_demande(demande)  # coûts totaux : équipe + autres coûts (None si rien n'est saisi)
    marge = (ca_signe - couts) if ca_signe and couts is not None else None  # marge, seulement si un devis est accepté et les coûts saisis
    return render_template("demande_fiche.html", ca_signe=ca_signe, marge=marge, couts=couts, piste=piste, demande=demande, conflits=conflits, statuts=STATUTS, types=dict(TYPES), sources=dict(SOURCES), devis_liste=devis_liste)  # affiche la page


@app.route("/demandes/<identifiant>/modifier", methods=["GET", "POST"])  # modification d'une demande
@admin_requis  # réservée aux admins
def modifier_demande(identifiant):  # affiche et traite le formulaire de modification
    demande = db.demande(jeton(), identifiant)  # lit la demande actuelle
    if not demande:  # introuvable
        abort(404)  # page introuvable
    if request.method == "POST":  # formulaire envoyé
        client, nouvelle, erreurs = lire_formulaire(request.form)  # lit et vérifie les champs
        if erreurs:  # des erreurs à corriger
            return render_template("demande_form.html", valeurs=request.form, erreurs=erreurs, sources=SOURCES, types=TYPES, contacts=CONTACTS, titre_page="Modifier la demande", edition=True, identifiant=identifiant), 422  # réaffiche le formulaire
        db.modifier_demande(jeton(), identifiant, demande["client_id"], client, nouvelle)  # enregistre
        flash("Demande mise à jour.", "ok")  # confirmation
        return redirect(url_for("fiche_demande", identifiant=identifiant))  # retour à la fiche
    return render_template("demande_form.html", valeurs=aplatir(demande), erreurs=[], sources=SOURCES, types=TYPES, contacts=CONTACTS, titre_page="Modifier la demande", edition=True, identifiant=identifiant)  # formulaire prérempli


@app.route("/demandes/<identifiant>/statut", methods=["POST"])  # changement d'étape
@admin_requis  # réservée aux admins
def changer_statut(identifiant):  # enregistre le nouveau statut
    statut = request.form.get("statut", "")  # étape choisie
    if statut not in LIBELLE_STATUT:  # valeur inattendue
        abort(400)  # requête refusée
    if not db.demande(jeton(), identifiant):  # demande introuvable
        abort(404)  # page introuvable
    db.changer_statut(jeton(), identifiant, statut)  # écrit le statut
    flash(f"Statut : {LIBELLE_STATUT[statut]}.", "ok")  # confirmation
    return redirect(url_for("fiche_demande", identifiant=identifiant))  # retour à la fiche


# ---------------------------------------------------------------- devis
def nombre_texte(valeur):  # 35.0 devient "35", 8.10 devient "8.1" (pour préremplir les champs)
    if valeur is None or valeur == "":  # rien à écrire
        return ""  # champ vide
    return calcul.propre(Decimal(str(valeur)))  # écriture sans zéros inutiles


def valeurs_initiales(demande, reglages):  # valeurs proposées à l'ouverture d'un nouveau devis
    return {
        "titre": demande["titre"], "civilite": "", "formule_appel": "Madame, Monsieur,", "adultes": demande["adultes"], "enfants": demande["enfants"],
        "forfait_libelle": "Forfait nourriture et boissons", "forfait_nourriture": "", "menu_texte": "",
        "tarif_h": nombre_texte(reglages.get("tarif_horaire", 35)), "tarif_hn": nombre_texte(reglages.get("tarif_horaire_nuit", 42)),
        "s1_libelle": "Service apéritif", "s1_pers": "", "s1_h": "", "s1_hn": "", "s1_forfait": "",
        "s2_libelle": "Service buffet et dessert", "s2_pers": "", "s2_h": "", "s2_hn": "", "s2_forfait": "",
        "debarras": "350", "km": "", "vehicules": "1", "tarif_km": nombre_texte(reglages.get("tarif_km", 1.2)),
        "tva_on": "", "taux_tva": nombre_texte(reglages.get("taux_tva", 8.1)), "validite": reglages.get("validite_jours", 14),
        "p1": nombre_texte(reglages.get("pourcentage_acompte_1", 10)), "p2": nombre_texte(reglages.get("pourcentage_acompte_2", 60)),
        "phrase_a": "on", "phrase_b": "on", "phrase_c": "on", "cgv": "", "libre": "", "affichage_prix": "total",
    }  # valeurs de départ


def phrases_du_devis(demande, valeurs):  # phrases proposées, avec les chiffres du devis
    fiche = {**demande, "date_evenement_fr": date_fr(demande["date_evenement"]) if demande.get("date_evenement") else None}  # date lisible
    erreurs = []  # inutilisé ici
    adultes = calcul.dec(valeurs.get("adultes"), "Adultes", erreurs)  # adultes
    enfants = calcul.dec(valeurs.get("enfants"), "Enfants", erreurs)  # enfants
    personnes = adultes + enfants / 2  # enfant = demi-tête
    return phrases.liste(fiche, calcul.propre(adultes), calcul.propre(enfants), calcul.propre(personnes))  # liste des phrases


def lire_devis(form, demande):  # transforme le formulaire en devis + lignes, avec la liste des erreurs
    resultat, erreurs = calcul.calculer(form)  # calcule lignes, totaux et acomptes
    civilite = form.get("civilite", "")  # civilité du client
    if civilite not in CIVILITES:  # valeur inattendue
        abort(400)  # requête refusée
    if form.get("affichage_prix", "total") not in ("total", "par_personne"):  # valeur inattendue
        abort(400)  # requête refusée
    titre = texte(form, "titre")  # titre du devis
    if not titre:  # obligatoire
        erreurs.append("Le titre du devis est obligatoire.")  # message d'erreur
    adultes = entier(form, "adultes", erreurs, "Adultes")  # adultes (entier)
    enfants = entier(form, "enfants", erreurs, "Enfants")  # enfants (entier)
    validite = entier(form, "validite", erreurs, "Validité")  # jours de validité
    choisies = [t for identifiant, t, _ in phrases_du_devis(demande, form) if form.get("phrase_" + identifiant) == "on"]  # phrases cochées
    if form.get("cgv") == "on":  # CGV jointes
        choisies.append(phrases.PHRASE_CGV)  # phrase automatique
    if texte(form, "libre"):  # ligne libre
        choisies.append(texte(form, "libre"))  # ajoutée à la fin
    devis = {
        "titre": titre or "", "formule_appel": texte(form, "formule_appel") or CIVILITES[civilite][0], "adultes": adultes, "enfants": enfants,
        "introduction_texte": "\n".join(choisies) or None, "menu_texte": texte(form, "menu_texte"),
        "soumis_tva": resultat["soumis_tva"], "taux_tva": resultat["taux_tva"], "validite_jours": validite,
        "pourcentage_acompte_1": resultat["p1"], "pourcentage_acompte_2": resultat["p2"], "cgv_jointes": form.get("cgv") == "on",
        "total_ht": resultat["total_ht"], "montant_tva": resultat["montant_tva"], "total_ttc": resultat["total_ttc"],
        "saisie": {cle: valeur for cle, valeur in form.items() if cle != "_csrf"},  # saisie brute, pour rouvrir le devis tel quel
    }  # champs de la table devis
    return devis, resultat["lignes"], erreurs  # résultat


def rendre_devis_form(demande, valeurs, erreurs, edition, identifiant=None, code=200):  # affiche le formulaire de devis
    return render_template("devis_form.html", demande=demande, valeurs=valeurs, erreurs=erreurs, phrases=phrases_du_devis(demande, valeurs), civilites=CIVILITES, civilite_choix=CIVILITE_CHOIX, edition=edition, identifiant=identifiant), code  # page


def demande_ou_404(identifiant):  # lit la demande ou affiche « introuvable »
    demande = db.demande(jeton(), identifiant)  # lecture
    if not demande:  # introuvable
        abort(404)  # page introuvable
    return demande  # demande trouvée


@app.route("/demandes/<identifiant>/devis/nouveau", methods=["GET", "POST"])  # création d'un devis
@admin_requis  # réservée aux admins
def nouveau_devis(identifiant):  # affiche et traite le formulaire de devis
    demande = demande_ou_404(identifiant)  # la demande concernée
    if request.method == "POST":  # formulaire envoyé
        devis, lignes, erreurs = lire_devis(request.form, demande)  # lit et vérifie
        if erreurs:  # à corriger
            return rendre_devis_form(demande, request.form, erreurs, False, code=422)  # réaffiche
        devis_id = db.creer_devis(jeton(), identifiant, devis, lignes)  # enregistre
        flash("Devis enregistré en brouillon.", "ok")  # confirmation
        return redirect(url_for("fiche_devis", identifiant=devis_id))  # va à la fiche du devis
    return rendre_devis_form(demande, valeurs_initiales(demande, db.reglages(jeton())), [], False)  # formulaire prérempli


@app.route("/devis/<identifiant>")  # fiche d'un devis
@connexion_requise  # réservée aux personnes connectées
def fiche_devis(identifiant):  # affiche le devis
    devis = db.devis(jeton(), identifiant)  # lecture
    if not devis:  # introuvable
        abort(404)  # page introuvable
    totaux = echeances(devis)  # acomptes et solde
    return render_template("devis_fiche.html", statuts_devis=[(c, STATUTS_DEVIS[c]) for c in STATUTS_DEVIS_CHOIX], devis=devis, demande=devis["demandes"], client=devis["demandes"]["clients"], totaux=totaux)  # affiche la page


@app.route("/devis/<identifiant>/statut", methods=["POST"])  # changement de statut d'un devis (brouillon, envoyé, accepté, refusé)
@admin_requis  # réservée aux admins
def changer_statut_devis(identifiant):  # enregistre le statut du devis et fait avancer la demande si besoin
    statut = request.form.get("statut", "")  # statut choisi
    if statut not in STATUTS_DEVIS_CHOIX:  # valeur inattendue (« remplacé » ne se choisit pas à la main)
        abort(400)  # requête refusée
    devis = db.devis(jeton(), identifiant)  # lit le devis avec sa demande
    if not devis:  # introuvable
        abort(404)  # page introuvable
    db.changer_statut_devis(jeton(), identifiant, statut)  # écrit le statut du devis
    demande = devis["demandes"]  # demande liée
    suite = AVANCE_DEMANDE.get(statut)  # (nouveau statut de la demande, statuts qui peuvent avancer)
    if suite and demande["statut"] in suite[1]:  # la demande est en retard sur le devis : elle avance, jamais l'inverse
        db.changer_statut(jeton(), demande["id"], suite[0])  # aligne la demande
    flash(f"Devis : {STATUTS_DEVIS[statut]}.", "ok")  # confirmation
    return redirect(url_for("fiche_devis", identifiant=identifiant))  # retour à la fiche du devis


STATUTS_SUPPRIMABLES = ("brouillon", "refuse", "remplace")  # un devis envoyé ou accepté ne se supprime pas : on le remet d'abord en brouillon


@app.route("/devis/<identifiant>/supprimer", methods=["GET", "POST"])  # suppression d'un devis (page de confirmation puis suppression)
@admin_requis  # réservée aux admins
def supprimer_devis(identifiant):  # demande confirmation, puis supprime le devis et ses lignes
    devis = db.devis(jeton(), identifiant)  # lit le devis avec sa demande
    if not devis:  # introuvable
        abort(404)  # page introuvable
    if devis["statut"] not in STATUTS_SUPPRIMABLES:  # envoyé ou accepté : trop risqué
        flash("Un devis envoyé ou accepté ne peut pas être supprimé. Remettez-le d'abord en brouillon si c'est une erreur.", "erreur")  # explication
        return redirect(url_for("fiche_devis", identifiant=identifiant))  # retour à la fiche
    demande = devis["demandes"]  # demande liée
    if request.method == "POST":  # confirmation reçue
        db.supprimer_devis(jeton(), identifiant)  # supprime les lignes puis le devis
        flash(f"Devis {devis['numero']} supprimé.", "ok")  # confirmation
        return redirect(url_for("fiche_demande", identifiant=demande["id"]))  # retour à la demande
    return render_template("devis_supprimer.html", devis=devis, demande=demande)  # page de confirmation


def echeances(devis):  # calcule les deux acomptes et le solde d'un devis enregistré (le solde est le reste exact)
    total = Decimal(str(devis["total_ttc"]))  # total à payer
    p1 = Decimal(str(devis["pourcentage_acompte_1"]))  # pourcentage du premier acompte
    p2 = Decimal(str(devis["pourcentage_acompte_2"]))  # pourcentage du deuxième acompte
    a1 = calcul.r2(total * p1 / 100)  # premier acompte
    a2 = calcul.r2(total * p2 / 100)  # deuxième acompte
    return {"a1": a1, "a2": a2, "a3": total - a1 - a2, "p1": p1, "p2": p2, "p3": 100 - p1 - p2}  # montants et pourcentages


def donnees_pdf(devis, reglages):  # rassemble tout ce dont le PDF a besoin, déjà mis en forme
    demande = devis["demandes"]  # la demande liée
    client = demande["clients"]  # le client
    saisie = devis.get("saisie") or {}  # saisie d'origine (tarifs utilisés)
    ec = echeances(devis)  # acomptes et solde
    personnes = calcul.propre(Decimal(devis["adultes"]) + Decimal(devis["enfants"]) / 2)  # un enfant = une demi-tête
    horaire = demande.get("horaire")  # horaire éventuel
    lignes = [{**ligne, "montant": Decimal(str(ligne["montant"])), "quantite": ligne.get("quantite"), "prix_unitaire": ligne.get("prix_unitaire")} for ligne in devis["lignes"]]  # montants en Decimal
    nourriture = next((l["montant"] for l in lignes if l["categorie"] == "forfait" and not l["libelle"].lower().startswith("débarras")), None)  # forfait mets et boissons
    deplacement = next((l for l in lignes if l["categorie"] == "kilometrique"), None)  # ligne de déplacement
    adresse_ville = " ".join(filter(None, [client.get("code_postal"), client.get("ville")]))  # code postal et ville
    return {
        "numero": devis["numero"], "objet": devis["titre"], "ville_date": "Lausanne, le " + date_fr(devis["date_emission"]),
        "date_evt": date_fr(demande.get("date_evenement")) + (", " + horaire if horaire else " (horaire à préciser)"), "lieu_evt": demande.get("lieu") or "à préciser",
        "client_lignes": [l for l in [(CIVILITES.get(saisie.get("civilite", ""), CIVILITES[""])[1] + " " if not client.get("entreprise") and CIVILITES.get(saisie.get("civilite", ""), CIVILITES[""])[1] else "") + nom_client(client), client.get("adresse"), adresse_ville, client.get("email"), client.get("telephone")] if l],
        "salutation": devis.get("formule_appel") or "Madame, Monsieur,", "phrases": [l for l in (devis.get("introduction_texte") or "").split("\n") if l.strip()],
        "personnes": personnes, "affichage_prix": saisie.get("affichage_prix", "total"), "forfait_nourriture": nourriture, "deplacement": deplacement, "menu_lignes": [l.strip() for l in (devis.get("menu_texte") or "").splitlines() if l.strip()],
        "lignes": lignes, "soumis_tva": devis["soumis_tva"], "taux_tva": "%g" % Decimal(str(devis["taux_tva"])), "total_ht": Decimal(str(devis["total_ht"])), "montant_tva": Decimal(str(devis["montant_tva"])), "total": Decimal(str(devis["total_ttc"])),
        "validite": devis["validite_jours"], "a1": ec["a1"], "a2": ec["a2"], "a3": ec["a3"], "p1": ec["p1"], "p2": ec["p2"], "p3": ec["p3"], "p1_txt": "%g" % ec["p1"], "p2_txt": "%g" % ec["p2"], "p3_txt": "%g" % ec["p3"],
        "tarif_h": nombre_texte(saisie.get("tarif_h") or reglages.get("tarif_horaire", 35)), "tarif_hn": nombre_texte(saisie.get("tarif_hn") or reglages.get("tarif_horaire_nuit", 42)),
        "reglages": reglages,
    }  # dictionnaire complet pour pdf_devis.generer


@app.route("/devis/<identifiant>/pdf")  # téléchargement du PDF
@connexion_requise  # réservée aux personnes connectées
def telecharger_pdf(identifiant):  # fabrique et envoie le PDF
    devis = db.devis(jeton(), identifiant)  # lecture du devis
    if not devis:  # introuvable
        abort(404)  # page introuvable
    contenu = pdf_devis.generer(donnees_pdf(devis, db.reglages(jeton())))  # PDF en mémoire
    nom = re.sub(r"[^0-9A-Za-z-]", "", str(devis["numero"]))  # nom de fichier sûr
    return Response(contenu, mimetype="application/pdf", headers={"Content-Disposition": f'attachment; filename="Devis-{nom}.pdf"'})  # envoi en téléchargement


@app.route("/devis/<identifiant>/modifier", methods=["GET", "POST"])  # modification d'un devis
@admin_requis  # réservée aux admins
def modifier_devis(identifiant):  # affiche et traite le formulaire
    devis_actuel = db.devis(jeton(), identifiant)  # lecture
    if not devis_actuel:  # introuvable
        abort(404)  # page introuvable
    demande = devis_actuel["demandes"]  # la demande concernée
    if request.method == "POST":  # formulaire envoyé
        devis, lignes, erreurs = lire_devis(request.form, demande)  # lit et vérifie
        if erreurs:  # à corriger
            return rendre_devis_form(demande, request.form, erreurs, True, identifiant, 422)  # réaffiche
        db.modifier_devis(jeton(), identifiant, devis, lignes)  # enregistre
        flash("Devis mis à jour.", "ok")  # confirmation
        return redirect(url_for("fiche_devis", identifiant=identifiant))  # retour à la fiche
    return rendre_devis_form(demande, devis_actuel.get("saisie") or valeurs_initiales(demande, db.reglages(jeton())), [], True, identifiant)  # formulaire prérempli avec la saisie d'origine


# ---------------------------------------------------------------- réglages
CHAMPS_TEXTE_REGLAGES = ["raison_sociale", "adresse", "numero_ide", "site_web", "email", "telephone", "banque", "adresse_banque", "signataire_nom", "signataire_fonction", "mention_signature"]  # champs texte libres
CHAMPS_NOMBRE_REGLAGES = [  # code, libellé, minimum, maximum
    ("tarif_horaire", "Tarif horaire de jour", Decimal("0"), Decimal("500")),
    ("tarif_horaire_nuit", "Tarif horaire de nuit", Decimal("0"), Decimal("500")),
    ("tarif_km", "Tarif au kilomètre", Decimal("0"), Decimal("20")),
    ("taux_tva", "Taux de TVA", Decimal("0"), Decimal("30")),
    ("pourcentage_acompte_1", "Premier acompte (%)", Decimal("0"), Decimal("100")),
    ("pourcentage_acompte_2", "Deuxième acompte (%)", Decimal("0"), Decimal("100")),
]


def iban_valide(iban):  # vérifie la longueur et la clé de contrôle (modulo 97) d'un IBAN
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", iban):  # forme générale
        return False  # refusé
    if iban[:2] in ("CH", "LI") and len(iban) != 21:  # IBAN suisse ou liechtensteinois : 21 caractères
        return False  # refusé
    deplace = iban[4:] + iban[:4]  # déplace les 4 premiers caractères à la fin
    chiffres = "".join(str(int(c, 36)) for c in deplace)  # lettres converties en nombres (A = 10 ...)
    return int(chiffres) % 97 == 1  # clé de contrôle correcte


def iban_lisible(iban):  # CH9300762011623852957 devient CH93 0076 2011 6238 5295 7
    return " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))  # groupes de 4


@app.route("/reglages", methods=["GET", "POST"])  # écran des réglages
@admin_requis  # réservé aux admins (l'IBAN et la banque ne sont pas pour tout le monde)
def reglages():  # affiche et enregistre les réglages
    if request.method == "POST":  # formulaire envoyé
        erreurs = []  # messages à corriger
        valeurs = {nom: texte(request.form, nom) for nom in CHAMPS_TEXTE_REGLAGES}  # champs texte
        if valeurs["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", valeurs["email"]):  # e-mail mal formé
            erreurs.append("L'adresse e-mail n'est pas valide.")  # message
        brut_iban = re.sub(r"\s", "", request.form.get("iban") or "").upper()  # IBAN sans espaces
        if brut_iban and not iban_valide(brut_iban):  # IBAN rempli mais faux
            erreurs.append("L'IBAN n'est pas valide : vérifie les chiffres (une IBAN suisse a 21 caractères).")  # message
        valeurs["iban"] = iban_lisible(brut_iban) if brut_iban else None  # enregistré avec espaces
        for nom, libelle, minimum, maximum in CHAMPS_NOMBRE_REGLAGES:  # nombres décimaux
            brut = (request.form.get(nom) or "").strip().replace(",", ".")  # virgule acceptée
            try:  # lecture du nombre
                nombre = Decimal(brut)  # conversion exacte
            except Exception:  # texte invalide ou vide
                erreurs.append(f"{libelle} : saisis un nombre.")  # message
                continue  # champ suivant
            if not nombre.is_finite() or nombre < minimum or nombre > maximum:  # hors limites
                erreurs.append(f"{libelle} : entre {minimum} et {maximum}.")  # message
            valeurs[nom] = nombre  # garde la valeur
        brut_jours = (request.form.get("validite_jours") or "").strip()  # durée de validité
        if brut_jours.isdigit() and 1 <= int(brut_jours) <= 365:  # entier raisonnable
            valeurs["validite_jours"] = int(brut_jours)  # garde la valeur
        else:  # invalide
            erreurs.append("Validité du devis : un nombre de jours entre 1 et 365.")  # message
        a1, a2 = valeurs.get("pourcentage_acompte_1"), valeurs.get("pourcentage_acompte_2")  # acomptes
        if isinstance(a1, Decimal) and isinstance(a2, Decimal) and a1 + a2 > 100:  # plus que le total
            erreurs.append("Les deux acomptes dépassent 100 % du total.")  # message
        if not valeurs["raison_sociale"]:  # nom obligatoire
            erreurs.append("La raison sociale est obligatoire.")  # message
        if erreurs:  # affiche à nouveau avec la saisie
            saisie = {**request.form, "iban": request.form.get("iban", "")}  # valeurs retapées
            return render_template("reglages.html", valeurs=saisie, erreurs=erreurs), 422  # erreur de validation
        db.modifier_reglages(jeton(), valeurs)  # enregistre
        flash("Réglages enregistrés. Ils s'appliquent aux prochains devis et PDF.", "ok")  # confirmation
        return redirect(url_for("reglages"))  # évite le renvoi du formulaire
    courants = db.reglages(jeton())  # réglages enregistrés
    valeurs = {cle: (nombre_texte(v) if cle in [c[0] for c in CHAMPS_NOMBRE_REGLAGES] + ["validite_jours"] else (v or "")) for cle, v in courants.items()}  # texte prêt pour les champs
    return render_template("reglages.html", valeurs=valeurs, erreurs=[])  # affiche le formulaire


# ---------------------------------------------------------------- stratégie
def date_saisie(form, nom, erreurs, libelle):  # lit une date facultative (AAAA-MM-JJ)
    brut = texte(form, nom)  # texte saisi
    if not brut:  # champ vide
        return None  # pas de date
    try:  # vérifie le format
        datetime.date.fromisoformat(brut)  # lève une erreur si invalide
    except ValueError:  # date invalide
        erreurs.append(f"{libelle} : date non valide.")  # message d'erreur
        return None  # valeur de repli
    return brut  # date valide


def nombre_saisi(brut, erreurs, libelle):  # lit un montant facultatif (accepte 12'000 et 12000,50)
    brut = (brut or "").strip()  # retire les espaces
    if not brut:  # champ vide
        return None  # pas de valeur
    try:  # conversion
        valeur = round(float(brut.replace("'", "").replace(" ", "").replace(",", ".")), 2)  # texte vers nombre
    except ValueError:  # pas un nombre
        erreurs.append(f"{libelle} : nombre attendu.")  # message d'erreur
        return None  # valeur de repli
    if valeur < 0:  # négatif
        erreurs.append(f"{libelle} : le nombre ne peut pas être négatif.")  # message d'erreur
        return None  # valeur de repli
    return valeur  # nombre valide


def lien_sur(brut, erreurs, libelle):  # accepte seulement les adresses http(s) (évite les liens dangereux)
    if not brut:  # champ vide
        return None  # rien
    if not brut.lower().startswith(("http://", "https://")):  # autre type de lien
        erreurs.append(f"{libelle} : l'adresse doit commencer par http:// ou https://.")  # message d'erreur
        return None  # valeur de repli
    return brut  # lien accepté


def lire_action(form):  # transforme le formulaire en action, avec la liste des erreurs
    erreurs = []  # messages à afficher
    axe, priorite, statut = form.get("axe", ""), form.get("priorite", ""), form.get("statut", "")  # choix
    if axe not in strategie.LIBELLE_AXE or priorite not in dict(strategie.PRIORITES) or statut not in strategie.LIBELLE_STATUT_ACTION:  # valeurs inattendues
        abort(400)  # requête refusée
    echeance = date_saisie(form, "echeance", erreurs, "Échéance")  # date limite
    if not texte(form, "action"):  # intitulé obligatoire
        erreurs.append("L'action est obligatoire.")  # message d'erreur
    mois = f"{strategie.MOIS_COURTS[int(echeance[5:7]) - 1]} {echeance[:4]}" if echeance else texte(form, "mois")  # mois déduit de l'échéance
    valeurs = {"action": texte(form, "action"), "axe": axe, "priorite": priorite, "statut": statut, "echeance": echeance, "mois": mois, "pourquoi": texte(form, "pourquoi"), "livrable": texte(form, "livrable"), "responsable": texte(form, "responsable"), "indicateur": texte(form, "indicateur"), "notes": texte(form, "notes")}  # champs de l'action
    return valeurs, erreurs  # renvoie les deux résultats


def lire_piste(form):  # transforme le formulaire en piste, avec la liste des erreurs
    erreurs = []  # messages à afficher
    categorie, priorite, statut, dossier = form.get("categorie", ""), form.get("priorite", ""), form.get("statut", ""), form.get("dossier_envoye", "")  # choix
    if categorie not in strategie.LIBELLE_CATEGORIE or priorite not in dict(strategie.PRIORITES) or statut not in strategie.LIBELLE_STATUT_PISTE or dossier not in strategie.LIBELLE_DOSSIER:  # valeurs inattendues
        abort(400)  # requête refusée
    if not texte(form, "nom"):  # nom obligatoire
        erreurs.append("Le nom est obligatoire.")  # message d'erreur
    email = texte(form, "email")  # adresse saisie
    if email and ("@" not in email or " " in email):  # contrôle simple
        erreurs.append("L'adresse e-mail ne semble pas valide.")  # message d'erreur
    frais_pct = nombre_saisi(form.get("frais_pct"), erreurs, "Part du CA reversée (%)")  # pourcentage du CA reversé à l'organisateur
    if frais_pct is not None and frais_pct > 100:  # plus de 100 % n'a pas de sens
        erreurs.append("Part du CA reversée : 100 % au maximum.")  # message d'erreur
        frais_pct = None  # valeur de repli
    valeurs = {"frais_fixes": nombre_saisi(form.get("frais_fixes"), erreurs, "Frais d'inscription fixes"), "frais_pct": frais_pct, "ca_hors_devis": nombre_saisi(form.get("ca_hors_devis"), erreurs, "Ventes sur place"), "couts_hors_devis": nombre_saisi(form.get("couts_hors_devis"), erreurs, "Coûts du stand"), "categorie": categorie, "nom": texte(form, "nom"), "personne": texte(form, "personne"), "lieu": texte(form, "lieu"), "type_piste": texte(form, "type_piste"), "dates_info": texte(form, "dates_info"), "pourquoi": texte(form, "pourquoi"), "conditions": texte(form, "conditions"), "candidature": texte(form, "candidature"), "lien_malewa": texte(form, "lien_malewa"), "email": email, "telephone": texte(form, "telephone"), "contact_libre": texte(form, "contact_libre"), "site": lien_sur(texte(form, "site"), erreurs, "Site"), "priorite": priorite, "statut": statut, "dossier_envoye": dossier or None, "date_envoi": date_saisie(form, "date_envoi", erreurs, "Date d'envoi"), "prochaine_relance": date_saisie(form, "prochaine_relance", erreurs, "Prochaine relance"), "notes": texte(form, "notes")}  # champs de la piste
    return valeurs, erreurs  # renvoie les deux résultats


def note_de_journal(form):  # lit la note du journal (1 000 caractères au maximum)
    note = texte(form, "note")  # texte saisi
    if not note:  # vide
        return None  # rien à enregistrer
    return note[:1000]  # coupe les textes trop longs


@app.route("/strategie")  # tableau de bord de la stratégie
@connexion_requise  # réservée aux personnes connectées
def strategie_accueil():  # affiche les chiffres du moment, les échéances et le journal
    aujourdhui = datetime.date.today()  # date du jour
    actions = db.actions(jeton())  # actions du plan
    demandes, devis = db.kpi_donnees(jeton())  # demandes et devis
    manuel = db.kpi_manuel(jeton())  # saisies à la main
    kpi = strategie.calculer_kpi(demandes, devis, manuel["mois"], manuel["cibles"])  # tous les calculs
    ouvertes = [a for a in actions if a["statut"] in ("a_faire", "en_cours")]  # actions pas terminées
    ouvertes.sort(key=lambda a: (a["echeance"] is None, str(a["echeance"] or "")))  # échéance la plus proche d'abord
    comptes = {code: sum(1 for a in actions if a["statut"] == code) for code, _ in strategie.STATUTS_ACTION}  # nombre d'actions par statut
    retard = [a for a in ouvertes if strategie.en_retard(a, aujourdhui)]  # actions en retard
    pistes = db.pistes(jeton())  # toutes les pistes
    relances = [p for p in pistes if p.get("prochaine_relance") and p["statut"] not in ("retenu", "abandonne") and str(p["prochaine_relance"]) <= (aujourdhui + datetime.timedelta(days=7)).isoformat()]  # relances à faire dans les 7 jours
    relances.sort(key=lambda p: str(p["prochaine_relance"]))  # la plus urgente d'abord
    par_categorie = [{"code": code, "libelle": nom, "total": sum(1 for p in pistes if p["categorie"] == code), "a_faire": sum(1 for p in pistes if p["categorie"] == code and p["statut"] == "a_faire"), "en_cours": sum(1 for p in pistes if p["categorie"] == code and p["statut"] in ("contacte", "en_discussion")), "retenues": sum(1 for p in pistes if p["categorie"] == code and p["statut"] == "retenu")} for code, nom in strategie.CATEGORIES]  # synthèse par liste
    manques = strategie.a_completer(demandes, aujourdhui)  # ce qu'il manque dans les demandes
    mois_courant = next((l for l in kpi["lignes"] if l["mois"] == aujourdhui.strftime("%Y-%m")), None)  # ligne du mois en cours
    return render_template("strategie.html", comptes=comptes, total_actions=len(actions), retard=retard, prochaines=ouvertes[:6], kpi=kpi, mois_courant=mois_courant, origines=strategie.statistiques_origine(demandes, devis, ORIGINES), par_categorie=par_categorie, relances=relances, manques=manques, journal=db.journal(jeton(), limite=6), aujourdhui=aujourdhui.isoformat())  # affiche la page


@app.route("/strategie/actions")  # liste des actions du plan
@connexion_requise  # réservée aux personnes connectées
def strategie_actions():  # affiche les actions, filtrables par axe, statut, priorité ou retard
    axe, statut, priorite, retard = request.args.get("axe", ""), request.args.get("statut", ""), request.args.get("priorite", ""), request.args.get("retard", "")  # filtres
    if (axe and axe not in strategie.LIBELLE_AXE) or (statut and statut not in strategie.LIBELLE_STATUT_ACTION) or (priorite and priorite not in dict(strategie.PRIORITES)):  # valeurs inattendues
        abort(400)  # requête refusée
    actions = db.actions(jeton())  # lit les actions
    for action in actions:  # repère les retards
        action["retard"] = strategie.en_retard(action)  # vrai si en retard
    liste = [a for a in actions if (not axe or a["axe"] == axe) and (not statut or a["statut"] == statut) and (not priorite or a["priorite"] == priorite) and (not retard or a["retard"])]  # applique les filtres
    return render_template("strategie_actions.html", actions=liste, axe=axe, statut=statut, priorite=priorite, retard=retard, axes=strategie.AXES, statuts=strategie.STATUTS_ACTION, priorites=strategie.PRIORITES)  # affiche la page


def rendre_action_form(valeurs, erreurs, titre_page, identifiant=None, code=200):  # affiche le formulaire d'action
    return render_template("action_form.html", valeurs=valeurs, erreurs=erreurs, axes=strategie.AXES, statuts=strategie.STATUTS_ACTION, priorites=strategie.PRIORITES, titre_page=titre_page, identifiant=identifiant), code  # page


@app.route("/strategie/actions/nouvelle", methods=["GET", "POST"])  # création d'une action
@admin_requis  # réservée aux admins
def nouvelle_action():  # affiche et traite le formulaire
    if request.method == "POST":  # formulaire envoyé
        valeurs, erreurs = lire_action(request.form)  # lit et vérifie
        if erreurs:  # à corriger
            return rendre_action_form(request.form, erreurs, "Nouvelle action", code=422)  # réaffiche
        identifiant = db.creer_action(jeton(), valeurs)  # enregistre
        db.ajouter_journal(jeton(), session["utilisateur"]["nom"], "Action créée.", action_id=identifiant)  # trace dans le journal
        flash("Action créée.", "ok")  # confirmation
        return redirect(url_for("fiche_action", identifiant=identifiant))  # va à la fiche
    return rendre_action_form({"axe": "mariages", "priorite": "P2", "statut": "a_faire", "responsable": session["utilisateur"]["nom"]}, [], "Nouvelle action")  # formulaire vide


def action_ou_404(identifiant):  # lit l'action ou affiche « introuvable »
    action = db.action(jeton(), identifiant)  # lecture
    if not action:  # introuvable
        abort(404)  # page introuvable
    return action  # action trouvée


@app.route("/strategie/actions/<identifiant>")  # fiche d'une action
@connexion_requise  # réservée aux personnes connectées
def fiche_action(identifiant):  # affiche la fiche et son journal
    action = action_ou_404(identifiant)  # lit l'action
    action["retard"] = strategie.en_retard(action)  # repère le retard
    return render_template("action_fiche.html", action=action, statuts=strategie.STATUTS_ACTION, journal=db.journal(jeton(), action_id=identifiant))  # affiche la page


@app.route("/strategie/actions/<identifiant>/modifier", methods=["GET", "POST"])  # modification d'une action
@admin_requis  # réservée aux admins
def modifier_action(identifiant):  # affiche et traite le formulaire
    action = action_ou_404(identifiant)  # lit l'action
    if request.method == "POST":  # formulaire envoyé
        valeurs, erreurs = lire_action(request.form)  # lit et vérifie
        if erreurs:  # à corriger
            return rendre_action_form(request.form, erreurs, "Modifier l'action", identifiant, 422)  # réaffiche
        db.modifier_action(jeton(), identifiant, valeurs)  # enregistre
        flash("Action mise à jour.", "ok")  # confirmation
        return redirect(url_for("fiche_action", identifiant=identifiant))  # retour à la fiche
    return rendre_action_form({cle: ("" if valeur is None else valeur) for cle, valeur in action.items()}, [], "Modifier l'action", identifiant)  # formulaire prérempli


@app.route("/strategie/actions/<identifiant>/statut", methods=["POST"])  # changement de statut d'une action
@admin_requis  # réservée aux admins
def statut_action(identifiant):  # enregistre le statut et le note dans le journal
    action = action_ou_404(identifiant)  # lit l'action
    statut = request.form.get("statut", "")  # statut choisi
    if statut not in strategie.LIBELLE_STATUT_ACTION:  # valeur inattendue
        abort(400)  # requête refusée
    if statut != action["statut"]:  # seulement si ça change
        db.modifier_action(jeton(), identifiant, {"statut": statut})  # écrit le statut
        db.ajouter_journal(jeton(), session["utilisateur"]["nom"], f"Statut : {strategie.LIBELLE_STATUT_ACTION[action['statut']]} → {strategie.LIBELLE_STATUT_ACTION[statut]}", action_id=identifiant)  # trace
        flash(f"Statut : {strategie.LIBELLE_STATUT_ACTION[statut]}.", "ok")  # confirmation
    return redirect(url_for("fiche_action", identifiant=identifiant))  # retour à la fiche


@app.route("/strategie/actions/<identifiant>/note", methods=["POST"])  # note de journal sur une action
@admin_requis  # réservée aux admins
def note_action(identifiant):  # ajoute la note
    action_ou_404(identifiant)  # vérifie que l'action existe
    note = note_de_journal(request.form)  # lit la note
    if note:  # une note a été saisie
        db.ajouter_journal(jeton(), session["utilisateur"]["nom"], note, action_id=identifiant)  # enregistre
        flash("Note ajoutée au journal.", "ok")  # confirmation
    return redirect(url_for("fiche_action", identifiant=identifiant))  # retour à la fiche


@app.route("/strategie/pistes")  # liste des pistes (festivals, planners, salons, entreprises)
@connexion_requise  # réservée aux personnes connectées
def strategie_pistes():  # affiche les pistes d'une liste, filtrables par statut
    categorie, statut = request.args.get("categorie", "festival"), request.args.get("statut", "")  # filtres
    if categorie not in strategie.LIBELLE_CATEGORIE or (statut and statut not in strategie.LIBELLE_STATUT_PISTE):  # valeurs inattendues
        abort(400)  # requête refusée
    toutes = db.pistes(jeton())  # lit les pistes
    nombres = {code: sum(1 for p in toutes if p["categorie"] == code) for code, _ in strategie.CATEGORIES}  # nombre par liste
    liste = [p for p in toutes if p["categorie"] == categorie and (not statut or p["statut"] == statut)]  # applique les filtres
    demandes, devis = db.kpi_donnees(jeton())  # demandes et devis (pour le résultat de chaque piste)
    groupes = strategie.demandes_par_piste(demandes, devis)  # demandes liées, par piste
    for piste in liste:  # calcule le bilan de chaque piste affichée
        piste["bilan"] = strategie.bilan_piste(piste, groupes.get(piste["id"], []))  # None si rien n'est saisi
    return render_template("strategie_pistes.html", pistes=liste, categorie=categorie, statut=statut, categories=strategie.CATEGORIES, nombres=nombres, statuts=strategie.STATUTS_PISTE)  # affiche la page


def rendre_piste_form(valeurs, erreurs, titre_page, identifiant=None, code=200):  # affiche le formulaire de piste
    return render_template("piste_form.html", valeurs=valeurs, erreurs=erreurs, categories=strategie.CATEGORIES, statuts=strategie.STATUTS_PISTE, priorites=strategie.PRIORITES, dossiers=strategie.DOSSIERS, titre_page=titre_page, identifiant=identifiant), code  # page


@app.route("/strategie/pistes/nouvelle", methods=["GET", "POST"])  # création d'une piste
@admin_requis  # réservée aux admins
def nouvelle_piste():  # affiche et traite le formulaire
    if request.method == "POST":  # formulaire envoyé
        valeurs, erreurs = lire_piste(request.form)  # lit et vérifie
        if erreurs:  # à corriger
            return rendre_piste_form(request.form, erreurs, "Nouvelle piste", code=422)  # réaffiche
        identifiant = db.creer_piste(jeton(), valeurs)  # enregistre
        db.ajouter_journal(jeton(), session["utilisateur"]["nom"], "Piste ajoutée.", piste_id=identifiant)  # trace
        flash("Piste ajoutée.", "ok")  # confirmation
        return redirect(url_for("fiche_piste", identifiant=identifiant))  # va à la fiche
    categorie = request.args.get("categorie", "festival")  # liste d'où l'on vient
    return rendre_piste_form({"categorie": categorie if categorie in strategie.LIBELLE_CATEGORIE else "festival", "priorite": "P2", "statut": "a_faire"}, [], "Nouvelle piste")  # formulaire vide


def piste_ou_404(identifiant):  # lit la piste ou affiche « introuvable »
    piste = db.piste(jeton(), identifiant)  # lecture
    if not piste:  # introuvable
        abort(404)  # page introuvable
    return piste  # piste trouvée


@app.route("/strategie/pistes/<identifiant>")  # fiche d'une piste
@connexion_requise  # réservée aux personnes connectées
def fiche_piste(identifiant):  # affiche la fiche, ses demandes liées et son journal
    piste = piste_ou_404(identifiant)  # lit la piste
    demandes = db.demandes_de_piste(jeton(), identifiant)  # demandes issues de cette piste
    bilan = strategie.bilan_piste(piste, demandes)  # bilan financier de la piste (None si rien n'est saisi)
    return render_template("piste_fiche.html", bilan=bilan, piste=piste, demandes=demandes, ca_total=sum(float(d["ca"] or 0) for d in demandes), statuts=strategie.STATUTS_PISTE, types=dict(TYPES), journal=db.journal(jeton(), piste_id=identifiant), conseille=strategie.DOSSIER_CONSEILLE.get(piste["categorie"]))  # affiche la page


@app.route("/strategie/pistes/<identifiant>/modifier", methods=["GET", "POST"])  # modification d'une piste
@admin_requis  # réservée aux admins
def modifier_piste(identifiant):  # affiche et traite le formulaire
    piste = piste_ou_404(identifiant)  # lit la piste
    if request.method == "POST":  # formulaire envoyé
        valeurs, erreurs = lire_piste(request.form)  # lit et vérifie
        if erreurs:  # à corriger
            return rendre_piste_form(request.form, erreurs, "Modifier la piste", identifiant, 422)  # réaffiche
        db.modifier_piste(jeton(), identifiant, valeurs)  # enregistre
        flash("Piste mise à jour.", "ok")  # confirmation
        return redirect(url_for("fiche_piste", identifiant=identifiant))  # retour à la fiche
    return rendre_piste_form({cle: ("" if valeur is None else valeur) for cle, valeur in piste.items()}, [], "Modifier la piste", identifiant)  # formulaire prérempli


@app.route("/strategie/pistes/<identifiant>/statut", methods=["POST"])  # changement de statut d'une piste
@admin_requis  # réservée aux admins
def statut_piste(identifiant):  # enregistre le statut et le note dans le journal
    piste = piste_ou_404(identifiant)  # lit la piste
    statut = request.form.get("statut", "")  # statut choisi
    if statut not in strategie.LIBELLE_STATUT_PISTE:  # valeur inattendue
        abort(400)  # requête refusée
    if statut != piste["statut"]:  # seulement si ça change
        db.modifier_piste(jeton(), identifiant, {"statut": statut})  # écrit le statut
        db.ajouter_journal(jeton(), session["utilisateur"]["nom"], f"Statut : {strategie.LIBELLE_STATUT_PISTE[piste['statut']]} → {strategie.LIBELLE_STATUT_PISTE[statut]}", piste_id=identifiant)  # trace
        flash(f"Statut : {strategie.LIBELLE_STATUT_PISTE[statut]}.", "ok")  # confirmation
    return redirect(url_for("fiche_piste", identifiant=identifiant))  # retour à la fiche


@app.route("/strategie/pistes/<identifiant>/note", methods=["POST"])  # note de journal sur une piste
@admin_requis  # réservée aux admins
def note_piste(identifiant):  # ajoute la note
    piste_ou_404(identifiant)  # vérifie que la piste existe
    note = note_de_journal(request.form)  # lit la note
    if note:  # une note a été saisie
        db.ajouter_journal(jeton(), session["utilisateur"]["nom"], note, piste_id=identifiant)  # enregistre
        flash("Note ajoutée au journal.", "ok")  # confirmation
    return redirect(url_for("fiche_piste", identifiant=identifiant))  # retour à la fiche


@app.route("/strategie/kpi", methods=["GET", "POST"])  # suivi des KPI
@connexion_requise  # réservée aux personnes connectées (la saisie est réservée aux admins)
def strategie_kpi():  # affiche le suivi et enregistre les saisies à la main
    if request.method == "POST":  # formulaire envoyé
        if session["utilisateur"]["role"] != "admin":  # rôle lecture
            abort(403)  # interdit
        erreurs = []  # messages d'erreur
        mois = {}  # saisies par mois
        for cle in strategie.mois_du_plan():  # un mois après l'autre
            avis = (request.form.get("avis_" + cle) or "").strip()  # avis Google cumulés
            if avis and not avis.isdigit():  # pas un entier
                erreurs.append(f"{strategie.libelle_mois(cle)} : avis Google, nombre entier attendu.")  # message d'erreur
                avis = ""  # valeur de repli
            charges = nombre_saisi(request.form.get("ch_" + cle) or request.form.get("charges_toutes"), erreurs, f"{strategie.libelle_mois(cle)} : charges fixes")  # charges fixes du mois (ou le montant commun à tous les mois)
            mois[cle] = {"charges_fixes": charges, "avis_google": int(avis) if avis else None, "ca_commande_simple": nombre_saisi(request.form.get("cs_" + cle), erreurs, f"{strategie.libelle_mois(cle)} : commande simple"), "ca_popup": nombre_saisi(request.form.get("pu_" + cle), erreurs, f"{strategie.libelle_mois(cle)} : pop-up")}  # valeurs du mois
        cibles = {axe: nombre_saisi(request.form.get("cible_" + axe), erreurs, "Cible " + strategie.LIBELLE_AXE[axe]) for axe in strategie.AXES_CA}  # cibles par axe
        if not erreurs:  # tout est valide
            db.sauver_kpi(jeton(), mois, cibles)  # enregistre
            flash("Suivi enregistré.", "ok")  # confirmation
            return redirect(url_for("strategie_kpi"))  # recharge la page
        flash(" ".join(erreurs), "erreur")  # affiche les erreurs
    demandes, devis = db.kpi_donnees(jeton())  # demandes et devis
    manuel = db.kpi_manuel(jeton())  # saisies à la main
    return render_template("strategie_kpi.html", kpi=strategie.calculer_kpi(demandes, devis, manuel["mois"], manuel["cibles"]), manuel=manuel, axes_ca=[(code, strategie.LIBELLE_AXE[code]) for code in strategie.AXES_CA], origines=strategie.statistiques_origine(demandes, devis, ORIGINES), types_stats=strategie.statistiques_type(demandes, devis, TYPES))  # affiche la page


@app.route("/strategie/journal")  # journal complet de ce qui est entrepris
@connexion_requise  # réservée aux personnes connectées
def strategie_journal():  # affiche les 200 dernières entrées
    return render_template("strategie_journal.html", journal=db.journal(jeton(), limite=200))  # affiche la page


@app.route("/sante")  # page de contrôle pour l'hébergeur (aucune donnée)
def sante():  # répond « ok »
    return "ok"  # texte simple


@app.errorhandler(403)  # accès interdit
def interdit(_erreur):  # message pour un rôle lecture
    return render_template("erreur.html", titre="Accès réservé", message="Ton rôle permet de consulter, pas de modifier."), 403  # page d'erreur


@app.errorhandler(404)  # page introuvable
def introuvable(_erreur):  # message pour une adresse inconnue
    return render_template("erreur.html", titre="Page introuvable", message="Cette page n'existe pas ou n'existe plus."), 404  # page d'erreur


@app.errorhandler(Exception)  # toute autre erreur
def erreur_generale(erreur):  # évite d'afficher des détails techniques
    code = getattr(erreur, "code", 500)  # code HTTP si disponible
    if isinstance(code, int) and code < 500:  # erreur côté demande (ex. 400)
        return render_template("erreur.html", titre="Requête refusée", message="Recharge la page et réessaie."), code  # page d'erreur
    logging.exception("Erreur inattendue")  # note l'erreur côté serveur
    return render_template("erreur.html", titre="Un problème est survenu", message="Réessaie dans un instant. Si cela continue, préviens Nancy."), 500  # message sobre


if __name__ == "__main__":  # lancement local : python app.py
    app.run(debug=MODE_DEMO, port=int(os.environ.get("PORT", 5000)))  # serveur de développement (jamais en ligne)
