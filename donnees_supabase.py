"""Accès aux données Malewa via Supabase (connexion et tables demandes/clients)."""  # description du fichier
import os  # lecture des variables d'environnement (clés jamais écrites dans le code)
from decimal import Decimal  # montants exacts venant des calculs du devis
from supabase import create_client  # fabrique de connexion Supabase

ACTIFS = ("devis_envoye", "accepte", "acompte_recu")  # statuts qui bloquent une date (risque de double réservation)


class Donnees:  # regroupe tous les échanges avec la base
    """Chaque méthode reçoit le jeton de la personne connectée : la base applique ses droits (RLS)."""  # explication

    def __init__(self):  # exécuté une fois au démarrage de l'app
        self.url = os.environ["SUPABASE_URL"]  # adresse du projet Supabase
        self.cle = os.environ["SUPABASE_KEY"]  # clé publique (publishable), jamais la clé secrète

    def _client(self, jeton=None):  # crée une connexion, avec les droits de la personne si un jeton est fourni
        client = create_client(self.url, self.cle)  # connexion de base
        if jeton:  # si une personne est connectée
            client.postgrest.auth(jeton)  # les requêtes portent son identité : les règles RLS s'appliquent
        return client  # renvoie la connexion prête

    def connexion(self, email, mot_de_passe):  # vérifie l'e-mail et le mot de passe
        client = self._client()  # connexion sans identité
        try:  # tentative de connexion
            reponse = client.auth.sign_in_with_password({"email": email, "password": mot_de_passe})  # demande à Supabase Auth
        except Exception as erreur:  # mauvais identifiants ou service indisponible
            raise ValueError("Identifiants incorrects") from erreur  # message volontairement vague
        return self._session(reponse.session, reponse.user)  # renvoie les informations de session

    def rafraichir(self, jeton_refresh):  # obtient un nouveau jeton quand l'ancien expire
        client = self._client()  # connexion sans identité
        reponse = client.auth.refresh_session(jeton_refresh)  # demande un nouveau jeton à Supabase Auth
        return self._session(reponse.session, reponse.user)  # renvoie les informations de session

    @staticmethod
    def _session(session, utilisateur):  # met en forme les informations de session
        return {  # dictionnaire stocké dans le cookie de session
            "jeton": session.access_token,  # jeton d'accès (valable 1 heure)
            "refresh": session.refresh_token,  # jeton de renouvellement
            "expire": session.expires_at,  # date d'expiration (secondes depuis 1970)
            "id": str(utilisateur.id),  # identifiant du compte
            "email": utilisateur.email,  # adresse e-mail du compte
        }

    def profil(self, jeton, identifiant):  # lit le nom et le rôle de la personne connectée
        reponse = self._client(jeton).table("profils").select("nom, role").eq("id", identifiant).execute()  # cherche le profil
        return reponse.data[0] if reponse.data else None  # None si aucun profil : accès refusé

    def liste_demandes(self, jeton, statut=None):  # liste des demandes, avec le nom du client
        requete = self._client(jeton).table("demandes").select("*, clients(prenom, nom, entreprise)")  # demandes + client lié
        if statut:  # si un filtre est demandé
            requete = requete.eq("statut", statut)  # garde ce statut seulement
        demandes = requete.execute().data  # exécute la requête
        demandes.sort(key=lambda d: (d["date_evenement"] is None, d["date_evenement"] or ""))  # date la plus proche d'abord, sans date à la fin
        return demandes  # renvoie la liste

    def demande(self, jeton, identifiant):  # lit une demande avec son client complet
        reponse = self._client(jeton).table("demandes").select("*, clients(*)").eq("id", identifiant).execute()  # demande + client
        return reponse.data[0] if reponse.data else None  # None si introuvable

    def dates_prises(self, jeton, date_iso, exclure=None):  # autres demandes actives le même jour
        if not date_iso:  # pas de date, pas de conflit possible
            return []  # liste vide
        requete = self._client(jeton).table("demandes").select("id, titre, statut").eq("date_evenement", date_iso).in_("statut", list(ACTIFS))  # même date, statut actif
        if exclure:  # ne pas se comparer à soi-même
            requete = requete.neq("id", exclure)  # exclut la demande en cours
        return requete.execute().data  # renvoie les conflits

    def chercher_client(self, jeton, email):  # retrouve un client existant par e-mail
        if not email:  # sans e-mail, pas de recherche
            return None  # rien trouvé
        reponse = self._client(jeton).table("clients").select("id").ilike("email", email).execute()  # recherche insensible à la casse
        return reponse.data[0]["id"] if reponse.data else None  # identifiant ou None

    def creer_demande(self, jeton, client, demande):  # crée le client (si besoin) puis la demande
        base = self._client(jeton)  # connexion avec les droits de la personne
        client_id = self.chercher_client(jeton, client.get("email"))  # le client existe-t-il déjà ?
        if not client_id:  # sinon on le crée
            client_id = base.table("clients").insert(client).execute().data[0]["id"]  # insère le client
        demande["client_id"] = client_id  # relie la demande au client
        return base.table("demandes").insert(demande).execute().data[0]["id"]  # insère la demande et renvoie son identifiant

    def modifier_demande(self, jeton, identifiant, client_id, client, demande):  # met à jour la demande et son client
        base = self._client(jeton)  # connexion avec les droits de la personne
        base.table("clients").update(client).eq("id", client_id).execute()  # met à jour le client
        base.table("demandes").update(demande).eq("id", identifiant).execute()  # met à jour la demande

    def changer_statut(self, jeton, identifiant, statut):  # change l'étape d'une demande
        self._client(jeton).table("demandes").update({"statut": statut}).eq("id", identifiant).execute()  # écrit le nouveau statut

    # ------------------------------------------------------------ devis
    @staticmethod
    def _json(dictionnaire):  # prépare un dictionnaire pour l'envoi à Supabase (Decimal devient nombre)
        return {cle: (float(valeur) if isinstance(valeur, Decimal) else valeur) for cle, valeur in dictionnaire.items()}  # montants en nombres

    def reglages(self, jeton):  # lit la fiche de réglages (une seule ligne, id = 1)
        reponse = self._client(jeton).table("reglages").select("*").eq("id", 1).execute()  # lecture
        return reponse.data[0] if reponse.data else {}  # dictionnaire vide si absent

    def devis_de_demande(self, jeton, demande_id):  # liste des devis d'une demande, du plus récent au plus ancien
        return self._client(jeton).table("devis").select("id, numero, version, statut, date_emission, total_ttc").eq("demande_id", demande_id).order("cree_le", desc=True).execute().data  # lecture

    def devis(self, jeton, identifiant):  # un devis complet : lignes, demande et client
        base = self._client(jeton)  # connexion avec les droits de la personne
        reponse = base.table("devis").select("*, demandes(id, titre, lieu, date_evenement, horaire, clients(*))").eq("id", identifiant).execute()  # devis + demande + client
        if not reponse.data:  # introuvable
            return None  # rien à afficher
        devis = reponse.data[0]  # le devis
        devis["lignes"] = base.table("devis_lignes").select("*").eq("devis_id", identifiant).order("ordre").execute().data  # lignes dans l'ordre
        return devis  # devis complet

    def prochain_numero(self, jeton):  # numéro automatique AAAA-NNN fourni par la base
        return self._client(jeton).rpc("prochain_numero_devis").execute().data  # appel de la fonction SQL

    @staticmethod
    def _ecrire_lignes(base, devis_id, lignes):  # enregistre les lignes d'un devis
        if lignes:  # rien à écrire si vide
            base.table("devis_lignes").insert([Donnees._json({**ligne, "devis_id": devis_id, "ordre": ordre}) for ordre, ligne in enumerate(lignes, start=1)]).execute()  # insertion groupée

    def creer_devis(self, jeton, demande_id, devis, lignes):  # crée le devis et ses lignes
        base = self._client(jeton)  # connexion avec les droits de la personne
        donnees = self._json({**devis, "demande_id": demande_id, "numero": self.prochain_numero(jeton)})  # ajoute le numéro automatique
        identifiant = base.table("devis").insert(donnees).execute().data[0]["id"]  # insère le devis
        try:  # puis ses lignes
            self._ecrire_lignes(base, identifiant, lignes)  # insertion des lignes
        except Exception:  # échec : on retire le devis incomplet
            base.table("devis").delete().eq("id", identifiant).execute()  # nettoyage
            raise  # l'erreur remonte
        return identifiant  # identifiant du devis

    def modifier_devis(self, jeton, identifiant, devis, lignes):  # met à jour le devis et remplace ses lignes
        base = self._client(jeton)  # connexion avec les droits de la personne
        base.table("devis").update(self._json(devis)).eq("id", identifiant).execute()  # met à jour le devis
        base.table("devis_lignes").delete().eq("devis_id", identifiant).execute()  # retire les anciennes lignes
        self._ecrire_lignes(base, identifiant, lignes)  # écrit les nouvelles lignes
