"""Malewa back-office : application Flask (connexion et gestion des demandes)."""  # description du fichier
import os  # accès aux variables d'environnement
import time  # horodatage pour l'expiration de la session
import secrets  # génération et comparaison sûres du jeton anti-falsification (CSRF)
import datetime  # lecture et formatage des dates
import logging  # journal des erreurs côté serveur
from functools import wraps  # conserve le nom des fonctions décorées
from decimal import Decimal  # montants exacts
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
    return {"csrf_token": session["_csrf"], "utilisateur": session.get("utilisateur"), "LIBELLE_STATUT": LIBELLE_STATUT, "STATUTS_DEVIS": STATUTS_DEVIS, "MODE_DEMO": MODE_DEMO, "ORIGINES": ORIGINES, "LIBELLE_ORIGINE": dict(ORIGINES)}  # variables partagées


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
    if source not in dict(SOURCES) or genre not in dict(TYPES) or origine not in dict(ORIGINES):  # valeurs inattendues
        abort(400)  # requête refusée
    demande = {  # champs de la demande
        "titre": texte(form, "titre") or "Demande sans titre", "source": source, "origine": origine or None, "type_evenement": genre,
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
    return render_template("demande_fiche.html", demande=demande, conflits=conflits, statuts=STATUTS, types=dict(TYPES), sources=dict(SOURCES), devis_liste=db.devis_de_demande(jeton(), identifiant))  # affiche la page


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
    return render_template("devis_fiche.html", devis=devis, demande=devis["demandes"], client=devis["demandes"]["clients"], totaux=totaux)  # affiche la page


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
