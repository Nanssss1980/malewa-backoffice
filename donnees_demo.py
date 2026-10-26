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
            self.demandes[demande_id] = {"id": demande_id, "client_id": client_id, "titre": titre, "source": source, "type_evenement": genre, "date_evenement": date, "horaire": None, "lieu": "Lausanne", "adultes": adultes, "enfants": enfants, "budget_indique": budget, "message_client": None, "notes_internes": None, "statut": statut, "recue_le": "2026-10-20T10:00:00+00:00"}  # fiche demande

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
    def reglages(self, jeton):  # réglages fictifs
        return {"raison_sociale": "Malewa Sàrl", "adresse": "La Claie-aux-Moines 17, 1000 Lausanne 26", "numero_ide": "CHE-209.761.684", "email": "info@malewa.ch", "telephone": "+41 78 603 36 11", "mention_signature": "Malewa Service Traiteur", "tarif_horaire": 35, "tarif_horaire_nuit": 42, "tarif_km": 1.2, "taux_tva": 8.1, "validite_jours": 14, "pourcentage_acompte_1": 10, "pourcentage_acompte_2": 60}  # valeurs par défaut

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

    def modifier_devis(self, jeton, identifiant, devis, lignes):  # met à jour un devis fictif
        self.devis_par_id[identifiant].update({**devis, "lignes": lignes})  # écrase
