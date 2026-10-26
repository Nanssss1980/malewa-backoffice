"""Calculs du devis : lignes, totaux, TVA et acomptes (une seule source de vérité, côté serveur)."""  # description du fichier
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation  # Decimal évite les erreurs d'arrondi des nombres à virgule

CENTIME = Decimal("0.01")  # précision d'un montant en francs
ZERO = Decimal("0")  # valeur nulle
CENT = Decimal("100")  # pour les pourcentages


def dec(valeur, libelle, erreurs):  # lit un nombre saisi (accepte 12'000 et 12,5), renvoie 0 si vide
    brut = str("" if valeur is None else valeur).strip().replace("'", "").replace("’", "").replace(" ", "").replace(",", ".")  # nettoie le texte
    if not brut:  # champ vide
        return ZERO  # compte pour zéro
    try:  # conversion
        nombre = Decimal(brut)  # texte vers Decimal
    except InvalidOperation:  # pas un nombre
        erreurs.append(f"{libelle} : nombre attendu.")  # message d'erreur
        return ZERO  # valeur de repli
    if nombre < 0:  # négatif interdit
        erreurs.append(f"{libelle} : le nombre ne peut pas être négatif.")  # message d'erreur
        return ZERO  # valeur de repli
    return nombre  # nombre valide


def r2(nombre):  # arrondit au centime (0.5 vers le haut)
    return nombre.quantize(CENTIME, rounding=ROUND_HALF_UP)  # deux décimales


def propre(nombre):  # 5.0 devient "5", 2.5 reste "2.5" (pour les textes)
    return format(nombre.normalize(), "f")  # écriture sans zéros inutiles (100 reste 100, 2.50 devient 2.5)


def calculer(s):  # s : dictionnaire des champs saisis (texte). Renvoie (résultat, erreurs)
    erreurs = []  # messages à afficher
    adultes = dec(s.get("adultes"), "Adultes", erreurs)  # nombre d'adultes
    enfants = dec(s.get("enfants"), "Enfants", erreurs)  # nombre d'enfants
    personnes = adultes + enfants / 2  # un enfant compte pour une demi-tête
    tarif_h = dec(s.get("tarif_h"), "Tarif horaire", erreurs)  # tarif de jour
    tarif_hn = dec(s.get("tarif_hn"), "Tarif horaire après 22 h", erreurs)  # tarif de nuit
    lignes = []  # lignes du devis, dans l'ordre d'affichage

    nourriture = dec(s.get("forfait_nourriture"), "Forfait nourriture et boissons", erreurs)  # forfait saisi à la main
    if nourriture > 0:  # ligne présente seulement si un montant est saisi
        lignes.append({"categorie": "forfait", "libelle": (s.get("forfait_libelle") or "Forfait nourriture et boissons").strip(), "details": None, "quantite": None, "prix_unitaire": None, "forfait_propose": None, "montant": r2(nourriture)})  # ligne forfait

    for cle, defaut in (("s1", "Service apéritif"), ("s2", "Service buffet et dessert")):  # deux lignes de service possibles
        pers = dec(s.get(cle + "_pers"), "Personnes", erreurs)  # nombre de personnes de service
        heures = dec(s.get(cle + "_h"), "Heures", erreurs)  # heures avant 22 h
        nuit = dec(s.get(cle + "_hn"), "Heures après 22 h", erreurs)  # heures après 22 h
        forfait = dec(s.get(cle + "_forfait"), "Forfait proposé", erreurs)  # prix forfaitaire facultatif
        if pers > 0 and (heures + nuit) > 0:  # ligne utile seulement avec des personnes et des heures
            calcule = r2(pers * (heures * tarif_h + nuit * tarif_hn))  # montant au tarif horaire
            heures_totales = pers * (heures + nuit)  # heures cumulées de toute l'équipe
            detail = f"{propre(pers)} pers. x {propre(heures)} h" + (f" + {propre(nuit)} h après 22 h" if nuit > 0 else "")  # texte explicatif
            lignes.append({  # ligne de service
                "categorie": "horaire", "libelle": (s.get(cle + "_libelle") or defaut).strip(), "details": detail,
                "quantite": heures_totales, "prix_unitaire": tarif_h if nuit == 0 else r2(calcule / heures_totales),
                "forfait_propose": r2(forfait) if forfait > 0 else None, "montant": r2(forfait) if forfait > 0 else calcule,  # le forfait remplace le calcul
            })

    debarras = dec(s.get("debarras"), "Débarras et vaisselle", erreurs)  # forfait débarras
    if debarras > 0:  # ligne présente seulement si un montant est saisi
        lignes.append({"categorie": "forfait", "libelle": "Débarras et vaisselle (forfait)", "details": None, "quantite": None, "prix_unitaire": None, "forfait_propose": None, "montant": r2(debarras)})  # ligne débarras

    km = dec(s.get("km"), "Kilomètres", erreurs)  # distance aller simple
    vehicules = dec(s.get("vehicules"), "Véhicules", erreurs)  # nombre de véhicules
    tarif_km = dec(s.get("tarif_km"), "Tarif au kilomètre", erreurs)  # tarif au km
    if km > 0 and vehicules > 0:  # ligne présente seulement avec une distance
        km_total = km * 2 * vehicules  # aller-retour, tous véhicules
        lignes.append({"categorie": "kilometrique", "libelle": "Frais de déplacement", "details": f"{propre(km)} km x 2 x {propre(vehicules)} véhicule(s)", "quantite": km_total, "prix_unitaire": tarif_km, "forfait_propose": None, "montant": r2(km_total * tarif_km)})  # ligne déplacement

    total_ht = sum((ligne["montant"] for ligne in lignes), ZERO)  # somme des lignes
    soumis_tva = s.get("tva_on") == "on"  # TVA facturée ou non
    taux = dec(s.get("taux_tva"), "Taux de TVA", erreurs)  # taux saisi
    if taux > 100:  # taux absurde
        erreurs.append("Taux de TVA : doit être entre 0 et 100.")  # message d'erreur
    montant_tva = r2(total_ht * taux / CENT) if soumis_tva else ZERO  # TVA calculée
    total_ttc = total_ht + montant_tva  # total à payer
    p1 = dec(s.get("p1"), "Acompte 1 (%)", erreurs)  # pourcentage du premier acompte
    p2 = dec(s.get("p2"), "Acompte 2 (%)", erreurs)  # pourcentage du deuxième acompte
    if p1 + p2 > 100:  # plus de 100 % avant le solde
        erreurs.append("Acomptes : le total des deux acomptes dépasse 100 %.")  # message d'erreur
    a1 = r2(total_ttc * p1 / CENT)  # premier acompte
    a2 = r2(total_ttc * p2 / CENT)  # deuxième acompte
    a3 = total_ttc - a1 - a2  # solde : le reste exact, pour éviter tout écart d'arrondi
    if not lignes:  # devis vide
        erreurs.append("Ajoute au moins une ligne au devis (forfait, service, débarras ou déplacement).")  # message d'erreur
    return {"lignes": lignes, "personnes": personnes, "total_ht": total_ht, "soumis_tva": soumis_tva, "taux_tva": taux, "montant_tva": montant_tva, "total_ttc": total_ttc, "p1": p1, "p2": p2, "p3": CENT - p1 - p2, "a1": a1, "a2": a2, "a3": a3}, erreurs  # résultat complet
