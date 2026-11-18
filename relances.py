"""Rappels de relance : repère les devis envoyés restés sans réponse."""  # description du fichier
import datetime  # calcul du nombre de jours écoulés

DELAI_PAR_DEFAUT = 5  # jours d'attente avant relance si le réglage n'existe pas encore


def a_relancer(demandes, devis_envoyes, delai, aujourdhui=None):  # renvoie les demandes à relancer, les plus en retard d'abord
    aujourdhui = aujourdhui or datetime.date.today()  # date du jour (modifiable pour les tests)
    dernier_envoi = {}  # demande_id vers date du devis envoyé le plus récent
    for devis in devis_envoyes:  # chaque devis au statut « envoyé »
        brut = str(devis.get("date_emission") or "")[:10]  # date au format AAAA-MM-JJ
        try:  # lecture de la date
            jour = datetime.date.fromisoformat(brut)  # convertit le texte en date
        except ValueError:  # date absente ou illisible : ce devis est ignoré
            continue  # devis suivant
        identifiant = devis["demande_id"]  # demande concernée
        if identifiant not in dernier_envoi or jour > dernier_envoi[identifiant]:  # garde le plus récent
            dernier_envoi[identifiant] = jour  # mémorise la date
    resultat = []  # liste finale
    for demande in demandes:  # demandes au statut « devis envoyé »
        jour = dernier_envoi.get(demande["id"])  # date d'envoi du dernier devis
        if jour is None:  # aucun devis envoyé daté : rien à calculer
            continue  # demande suivante
        attente = (aujourdhui - jour).days  # jours écoulés depuis l'envoi
        if attente >= delai:  # délai atteint ou dépassé
            resultat.append({"demande": demande, "jours": attente, "depuis": jour})  # à relancer
    resultat.sort(key=lambda r: -r["jours"])  # les plus anciens d'abord
    return resultat  # renvoie la liste
