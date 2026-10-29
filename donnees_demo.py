"""Mode démo : mêmes méthodes que donnees_supabase, avec des données fictives en mémoire.

Sert à tester l'app sans Supabase et à la montrer sans montrer de vrais clients.
Comptes de démo : admin@malewa.demo (modifie) et lecture@malewa.demo (consulte), mot de passe Demo-1234.
"""  # description du fichier
import time  # horodatage pour simuler l'expiration du jeton
import uuid  # identifiants uniques

ACTIFS = ("devis_envoye", "accepte", "acompte_recu")  # statuts qui bloquent une date
MOT_DE_PASSE = "Demo-1234"  # mot de passe de démonstration (jamais utilisé en production)
COMPTES = {  # comptes fictifs : e-mail, identifiant, nom, rôle
    "admin@malewa.demo": ("id-admin", "Nancy (démo)", "admin"),
    "lecture@malewa.demo": ("id-lecture", "Edgar (démo)", "lecture"),
}


def _nouvel_id():  # fabrique un identifiant unique
    return str(uuid.uuid4())  # texte aléatoire unique


class Donnees:  # même interface que la version Supabase
    def __init__(self):  # prépare les données fictives
        self.clients = {}  # clients par identifiant
        self.demandes = {}  # demandes par identifiant
        self.devis_par_id = {}  # devis par identifiant
        fictifs = [  # (prénom, nom, entreprise, e-mail, titre, source, type, date, adultes, enfants, budget, statut)
            ("Aurélie", "Exemple", None, "aurelie@exemple.test", "Mariage Exemple", "whatsapp", "mariage", "2027-06-19", 120, 10, 12000, "nouvelle"),
            ("Marc", "Démo", None, "marc@exemple.test", "Anniversaire 40 ans", "site", "evenement_prive", "2027-03-06", 45, 0, None, "en_discussion"),
            ("Société Exemple SA", "Contact", "Société Exemple SA", "contact@exemple-sa.test", "Cocktail d'entreprise", "email", "evenement_entreprise", "2027-06-19", 80, 0, 6500, "devis_envoye"),
            ("Léa", "Fictive", None, "lea@exemple.test", "Baptême", "telephone", "evenement_prive", "2026-12-12", 30, 8, 3000, "accepte"),
        ]
        for prenom, nom, entreprise, email, titre, source, genre, date, adultes, enfants, budget, statut in fictifs:  # crée chaque exemple
            client_id = _nouvel_id()  # identifiant du client
            self.clients[client_id] = {"id": client_id, "prenom": prenom, "nom": nom, "entreprise": entreprise, "email": email, "telephone": None, "contact_prefere": None, "email_invalide": False, "adresse": None, "code_postal": None, "ville": None}  # fiche client
            demande_id = _nouvel_id()  # identifiant de la demande
            self.demandes[demande_id] = {"id": demande_id, "client_id": client_id, "titre": titre, "source": source, "type_evenement": genre, "date_evenement": date, "horaire": None, "lieu": "Lausanne", "adultes": adultes, "enfants": enfants, "budget_indique": budget, "cout_total": None, "cout_equipe": None, "message_client": None, "notes_internes": None, "statut": statut, "recue_le": "2026-10-20T10:00:00+00:00"}  # fiche demande

    def connexion(self, email, mot_de_passe):  # vérifie les identifiants de démonstration
        compte = COMPTES.get((email or "").lower())  # cherche le compte
        if not compte or mot_de_passe != MOT_DE_PASSE:  # inconnu ou mauvais mot de passe
            raise ValueError("Identifiants incorrects")  # même message vague qu'en production
        return {"jeton": "jeton-" + compte[0], "refresh": "refresh-" + compte[0], "expire": time.time() + 3600, "id": compte[0], "email": email.lower()}  # session fictive

    def rafraichir(self, jeton_refresh):  # renouvelle le jeton fictif
        identifiant = jeton_refresh.replace("refresh-", "")  # retrouve le compte
        email = next(e for e, c in COMPTES.items() if c[0] == identifiant)  # e-mail du compte
        return {"jeton": "jeton-" + identifiant, "refresh": jeton_refresh, "expire": time.time() + 3600, "id": identifiant, "email": email}  # nouvelle session

    def profil(self, jeton, identifiant):  # nom et rôle du compte fictif
        for compte in COMPTES.values():  # parcourt les comptes
            if compte[0] == identifiant:  # trouvé
                return {"nom": compte[1], "role": compte[2]}  # profil fictif
        return None  # inconnu

    def _avec_client(self, demande):  # joint le client à la demande (comme la requête Supabase)
        copie = dict(demande)  # copie pour ne pas modifier l'original
        copie["clients"] = dict(self.clients[demande["client_id"]])  # ajoute la fiche client
        return copie  # renvoie la demande complète

    def liste_demandes(self, jeton, statut=None):  # liste filtrée et triée
        liste = [self._avec_client(d) for d in self.demandes.values() if not statut or d["statut"] == statut]  # filtre par statut
        liste.sort(key=lambda d: (d["date_evenement"] is None, d["date_evenement"] or ""))  # date la plus proche d'abord
        return liste  # renvoie la liste

    def demande(self, jeton, identifiant):  # une demande avec son client
        demande = self.demandes.get(identifiant)  # cherche la demande
        return self._avec_client(demande) if demande else None  # None si introuvable

    def dates_prises(self, jeton, date_iso, exclure=None):  # autres demandes actives le même jour
        if not date_iso:  # pas de date
            return []  # pas de conflit
        return [{"id": d["id"], "titre": d["titre"], "statut": d["statut"]} for d in self.demandes.values() if d["date_evenement"] == date_iso and d["statut"] in ACTIFS and d["id"] != exclure]  # conflits

    def chercher_client(self, jeton, email):  # retrouve un client par e-mail
        for client in self.clients.values():  # parcourt les clients
            if email and client["email"] and client["email"].lower() == email.lower():  # même adresse
                return client["id"]  # identifiant trouvé
        return None  # aucun client

    def creer_demande(self, jeton, client, demande):  # crée le client si besoin puis la demande
        client_id = self.chercher_client(jeton, client.get("email"))  # client existant ?
        if not client_id:  # sinon on le crée
            client_id = _nouvel_id()  # nouvel identifiant
            self.clients[client_id] = {"id": client_id, **client}  # enregistre le client
        identifiant = _nouvel_id()  # identifiant de la demande
        self.demandes[identifiant] = {"id": identifiant, "client_id": client_id, "recue_le": "2026-10-26T12:00:00+00:00", **demande}  # enregistre la demande
        return identifiant  # renvoie l'identifiant

    def modifier_demande(self, jeton, identifiant, client_id, client, demande):  # met à jour la demande et le client
        self.clients[client_id].update(client)  # met à jour le client
        self.demandes[identifiant].update(demande)  # met à jour la demande

    def changer_statut(self, jeton, identifiant, statut):  # change l'étape
        self.demandes[identifiant]["statut"] = statut  # écrit le statut

    # ------------------------------------------------------------ devis
    def reglages(self, jeton):  # réglages fictifs (gardés en mémoire pour pouvoir les modifier)
        if not hasattr(self, "_reglages"):  # première lecture
            self._reglages = {"raison_sociale": "Malewa Sàrl", "adresse": "La Claie-aux-Moines 17, 1000 Lausanne 26", "numero_ide": "CHE-209.761.684", "site_web": "https://malewa.ch", "email": "info@malewa.ch", "telephone": "+41 78 603 36 11", "banque": "Banque de démonstration", "adresse_banque": "Rue du Test 1, 1000 Lausanne", "iban": "CH93 0076 2011 6238 5295 7", "signataire_nom": "Nady Nzita-Nanga", "signataire_fonction": "Gérante", "mention_signature": "Malewa Service Traiteur", "tarif_horaire": 35, "tarif_horaire_nuit": 42, "tarif_km": 1.2, "taux_tva": 8.1, "validite_jours": 14, "pourcentage_acompte_1": 10, "pourcentage_acompte_2": 60}  # valeurs par défaut
        return dict(self._reglages)  # copie, pour ne pas modifier par accident

    def modifier_reglages(self, jeton, valeurs):  # enregistre les réglages fictifs
        self.reglages(jeton)  # s'assure qu'ils existent
        self._reglages.update(valeurs)  # applique les changements

    def devis_de_demande(self, jeton, demande_id):  # devis d'une demande
        return [d for d in self.devis_par_id.values() if d["demande_id"] == demande_id]  # filtre

    def devis(self, jeton, identifiant):  # un devis avec sa demande
        d = self.devis_par_id.get(identifiant)  # cherche
        if not d:  # introuvable
            return None  # rien
        return {**d, "demandes": self._avec_client(self.demandes[d["demande_id"]])}  # joint la demande et le client

    def prochain_numero(self, jeton):  # numéro fictif AAAA-NNN
        return f"2026-{len(self.devis_par_id) + 1:03d}"  # compteur simple

    def creer_devis(self, jeton, demande_id, devis, lignes):  # enregistre un devis fictif
        identifiant = _nouvel_id()  # identifiant unique
        self.devis_par_id[identifiant] = {"id": identifiant, "demande_id": demande_id, "numero": self.prochain_numero(jeton), "version": 1, "statut": "brouillon", "date_emission": "2026-10-26", "lignes": lignes, **devis}  # enregistre
        return identifiant  # identifiant du devis

    def changer_statut_devis(self, jeton, identifiant, statut):  # change le statut d'un devis fictif
        self.devis_par_id[identifiant]["statut"] = statut  # écrit le statut

    def modifier_devis(self, jeton, identifiant, devis, lignes):  # met à jour un devis fictif
        self.devis_par_id[identifiant].update({**devis, "lignes": lignes})  # écrase

    # ------------------------------------------------------------ stratégie
    def _charger_strategie(self):  # charge le plan Excel (fichier JSON) la première fois seulement
        if hasattr(self, "_actions"):  # déjà chargé
            return  # rien à faire
        import json  # lecture du fichier
        import os  # chemin du fichier
        chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategie_donnees.json")  # à côté de ce fichier
        with open(chemin, encoding="utf-8") as fichier:  # ouverture
            contenu = json.load(fichier)  # lecture
        self._actions = {}  # actions par identifiant
        for action in contenu["actions"]:  # chaque action du plan
            identifiant = _nouvel_id()  # identifiant unique
            self._actions[identifiant] = {"id": identifiant, **action}  # enregistre
        self._pistes = {}  # pistes par identifiant
        for piste in contenu["pistes"]:  # chaque piste
            identifiant = _nouvel_id()  # identifiant unique
            self._pistes[identifiant] = {"id": identifiant, "personne": None, "lieu": None, "type_piste": None, "dates_info": None, "pourquoi": None, "conditions": None, "candidature": None, "lien_malewa": None, "email": None, "telephone": None, "contact_libre": None, "site": None, "dossier_envoye": None, "date_envoi": None, "prochaine_relance": None, "notes": None, "frais_fixes": None, "frais_pct": None, "ca_hors_devis": None, "couts_hors_devis": None, **piste}  # enregistre avec valeurs par défaut
        self._journal = []  # entrées du journal
        self._kpi = {"mois": {}, "cibles": {}}  # saisies à la main

    def actions(self, jeton):  # actions dans l'ordre du plan
        self._charger_strategie()  # charge si besoin
        return sorted((dict(a) for a in self._actions.values()), key=lambda a: a["numero"] or 0)  # copies triées

    def action(self, jeton, identifiant):  # une action
        self._charger_strategie()  # charge si besoin
        action = self._actions.get(identifiant)  # cherche
        return dict(action) if action else None  # copie ou None

    def creer_action(self, jeton, valeurs):  # ajoute une action
        self._charger_strategie()  # charge si besoin
        identifiant = _nouvel_id()  # identifiant unique
        numero = max([a["numero"] or 0 for a in self._actions.values()] + [0]) + 1  # numéro suivant
        self._actions[identifiant] = {"id": identifiant, "numero": numero, **valeurs}  # enregistre
        return identifiant  # renvoie l'identifiant

    def modifier_action(self, jeton, identifiant, valeurs):  # met à jour une action
        self._actions[identifiant].update(valeurs)  # applique les changements

    def pistes(self, jeton):  # pistes, P1 d'abord
        self._charger_strategie()  # charge si besoin
        return sorted((dict(p) for p in self._pistes.values()), key=lambda p: (p["priorite"], p["nom"].lower()))  # copies triées

    def piste(self, jeton, identifiant):  # une piste
        self._charger_strategie()  # charge si besoin
        piste = self._pistes.get(identifiant) if identifiant else None  # cherche
        return dict(piste) if piste else None  # copie ou None

    def creer_piste(self, jeton, valeurs):  # ajoute une piste
        self._charger_strategie()  # charge si besoin
        identifiant = _nouvel_id()  # identifiant unique
        self._pistes[identifiant] = {"id": identifiant, "personne": None, "lieu": None, "type_piste": None, "dates_info": None, "pourquoi": None, "conditions": None, "candidature": None, "lien_malewa": None, "email": None, "telephone": None, "contact_libre": None, "site": None, "dossier_envoye": None, "date_envoi": None, "prochaine_relance": None, "notes": None, "frais_fixes": None, "frais_pct": None, "ca_hors_devis": None, "couts_hors_devis": None, **valeurs}  # enregistre
        return identifiant  # renvoie l'identifiant

    def modifier_piste(self, jeton, identifiant, valeurs):  # met à jour une piste
        self._pistes[identifiant].update(valeurs)  # applique les changements

    def demandes_de_piste(self, jeton, piste_id):  # demandes issues d'une piste, avec leur CA signé
        resultat = []  # liste à remplir
        for demande in self.demandes.values():  # parcourt les demandes
            if demande.get("piste_id") == piste_id:  # liée à cette piste
                ca = sum(float(d.get("total_ht") or 0) for d in self.devis_par_id.values() if d["demande_id"] == demande["id"] and d["statut"] == "accepte")  # CA des devis acceptés
                resultat.append({"id": demande["id"], "titre": demande["titre"], "statut": demande["statut"], "date_evenement": demande["date_evenement"], "type_evenement": demande["type_evenement"], "ca": ca})  # ligne
        return resultat  # renvoie la liste

    def journal(self, jeton, action_id=None, piste_id=None, limite=None):  # journal, récent d'abord
        self._charger_strategie()  # charge si besoin
        lignes = []  # liste à remplir
        for entree in reversed(self._journal):  # du plus récent au plus ancien
            if action_id and entree["action_id"] != action_id:  # autre action
                continue  # ignore
            if piste_id and entree["piste_id"] != piste_id:  # autre piste
                continue  # ignore
            copie = dict(entree)  # copie
            action = self._actions.get(entree["action_id"])  # action liée
            piste = self._pistes.get(entree["piste_id"])  # piste liée
            copie["strategie_actions"] = {"id": action["id"], "numero": action["numero"], "action": action["action"]} if action else None  # nom de l'action
            copie["strategie_pistes"] = {"id": piste["id"], "nom": piste["nom"]} if piste else None  # nom de la piste
            lignes.append(copie)  # ajoute
        return lignes[:limite] if limite else lignes  # applique la limite

    def ajouter_journal(self, jeton, auteur, texte, action_id=None, piste_id=None):  # ajoute une entrée
        self._charger_strategie()  # charge si besoin
        self._journal.append({"id": _nouvel_id(), "cree_le": time.strftime("%Y-%m-%dT%H:%M:%S+00:00"), "auteur": auteur, "texte": texte, "action_id": action_id, "piste_id": piste_id})  # enregistre

    def kpi_donnees(self, jeton):  # demandes et devis pour les KPI
        demandes = [{k: d.get(k) for k in ("id", "titre", "type_evenement", "statut", "recue_le", "date_evenement", "origine", "cout_total", "cout_equipe", "piste_id")} for d in self.demandes.values()]  # demandes
        devis = [{k: d.get(k) for k in ("demande_id", "statut", "date_emission", "total_ht")} for d in self.devis_par_id.values()]  # devis
        return demandes, devis  # les deux listes

    def kpi_manuel(self, jeton):  # saisies à la main
        self._charger_strategie()  # charge si besoin
        return {"mois": dict(self._kpi["mois"]), "cibles": dict(self._kpi["cibles"])}  # copie

    def sauver_kpi(self, jeton, mois, cibles):  # enregistre les saisies
        self._charger_strategie()  # charge si besoin
        for cle, valeurs in mois.items():  # un mois après l'autre
            self._kpi["mois"].setdefault(cle, {}).update(valeurs)  # fusionne
        self._kpi["cibles"].update(cibles)  # applique les cibles
