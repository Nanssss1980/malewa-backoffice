"""Stratégie Malewa : listes de choix et calculs des KPI, à partir des demandes et des devis du back-office."""  # description du fichier
import datetime  # dates du plan (mois, échéances)
from decimal import Decimal  # montants exacts (CA)

AXES = [("mariages", "Mariages & +70"), ("festivals", "Festivals"), ("prive_entreprise", "Privé & entreprise"), ("commande_simple", "Commande simple"), ("popup", "Pop-up & collab"), ("pilotage", "Pilotage"), ("marque", "Marque & site")]  # les 7 axes du plan, comme dans l'Excel
LIBELLE_AXE = dict(AXES)  # code vers libellé
AXES_CA = [code for code, _ in AXES[:5]]  # les 5 axes qui produisent du chiffre d'affaires
AXES_MANUELS = ("commande_simple", "popup")  # CA qui ne vient pas des devis : saisi à la main chaque mois
STATUTS_ACTION = [("a_faire", "À faire"), ("en_cours", "En cours"), ("fait", "Fait"), ("abandonne", "Abandonné")]  # étapes d'une action
LIBELLE_STATUT_ACTION = dict(STATUTS_ACTION)  # code vers libellé
PRIORITES = [("P1", "P1 · en premier"), ("P2", "P2 · important"), ("P3", "P3 · si le temps")]  # priorités du plan
CATEGORIES = [("festival", "Festivals & événements"), ("planner", "Wedding planners"), ("salon", "Salons, lieux & annuaires"), ("entreprise", "Entreprises & réseaux")]  # les 4 listes de pistes
LIBELLE_CATEGORIE = dict(CATEGORIES)  # code vers libellé
STATUTS_PISTE = [("a_faire", "À faire"), ("contacte", "Contacté"), ("en_discussion", "En discussion"), ("retenu", "Retenu"), ("abandonne", "Abandonné")]  # étapes d'une piste (un petit entonnoir commercial)
LIBELLE_STATUT_PISTE = dict(STATUTS_PISTE)  # code vers libellé
DOSSIERS = [("", "Aucun"), ("festival", "Dossier festival"), ("pro", "Dossier événements professionnels"), ("mariage", "Brochure mariage")]  # PDF que Malewa envoie
LIBELLE_DOSSIER = dict(DOSSIERS)  # code vers libellé
DOSSIER_CONSEILLE = {"festival": "festival", "entreprise": "pro", "planner": "mariage"}  # quel dossier envoyer selon la liste
TYPE_VERS_AXE = {"mariage": "mariages", "festival": "festivals", "evenement_prive": "prive_entreprise", "evenement_entreprise": "prive_entreprise"}  # type de demande vers axe du plan
SIGNES = ("accepte", "acompte_recu")  # statuts de demande qui comptent comme signés
DEVIS_ENVOYES = ("envoye", "accepte", "refuse")  # statuts de devis qui comptent comme « envoyés » (pas les brouillons ni les remplacés)
MOIS_COURTS = ["Janv.", "Févr.", "Mars", "Avr.", "Mai", "Juin", "Juil.", "Août", "Sept.", "Oct.", "Nov.", "Déc."]  # mois abrégés comme dans l'Excel


def mois_du_plan():  # les 14 mois du plan : nov. 2026 à déc. 2027
    mois = []  # liste à remplir
    annee, numero = 2026, 11  # point de départ
    while (annee, numero) <= (2027, 12):  # jusqu'à décembre 2027
        mois.append(f"{annee}-{numero:02d}")  # clé AAAA-MM
        annee, numero = (annee + 1, 1) if numero == 12 else (annee, numero + 1)  # mois suivant
    return mois  # renvoie la liste


def libelle_mois(cle):  # 2027-03 devient « Mars 2027 »
    return f"{MOIS_COURTS[int(cle[5:7]) - 1]} {cle[:4]}"  # mois abrégé + année


def cle_mois(valeur):  # extrait AAAA-MM d'une date ou d'un horodatage (None si vide)
    return str(valeur)[:7] if valeur else None  # les 7 premiers caractères


def montant(valeur):  # convertit en Decimal sans erreur (None devient 0)
    return Decimal(str(valeur)) if valeur not in (None, "") else Decimal("0")  # valeur exacte


def calculer_kpi(demandes, devis, manuel, cibles):  # calcule tout le tableau de suivi
    par_demande = {d["id"]: d for d in demandes}  # retrouve une demande par son identifiant
    lignes = {cle: {"mois": cle, "libelle": libelle_mois(cle), "demandes": 0, "devis_envoyes": 0, "devis_signes": 0, "taux": None, "ca": {axe: Decimal("0") for axe in AXES_CA}, "ca_autre": Decimal("0"), "ca_paye": Decimal("0"), "ca_cout": Decimal("0"), "couts": Decimal("0"), "avis_google": None} for cle in mois_du_plan()}  # une ligne vide par mois
    for demande in demandes:  # demandes reçues, par mois de réception
        cle = cle_mois(demande.get("recue_le"))  # mois de réception
        if cle in lignes:  # dans la période du plan
            lignes[cle]["demandes"] += 1  # une de plus
    couts_comptes = set()  # demandes dont les coûts sont déjà comptés (une seule fois, même avec plusieurs devis)
    for un_devis in devis:  # devis envoyés et signés, par mois d'émission
        cle = cle_mois(un_devis.get("date_emission"))  # mois d'émission
        if cle in lignes and un_devis["statut"] in DEVIS_ENVOYES:  # devis réellement envoyé
            lignes[cle]["devis_envoyes"] += 1  # un de plus
            if un_devis["statut"] == "accepte":  # signé
                lignes[cle]["devis_signes"] += 1  # un de plus
        if un_devis["statut"] == "accepte":  # le CA vient des devis acceptés, au mois de l'événement
            demande = par_demande.get(un_devis["demande_id"])  # demande liée
            cle_evt = cle_mois(demande.get("date_evenement")) if demande else None  # mois de l'événement
            if cle_evt in lignes:  # dans la période du plan
                if demande.get("cout_total") is not None and demande["id"] not in couts_comptes:  # coûts saisis, pas encore comptés
                    couts_comptes.add(demande["id"])  # compte une seule fois
                    lignes[cle_evt]["ca_cout"] += montant(un_devis.get("total_ht"))  # CA comparable aux coûts
                    lignes[cle_evt]["couts"] += montant(demande["cout_total"])  # coûts de l'événement
                if demande["statut"] == "acompte_recu":  # l'acompte est encaissé : le CA est confirmé
                    lignes[cle_evt]["ca_paye"] += montant(un_devis.get("total_ht"))  # compte aussi dans « acompte reçu »
                axe = TYPE_VERS_AXE.get(demande["type_evenement"])  # axe correspondant
                if axe:  # type connu
                    lignes[cle_evt]["ca"][axe] += montant(un_devis.get("total_ht"))  # ajoute le montant hors taxes
                else:  # type « Autre »
                    lignes[cle_evt]["ca_autre"] += montant(un_devis.get("total_ht"))  # compté à part
    for cle, ligne in lignes.items():  # complète chaque mois
        saisie = manuel.get(cle, {})  # valeurs saisies à la main
        ligne["avis_google"] = saisie.get("avis_google")  # avis Google cumulés
        ligne["charges"] = montant(saisie.get("charges_fixes"))  # charges fixes du mois (saisies à la main)
        ligne["marge"] = ligne["ca_cout"] - ligne["couts"]  # marge des événements dont les coûts sont saisis
        for axe in AXES_MANUELS:  # CA hors devis
            ligne["ca"][axe] = montant(saisie.get("ca_" + axe))  # valeur saisie
        ligne["taux"] = (Decimal(ligne["devis_signes"]) / ligne["devis_envoyes"] * 100) if ligne["devis_envoyes"] else None  # taux de signature en %
        ligne["ca_total"] = sum(ligne["ca"].values(), Decimal("0")) + ligne["ca_autre"]  # CA total du mois
    liste = list(lignes.values())  # lignes dans l'ordre des mois
    en_2027 = [ligne for ligne in liste if ligne["mois"].startswith("2027")]  # le total de l'Excel ne couvre que 2027
    total = {"demandes": sum(l["demandes"] for l in en_2027), "devis_envoyes": sum(l["devis_envoyes"] for l in en_2027), "devis_signes": sum(l["devis_signes"] for l in en_2027)}  # totaux d'activité 2027
    total["taux"] = (Decimal(total["devis_signes"]) / total["devis_envoyes"] * 100) if total["devis_envoyes"] else None  # taux 2027
    total["ca"] = {axe: sum((l["ca"][axe] for l in en_2027), Decimal("0")) for axe in AXES_CA}  # CA 2027 par axe
    total["ca_autre"] = sum((l["ca_autre"] for l in en_2027), Decimal("0"))  # CA 2027 autres types
    total["ca_cout"] = sum((l["ca_cout"] for l in en_2027), Decimal("0"))  # CA des événements dont les coûts sont saisis
    total["marge"] = total["ca_cout"] - sum((l["couts"] for l in en_2027), Decimal("0"))  # marge 2027 sur ces événements
    total["charges"] = sum((l["charges"] for l in en_2027), Decimal("0"))  # charges fixes 2027
    total["resultat"] = total["marge"] - total["charges"]  # résultat estimé : marge moins charges fixes
    total["taux_marge"] = (total["marge"] / total["ca_cout"] * 100) if total["ca_cout"] else None  # marge moyenne en % du CA
    total["seuil"] = (total["charges"] / (total["taux_marge"] / 100)) if total["taux_marge"] and total["taux_marge"] > 0 and total["charges"] else None  # CA à signer pour couvrir les charges fixes
    total["ca_paye"] = sum((l["ca_paye"] for l in en_2027), Decimal("0"))  # dont CA avec acompte reçu
    total["ca_total"] = sum(total["ca"].values(), Decimal("0")) + total["ca_autre"]  # CA 2027 total
    objectifs = []  # cibles 2027 par axe
    for axe in AXES_CA:  # un axe après l'autre
        cible = cibles.get(axe)  # cible saisie (None si pas encore fixée)
        realise = total["ca"][axe]  # réalisé 2027
        objectifs.append({"axe": axe, "libelle": LIBELLE_AXE[axe], "cible": cible, "realise": realise, "ecart": (realise - montant(cible)) if cible else None, "pourcent": (realise / montant(cible) * 100) if cible else None})  # une ligne par axe
    cible_totale = sum((montant(o["cible"]) for o in objectifs if o["cible"]), Decimal("0"))  # somme des cibles
    return {"lignes": liste, "total": total, "objectifs": objectifs, "cible_totale": cible_totale, "pourcent_total": (total["ca_total"] / cible_totale * 100) if cible_totale else None}  # tout le calcul


def statistiques_origine(demandes, devis, origines):  # demandes, signatures et CA par origine (« comment nous a-t-il connus ? »)
    ca_par_demande = {}  # CA des devis acceptés, par demande
    for un_devis in devis:  # parcourt les devis
        if un_devis["statut"] == "accepte":  # seulement les signés
            ca_par_demande[un_devis["demande_id"]] = ca_par_demande.get(un_devis["demande_id"], Decimal("0")) + montant(un_devis.get("total_ht"))  # additionne
    lignes = {code: {"code": code, "libelle": nom, "demandes": 0, "signees": 0, "ca": Decimal("0")} for code, nom in origines}  # une ligne par origine
    for demande in demandes:  # parcourt les demandes
        ligne = lignes[demande.get("origine") or ""]  # ligne de son origine (vide = non précisé)
        ligne["demandes"] += 1  # une demande de plus
        if demande["statut"] in SIGNES:  # signée
            ligne["signees"] += 1  # une de plus
        ligne["ca"] += ca_par_demande.get(demande["id"], Decimal("0"))  # CA de la demande
    return [ligne for ligne in lignes.values() if ligne["demandes"]]  # seulement les origines utilisées


def en_retard(action, aujourdhui=None):  # vrai si l'échéance est passée et l'action pas terminée
    aujourdhui = aujourdhui or datetime.date.today()  # date du jour
    if action["statut"] in ("fait", "abandonne") or not action.get("echeance"):  # terminée ou sans échéance
        return False  # pas en retard
    return datetime.date.fromisoformat(str(action["echeance"])[:10]) < aujourdhui  # échéance dépassée


def statistiques_type(demandes, devis, types):  # taux de signature et panier moyen par type d'événement
    par_demande = {d["id"]: d for d in demandes}  # retrouve une demande par son identifiant
    lignes = {code: {"code": code, "libelle": nom, "demandes": 0, "devis_envoyes": 0, "devis_signes": 0, "ca": Decimal("0"), "ca_avec_couts": Decimal("0"), "couts": Decimal("0"), "evenements_avec_couts": 0} for code, nom in types}  # une ligne par type
    for demande in demandes:  # compte les demandes
        if demande["type_evenement"] in lignes:  # type connu
            lignes[demande["type_evenement"]]["demandes"] += 1  # une de plus
    for un_devis in devis:  # compte les devis
        demande = par_demande.get(un_devis["demande_id"])  # demande liée
        if not demande or demande["type_evenement"] not in lignes or un_devis["statut"] not in DEVIS_ENVOYES:  # inconnu, brouillon ou remplacé
            continue  # ignoré
        ligne = lignes[demande["type_evenement"]]  # ligne du type
        ligne["devis_envoyes"] += 1  # devis envoyé
        if un_devis["statut"] == "accepte":  # devis signé
            ligne["devis_signes"] += 1  # un de plus
            ligne["ca"] += montant(un_devis.get("total_ht"))  # CA hors taxes
            if demande.get("cout_total") is not None:  # les coûts de cet événement sont saisis
                ligne["ca_avec_couts"] += montant(un_devis.get("total_ht"))  # CA comparable aux coûts
                ligne["couts"] += montant(demande["cout_total"])  # coûts de l'événement
                ligne["evenements_avec_couts"] += 1  # un événement de plus avec ses coûts
    for ligne in lignes.values():  # calcule les moyennes
        ligne["taux"] = (Decimal(ligne["devis_signes"]) / ligne["devis_envoyes"] * 100) if ligne["devis_envoyes"] else None  # taux de signature
        ligne["panier"] = (ligne["ca"] / ligne["devis_signes"]) if ligne["devis_signes"] else None  # panier moyen par devis signé
        ligne["marge"] = (ligne["ca_avec_couts"] - ligne["couts"]) if ligne["evenements_avec_couts"] else None  # marge, seulement sur les événements dont les coûts sont saisis
        ligne["marge_pct"] = (ligne["marge"] / ligne["ca_avec_couts"] * 100) if ligne["evenements_avec_couts"] and ligne["ca_avec_couts"] else None  # marge en % du CA
    return [ligne for ligne in lignes.values() if ligne["demandes"]]  # seulement les types utilisés


def demandes_par_piste(demandes, devis):  # regroupe, par piste, les demandes liées avec leur CA signé (devis acceptés)
    ca_par_demande = {}  # CA des devis acceptés, par demande
    for un_devis in devis:  # parcourt les devis
        if un_devis["statut"] == "accepte":  # seulement les signés
            ca_par_demande[un_devis["demande_id"]] = ca_par_demande.get(un_devis["demande_id"], Decimal("0")) + montant(un_devis.get("total_ht"))  # additionne
    groupes = {}  # résultat : identifiant de piste vers liste de demandes
    for demande in demandes:  # parcourt les demandes
        if demande.get("piste_id"):  # liée à une piste
            groupes.setdefault(demande["piste_id"], []).append({"ca": ca_par_demande.get(demande["id"], Decimal("0")), "cout_total": demande.get("cout_total")})  # ajoute
    return groupes  # renvoie les groupes


def bilan_piste(piste, liees):  # bilan d'une piste : CA, coûts, frais d'inscription, résultat (None si rien n'est saisi)
    ca_devis = sum((montant(d["ca"]) for d in liees), Decimal("0"))  # CA signé par devis
    if not (ca_devis or any(piste.get(cle) is not None for cle in ("frais_fixes", "frais_pct", "ca_hors_devis", "couts_hors_devis"))):  # aucune donnée financière
        return None  # rien à afficher
    ca_total = ca_devis + montant(piste.get("ca_hors_devis"))  # CA des devis + ventes sur place
    couts = sum((montant(d["cout_total"]) for d in liees if d["ca"]), Decimal("0")) + montant(piste.get("couts_hors_devis"))  # coûts des événements signés + coûts du stand
    frais_pct = ca_total * montant(piste.get("frais_pct")) / 100  # part du CA reversée à l'organisateur
    frais = montant(piste.get("frais_fixes")) + frais_pct  # frais d'inscription totaux
    return {"ca_devis": ca_devis, "ca_hors_devis": montant(piste.get("ca_hors_devis")), "ca_total": ca_total, "couts": couts, "frais_fixes": montant(piste.get("frais_fixes")), "frais_pct_montant": frais_pct, "frais": frais, "resultat": ca_total - couts - frais}  # bilan complet


def a_completer(demandes, aujourdhui=None):  # ce qu'il manque dans les demandes : coûts des événements passés, origine des demandes actives
    aujourdhui = (aujourdhui or datetime.date.today()).isoformat()  # date du jour au format texte
    sans_couts = [d for d in demandes if d["statut"] in SIGNES and d.get("date_evenement") and str(d["date_evenement"]) < aujourdhui and d.get("cout_total") is None]  # événements passés sans coûts
    sans_origine = [d for d in demandes if d["statut"] not in ("refuse", "annule") and not d.get("origine")]  # demandes sans origine
    return {"sans_couts": sans_couts, "sans_origine": sans_origine}  # les deux listes
