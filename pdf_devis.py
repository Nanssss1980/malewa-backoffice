"""PDF du devis Malewa (3 pages A4), généré avec ReportLab : Python pur, léger, sans navigateur ni programme système."""  # description du fichier
import io  # fichier en mémoire (le PDF n'est jamais écrit sur le disque du serveur)
import os  # chemins des polices et du logo
from decimal import Decimal, ROUND_HALF_UP  # montants exacts et arrondi au centime
from xml.sax.saxutils import escape  # protège les textes saisis (&, <, >) dans les paragraphes
from reportlab.lib import colors  # couleurs
from reportlab.lib.enums import TA_RIGHT  # alignement à droite
from reportlab.lib.pagesizes import A4  # format de page
from reportlab.lib.styles import ParagraphStyle  # styles de texte
from reportlab.lib.units import mm  # millimètres
from reportlab.pdfbase import pdfmetrics  # enregistrement des polices
from reportlab.pdfbase.ttfonts import TTFont  # polices TrueType
from reportlab.pdfgen import canvas  # dessin bas niveau (pieds de page)
from reportlab.platypus import BaseDocTemplate, Frame, HRFlowable, Image, KeepTogether, ListFlowable, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle  # éléments de mise en page

DOSSIER = os.path.dirname(os.path.abspath(__file__))  # dossier de l'app
INDIGO = colors.HexColor("#21184B")  # couleur principale du site
OR = colors.HexColor("#C6A624")  # accent or
ENCRE = colors.HexColor("#1d1a33")  # texte courant
GRIS = colors.HexColor("#5b5778")  # texte secondaire
TRAIT = colors.HexColor("#e4e1ee")  # filets
TEINTE = colors.HexColor("#f6f5fa")  # fond clair
LARGEUR = 174 * mm  # largeur utile : A4 moins deux marges de 18 mm

for nom, fichier in (("Bodoni", "bodoni-moda-700.ttf"), ("BodoniNoir", "bodoni-moda-900.ttf"), ("Figtree", "figtree-400.ttf"), ("FigtreeSemi", "figtree-600.ttf"), ("FigtreeGras", "figtree-700.ttf")):  # polices du site
    pdfmetrics.registerFont(TTFont(nom, os.path.join(DOSSIER, "polices", fichier)))  # enregistre chaque police
pdfmetrics.registerFontFamily("Figtree", normal="Figtree", bold="FigtreeGras", italic="Figtree", boldItalic="FigtreeGras")  # le gras <b> utilise Figtree 700


def chf(valeur):  # 12000 devient 12'000.00
    return f"{Decimal(str(valeur)):,.2f}".replace(",", "'")  # apostrophe suisse pour les milliers


def t(valeur):  # protège un texte saisi pour l'insérer dans un paragraphe
    return escape(str(valeur or ""))  # remplace &, < et >


def style(nom, **options):  # fabrique un style de texte avec les réglages communs
    base = {"fontName": "Figtree", "fontSize": 9.5, "leading": 13.5, "textColor": ENCRE}  # valeurs par défaut
    base.update(options)  # réglages propres au style
    return ParagraphStyle(nom, **base)  # style prêt à l'emploi


NORMAL = style("normal", spaceAfter=3 * mm)  # texte courant
PETIT = style("petit", fontSize=8.3, leading=11, textColor=GRIS)  # texte secondaire
CELLULE = style("cellule", fontSize=8.6, leading=11.5)  # texte des tableaux
CELLULE_GRAS = style("cellule_gras", fontName="FigtreeGras", fontSize=8.6, leading=11.5, textColor=INDIGO)  # première colonne
TITRE_SECTION = style("section", fontName="Bodoni", fontSize=15, leading=18, textColor=INDIGO, spaceAfter=4 * mm)  # titre de page
ETIQUETTE = style("etiquette", fontName="FigtreeGras", fontSize=7.8, leading=10, textColor=OR, charSpace=1.4)  # petits titres dorés


def en_tete_page_1(d):  # logo, marque, titre « Devis » et numéro
    logo = os.path.join(DOSSIER, "static", "logo-malewa.png")  # logo rond de Malewa
    marque = [Image(logo, width=30 * mm, height=30 * mm, hAlign="LEFT"), Spacer(1, 2 * mm),  # logo
              Paragraph("MALEWA", style("m", fontName="BodoniNoir", fontSize=15, leading=18, textColor=INDIGO, charSpace=2.6)),  # nom
              Paragraph("SERVICE TRAITEUR", style("s", fontName="FigtreeSemi", fontSize=7.2, leading=9, textColor=GRIS, charSpace=2.2))]  # sous-titre
    droite = [Paragraph("PROPOSITION", style("k", fontName="FigtreeGras", fontSize=8, leading=10, textColor=OR, charSpace=2.6, alignment=TA_RIGHT)),  # surtitre
              Paragraph("Devis", style("h", fontName="Bodoni", fontSize=26, leading=30, textColor=INDIGO, alignment=TA_RIGHT)),  # titre
              Paragraph("N° " + t(d["numero"]), style("n", fontName="FigtreeSemi", fontSize=11, leading=14, textColor=INDIGO, alignment=TA_RIGHT))]  # numéro
    tableau = Table([[marque, droite]], colWidths=[LARGEUR / 2, LARGEUR / 2])  # deux colonnes
    tableau.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))  # sans marges
    return tableau  # bloc d'en-tête


def bloc_infos(d):  # objet, date, lieu à gauche ; adresse du client à droite
    lignes = [[Paragraph("<b>Objet</b>", style("o1", textColor=INDIGO)), Paragraph(t(d["objet"]), NORMAL)],  # objet
              [Paragraph("<b>Date</b>", style("o2", textColor=INDIGO)), Paragraph(t(d["date_evt"]), NORMAL)],  # date
              [Paragraph("<b>Lieu</b>", style("o3", textColor=INDIGO)), Paragraph(t(d["lieu_evt"]), NORMAL)]]  # lieu
    gauche = Table(lignes, colWidths=[14 * mm, 70 * mm])  # petit tableau sans bordures
    gauche.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))  # sans marges
    client = d["client_lignes"]  # lignes d'adresse
    texte_client = [Paragraph("<b>" + t(client[0]) + "</b>", style("c0", textColor=INDIGO, spaceAfter=1 * mm))] if client else []  # nom en gras
    texte_client += [Paragraph(t(ligne), style("c" + str(i), leading=12.5)) for i, ligne in enumerate(client[1:], start=1)]  # adresse, e-mail, téléphone
    texte_client += [Spacer(1, 3 * mm), Paragraph(t(d["ville_date"]), PETIT)]  # lieu et date d'émission
    droite = Table([[texte_client]], colWidths=[72 * mm])  # encadré gris à filet indigo
    droite.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TEINTE), ("LINEBEFORE", (0, 0), (0, -1), 3.4, INDIGO), ("LEFTPADDING", (0, 0), (-1, -1), 5 * mm), ("TOPPADDING", (0, 0), (-1, -1), 4 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm)]))  # mise en forme
    ensemble = Table([[gauche, droite]], colWidths=[LARGEUR - 72 * mm, 72 * mm])  # deux colonnes
    ensemble.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))  # sans marges
    return ensemble  # bloc complet


def page_1(d):  # lettre d'introduction
    contenu = [en_tete_page_1(d), Spacer(1, 7 * mm), HRFlowable(width=30 * mm, thickness=3.4, color=OR, hAlign="LEFT", spaceAfter=0), Spacer(1, 6 * mm), bloc_infos(d), Spacer(1, 8 * mm)]  # haut de page
    contenu.append(Paragraph(t(d["salutation"]), NORMAL))  # formule d'appel
    if d["phrases"]:  # liste des informations à rappeler
        contenu.append(Paragraph("Suite à nos échanges, voici une première proposition qui tient compte des informations suivantes :", NORMAL))  # phrase d'accroche
        puces = [Paragraph(t(phrase), style("p", spaceAfter=1.2 * mm)) for phrase in d["phrases"]]  # une puce par phrase
        contenu.append(ListFlowable(puces, bulletType="bullet", start="•", leftIndent=5 * mm, bulletFontSize=10, bulletColor=INDIGO))  # liste à puces
        contenu.append(Spacer(1, 3 * mm))  # espace
    if d["forfait_nourriture"]:  # encadré du forfait mets et boissons
        if d.get("affichage_prix") == "par_personne" and d["personnes"]:  # option : prix par personne au lieu du total
            par_tete = (d["forfait_nourriture"] / Decimal(str(d["personnes"]))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)  # forfait divisé par le nombre de personnes, au centime
            titre_bandeau = "PRIX PAR PERSONNE, METS ET BOISSONS (" + t(d["personnes"]) + " PERSONNES)"  # libellé du bandeau
            montant_bandeau = "CHF " + chf(par_tete) + " / pers."  # montant par personne
        else:  # affichage habituel : le forfait total
            titre_bandeau = "PRIX FORFAITAIRE METS ET BOISSONS, " + t(d["personnes"]) + " PERSONNES"  # libellé du bandeau
            montant_bandeau = "CHF " + chf(d["forfait_nourriture"])  # montant total
        libelle = Paragraph(titre_bandeau, style("l", fontName="Figtree", fontSize=8.6, leading=11, textColor=colors.white, charSpace=1.3))  # libellé
        valeur = Paragraph(montant_bandeau, style("v", fontName="FigtreeGras", fontSize=11.5, leading=15, textColor=colors.white, alignment=TA_RIGHT))  # montant discret, tout en blanc
        encadre = Table([[libelle, valeur]], colWidths=[LARGEUR * 0.62, LARGEUR * 0.38])  # bandeau indigo
        encadre.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), INDIGO), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 6 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 6 * mm), ("TOPPADDING", (0, 0), (-1, -1), 3 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm)]))  # mise en forme
        contenu += [encadre, Spacer(1, 4 * mm)]  # ajoute le bandeau
    if d["deplacement"]:  # phrase sur les frais de déplacement
        ligne = d["deplacement"]  # ligne de déplacement
        contenu.append(Paragraph("Les frais de déplacement (" + t(ligne["details"]) + ", CHF " + chf(ligne["prix_unitaire"]) + "/km) s'élèvent à <b>CHF " + chf(ligne["montant"]) + "</b>.", NORMAL))  # phrase
    contenu.append(Paragraph("Votre satisfaction nous tient à cœur : nous restons à votre disposition pour toute question, modification ou ajout. Le détail de la proposition figure en page suivante.", NORMAL))  # phrase de clôture
    contenu.append(KeepTogether([Spacer(1, 3 * mm), Paragraph("Avec nos sincères salutations,", style("sal", spaceAfter=1 * mm)), Paragraph(t(d["reglages"].get("signataire_nom") or "Nady Nzita-Nanga"), style("eq", fontName="Bodoni", fontSize=12, leading=15, textColor=INDIGO)), Paragraph(t(d["reglages"].get("mention_signature") or "Malewa Service Traiteur"), PETIT)]))  # signature
    return contenu  # éléments de la page


def tarif_texte(ligne, d):  # texte de la colonne « Prix unit. »
    if ligne["categorie"] == "kilometrique":  # déplacement
        return "CHF " + chf(ligne["prix_unitaire"]) + "/km"  # tarif au kilomètre
    if ligne["forfait_propose"] or ligne["categorie"] == "forfait":  # forfait
        return "Forfait"  # pas de prix unitaire
    if "après" in (ligne.get("details") or ""):  # heures de jour et de nuit mélangées
        return "Tarif horaire"  # pas de prix unique
    return "CHF " + t(d["tarif_h"]) + ".-/h"  # tarif horaire


def quantite_texte(ligne, d):  # texte de la colonne « Qté »
    if ligne["categorie"] == "kilometrique" and ligne["quantite"] is not None:  # déplacement
        return f"{Decimal(str(ligne['quantite'])).normalize():f} km"  # kilomètres cumulés
    if ligne["categorie"] == "horaire" and ligne["quantite"] is not None:  # services
        return f"{Decimal(str(ligne['quantite'])).normalize():f} h"  # heures cumulées de l'équipe
    if ligne["libelle"].lower().startswith("forfait nourriture") or (ligne["categorie"] == "forfait" and not ligne["libelle"].lower().startswith("débarras")):  # forfait nourriture
        return t(d["personnes"]) + " pers."  # nombre de personnes facturées
    return ""  # rien


def details_cellule(ligne, d, premiere_nourriture):  # contenu de la colonne « Détails »
    elements = []  # paragraphes de la cellule
    if premiere_nourriture and d["menu_lignes"]:  # menu proposé, une puce par ligne
        elements.append(ListFlowable([Paragraph(t(m), style("mn", fontSize=8.6, leading=11.5, spaceAfter=0.6 * mm)) for m in d["menu_lignes"]], bulletType="bullet", start="•", leftIndent=4 * mm, bulletFontSize=9, bulletColor=INDIGO))  # menu
    texte = t(ligne["details"])  # détail calculé (ex. 5 pers. x 5 h)
    if ligne["categorie"] == "horaire":  # services : rappel du tarif
        texte = texte + (". " if texte else "") + "En principe au tarif horaire de CHF " + t(d["tarif_h"]) + ".- (CHF " + t(d["tarif_hn"]) + ".- dès 22 h)" + (", proposé à un prix forfaitaire." if ligne["forfait_propose"] else ".")  # phrase de tarif
    if texte:  # ajoute le texte s'il y en a
        elements.append(Paragraph(texte, CELLULE))  # paragraphe
    return elements or ""  # contenu de la cellule


def page_2(d):  # détail des lignes
    contenu = [Paragraph('Détail de la proposition <font name="FigtreeSemi" size="10" color="#5b5778">· Devis N° ' + t(d["numero"]) + "</font>", TITRE_SECTION)]  # titre
    entete_style = style("th", fontName="FigtreeGras", fontSize=7.6, leading=10, textColor=colors.white, charSpace=1.1)  # en-têtes de colonnes
    droite_style = style("thr", fontName="FigtreeGras", fontSize=7.6, leading=10, textColor=colors.white, charSpace=1.1, alignment=TA_RIGHT)  # en-têtes alignés à droite
    rangees = [[Paragraph("PRESTATION", entete_style), Paragraph("QTÉ", entete_style), Paragraph("DÉTAILS", entete_style), Paragraph("PRIX UNIT.", droite_style), Paragraph("TOTAL", droite_style)]]  # ligne d'en-tête
    montant_style = style("mt", fontName="FigtreeGras", fontSize=8.8, leading=11.5, textColor=INDIGO, alignment=TA_RIGHT)  # montants
    prix_style = style("pu", fontSize=8, leading=11, textColor=GRIS, alignment=TA_RIGHT)  # prix unitaires
    deja_menu = False  # le menu s'affiche une seule fois, sur la ligne de nourriture
    for numero, ligne in enumerate(d["lignes"], start=1):  # une rangée par ligne du devis
        nourriture = (not deja_menu) and ligne["categorie"] == "forfait" and not ligne["libelle"].lower().startswith("débarras")  # ligne du forfait nourriture
        if nourriture:  # une seule fois
            deja_menu = True  # mémorise
        rangees.append([Paragraph(f"{numero}) " + t(ligne["libelle"]), CELLULE_GRAS), Paragraph(quantite_texte(ligne, d), CELLULE), details_cellule(ligne, d, nourriture), Paragraph(tarif_texte(ligne, d), prix_style), Paragraph("CHF " + chf(ligne["montant"]), montant_style)])  # rangée
    tableau = Table(rangees, colWidths=[35 * mm, 18 * mm, 66 * mm, 24 * mm, 31 * mm], repeatRows=1)  # l'en-tête se répète sur chaque page
    tableau.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), INDIGO), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 1), (-1, -1), 0.8, TRAIT), ("TOPPADDING", (0, 0), (-1, -1), 2.4 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4 * mm), ("LEFTPADDING", (0, 0), (-1, -1), 2.6 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2.6 * mm)]))  # mise en forme
    contenu.append(tableau)  # ajoute le tableau
    return contenu  # éléments de la page


def page_3(d):  # totaux, échéancier, banque et acceptation
    contenu = [Paragraph('Conditions et paiement <font name="FigtreeSemi" size="10" color="#5b5778">· Devis N° ' + t(d["numero"]) + "</font>", TITRE_SECTION)]  # titre
    ligne_style = style("lt", fontSize=10, leading=13)  # lignes de totaux
    droite = style("ltr", fontSize=10, leading=13, alignment=TA_RIGHT)  # montants alignés à droite
    gros = style("gros", fontName="FigtreeGras", fontSize=11.5, leading=14, textColor=INDIGO)  # total général
    grosr = style("grosr", fontName="FigtreeGras", fontSize=11.5, leading=14, textColor=INDIGO, alignment=TA_RIGHT)  # total général à droite
    lignes = []  # lignes du tableau des totaux
    if d["soumis_tva"]:  # TVA facturée : détail HT, TVA, TTC
        lignes.append([Paragraph("Total hors TVA", ligne_style), Paragraph("CHF " + chf(d["total_ht"]), droite)])  # total HT
        lignes.append([Paragraph("TVA " + t(d["taux_tva"]) + " %", ligne_style), Paragraph("CHF " + chf(d["montant_tva"]), droite)])  # TVA
    lignes.append([Paragraph("TOTAL TTC" if d["soumis_tva"] else "TOTAL DE LA PRESTATION", gros), Paragraph("CHF " + chf(d["total"]), grosr)])  # total à payer
    dernier = len(lignes) - 1  # indice de la dernière ligne
    totaux = Table(lignes, colWidths=[56 * mm, 42 * mm], hAlign="RIGHT")  # tableau aligné à droite
    totaux.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, dernier - 1), 0.8, TRAIT), ("BACKGROUND", (0, dernier), (-1, dernier), TEINTE), ("LINEABOVE", (0, dernier), (-1, dernier), 2.2, OR), ("TOPPADDING", (0, 0), (-1, -1), 2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm), ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm)]))  # mise en forme
    contenu += [totaux, Spacer(1, 1.5 * mm), Paragraph(("Prix en francs suisses, TVA incluse." if d["soumis_tva"] else "Prix en francs suisses, non soumis à la TVA.") + f" Devis valable {d['validite']} jours.", style("note", fontSize=8.3, leading=11, textColor=GRIS, alignment=TA_RIGHT)), Spacer(1, 6 * mm)]  # totaux et note
    contenu.append(Paragraph("ÉCHÉANCIER DE PAIEMENT", ETIQUETTE))  # titre de section
    contenu.append(Spacer(1, 2 * mm))  # espace
    echeances = []  # lignes de l'échéancier
    if d["p1"] > 0:  # premier acompte
        echeances.append(("Acompte " + t(d["p1_txt"]) + " %", " à verser à l'acceptation du devis", d["a1"]))  # ligne 1
    if d["p2"] > 0:  # deuxième acompte
        echeances.append(("Acompte " + t(d["p2_txt"]) + " %", " à verser un mois avant l'événement", d["a2"]))  # ligne 2
    echeances.append(("Solde " + t(d["p3_txt"]) + " %", " à verser au plus tard le jour de l'événement", d["a3"]))  # solde
    rangees = [[Paragraph("<b>" + gras + "</b>" + reste, style("e", fontSize=9.2, textColor=ENCRE)), Paragraph("CHF " + chf(montant), style("er", fontName="FigtreeGras", fontSize=9.2, textColor=INDIGO, alignment=TA_RIGHT))] for gras, reste, montant in echeances]  # une rangée par échéance
    tableau = Table(rangees, colWidths=[LARGEUR - 34 * mm, 34 * mm])  # tableau de l'échéancier
    fonds = [("BACKGROUND", (0, i), (-1, i), TEINTE) for i in range(0, len(rangees), 2)]  # lignes alternées
    tableau.setStyle(TableStyle(fonds + [("LINEBELOW", (0, 0), (-1, -1), 0.8, TRAIT), ("TOPPADDING", (0, 0), (-1, -1), 2.2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2 * mm), ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm)]))  # mise en forme
    contenu += [tableau, Spacer(1, 6 * mm)]  # ajoute l'échéancier
    r = d["reglages"]  # réglages de l'entreprise
    banque = [Paragraph("COORDONNÉES BANCAIRES", ETIQUETTE), Spacer(1, 1.5 * mm), Paragraph("<b>" + t(r.get("raison_sociale") or "Malewa Sàrl") + "</b>", style("b1", fontSize=9, leading=12.5))]  # titre et nom
    for champ in ("banque", "adresse_banque"):  # banque et adresse
        if r.get(champ):  # si renseignés
            banque.append(Paragraph(t(r[champ]), style("b2", fontSize=9, leading=12.5)))  # ligne
    banque.append(Paragraph("IBAN " + t(r["iban"]) if r.get("iban") else "<i>IBAN à renseigner dans les réglages</i>", style("b3", fontSize=9, leading=12.5)))  # IBAN
    acceptation = [Paragraph("ACCEPTATION DU DEVIS", ETIQUETTE), Spacer(1, 3 * mm), Paragraph("Devis accepté le ……………………………", style("a1", fontSize=9)), Spacer(1, 8 * mm), HRFlowable(width="100%", thickness=0.8, color=ENCRE, spaceAfter=1 * mm), Paragraph("Signature", PETIT)]  # cadre de signature
    cartes = Table([[banque, acceptation]], colWidths=[LARGEUR / 2 - 3 * mm, LARGEUR / 2 - 3 * mm], hAlign="LEFT")  # deux encadrés
    cartes.setStyle(TableStyle([("BOX", (0, 0), (0, 0), 0.8, TRAIT), ("BOX", (1, 0), (1, 0), 0.8, TRAIT), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4.5 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 4.5 * mm), ("TOPPADDING", (0, 0), (-1, -1), 3.5 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5 * mm)]))  # mise en forme
    contenu.append(Table([[cartes]], colWidths=[LARGEUR], style=[("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))  # enveloppe pour garder les deux encadrés alignés
    return contenu  # éléments de la page


def generer(d):  # fabrique le PDF et renvoie ses octets
    memoire = io.BytesIO()  # fichier en mémoire
    r = d["reglages"]  # réglages de l'entreprise

    class ToileNumerotee(canvas.Canvas):  # toile qui connaît le nombre total de pages
        def __init__(self, *args, **kwargs):  # initialisation
            super().__init__(*args, **kwargs)  # parent
            self.etats = []  # mémorise chaque page avant de l'écrire

        def showPage(self):  # fin d'une page : on la mémorise au lieu de l'écrire
            self.etats.append(dict(self.__dict__))  # copie de l'état de la page
            self._startPage()  # prépare la page suivante

        def save(self):  # fin du document : on écrit chaque page avec « page n sur N »
            total = len(self.etats)  # nombre de pages
            for etat in self.etats:  # pour chaque page
                self.__dict__.update(etat)  # restaure son état
                self.pied(total)  # dessine le pied de page
                super().showPage()  # écrit la page
            super().save()  # termine le fichier

        def pied(self, total):  # pied de page
            self.setStrokeColor(TRAIT)  # couleur du filet
            self.setLineWidth(0.8)  # épaisseur
            self.line(18 * mm, 15 * mm, 192 * mm, 15 * mm)  # filet
            self.setFont("Figtree", 7.6)  # police du pied de page
            self.setFillColor(GRIS)  # couleur du texte
            if self._pageNumber == 1:  # page 1 : coordonnées de l'entreprise
                self.drawString(18 * mm, 10.5 * mm, f"{r.get('raison_sociale') or 'Malewa Sàrl'} · {r.get('adresse') or ''}")  # adresse
                self.drawRightString(192 * mm, 10.5 * mm, f"{r.get('email') or ''} · {r.get('telephone') or ''}")  # contacts
            else:  # autres pages : numéro d'identification et pagination
                self.drawString(18 * mm, 10.5 * mm, f"{r.get('raison_sociale') or 'Malewa Sàrl'} · IDE {r.get('numero_ide') or ''}")  # IDE
                self.drawRightString(192 * mm, 10.5 * mm, f"Devis N° {d['numero']} · page {self._pageNumber} sur {total}")  # pagination

    document = BaseDocTemplate(memoire, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=20 * mm, title="Devis " + str(d["numero"]) + " Malewa", author="Malewa Sàrl")  # document A4
    cadre = Frame(18 * mm, 20 * mm, LARGEUR, 297 * mm - 36 * mm, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)  # zone de texte
    document.addPageTemplates([PageTemplate(id="devis", frames=[cadre])])  # modèle unique
    document.build(page_1(d) + [PageBreak()] + page_2(d) + [PageBreak()] + page_3(d), canvasmaker=ToileNumerotee)  # assemble les trois pages
    return memoire.getvalue()  # octets du PDF
