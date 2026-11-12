# -*- coding: utf-8 -*-
"""Conditions générales Malewa 2026, mises en page dans l'identité du devis (jointes au PDF si la case est cochée)."""
from reportlab.lib.units import mm  # millimètres
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, Spacer, Table, TableStyle  # éléments de mise en page
from pdf_devis import ETIQUETTE, ENCRE, GRIS, INDIGO, LARGEUR, OR, TRAIT, style, t  # styles et couleurs du devis

TITRE = style("cg_titre", fontName="Bodoni", fontSize=15, leading=18, textColor=INDIGO, spaceAfter=1.5 * mm)  # titre de la première page
INTRO = style("cg_intro", fontSize=9, leading=12.5, textColor=GRIS, spaceAfter=4 * mm)  # phrase d'introduction
LISTE = style("cg_liste", fontSize=9, leading=12.6, leftIndent=5 * mm, spaceAfter=0.8 * mm)  # ligne de liste
H = style("cg_h", fontName="Bodoni", fontSize=11.5, leading=14, textColor=INDIGO, spaceAfter=1.5 * mm)  # titre de clause
TXT = style("cg_txt", fontSize=9, leading=12.6, spaceAfter=1.8 * mm)  # texte de clause
PUCE = style("cg_puce", fontName="FigtreeGras", fontSize=9, leading=12.6, textColor=INDIGO, spaceAfter=1 * mm)  # sous-titre (puce)


def clauses(d):  # liste des clauses : (titre, [paragraphes]) ; "- " au début = sous-titre
    r = d.get("reglages") or {}  # réglages de l'entreprise
    return [
        ("Prix", [
            "Nos prix sont communiqués sur demande et sont fonction du nombre de personnes mais également du marché car nous nous efforçons de travailler avec des produits frais et de saison et garantissons que tout est fait maison.",
            "Lorsque le prix est proposé par personne, un tarif de 50% dudit prix est pratiqué pour les enfants jusqu’à 12 ans et la quantité ainsi adaptée afin d’éviter le gaspillage alimentaire. Il convient dès lors au client de nous indiquer le nombre d’enfants concernés.",
            "Tous nos prix s’entendent en franc suisse (CHF), hors TVA. Conformément à la loi et si nécessaire, les taux de TVA en vigueur sont appliqués : <b>8,1%</b> aux prestations avec personnel de service, <b>2,6%</b> aux prestations sans personnel de service."]),
        ("Offre / devis", [
            "À la demande du client, un devis est établi conformément à ses souhaits. Sauf indication contraire, notre offre est valable pendant la durée indiquée sur le devis, à compter de sa date d’émission.",
            "Le devis ne tient pas lieu de réservation, cette dernière n’intervenant qu’après le retour dudit devis et des présentes conditions générales datés et signés.",
            "Chaque offre mise à jour annule la précédente, la date du document faisant foi.",
            "Un acompte de 10% de la valeur totale de la commande est demandé au client au moment de la confirmation afin de réserver la date."]),
        ("Dégustation", [
            "Une dégustation est possible pour deux personnes. Elle est offerte par Malewa Sàrl."]),
        ("Facturation et délais de paiement", [
            "Le nombre de convives définitif doit nous parvenir au plus tard 15 jours avant la date de l’événement et servira de base à la facturation finale.",
            "Si ce nombre devait être dépassé lors de l’événement, Malewa Sàrl se réserve le droit de facturer ce dépassement au client à hauteur du prix moyen devisé par personne pour la prestation.",
            "L’acompte de 10% de la valeur totale de la commande est à régler lors de la confirmation. Un acompte de 60% de la valeur totale de la commande doit nous parvenir au plus tard 30 jours avant la date de l’événement.",
            "Le solde, équivalant à 30% de la valeur totale de la commande, est à régler au plus tard le jour de l’événement."]),
        ("Produits – matières premières", [
            "Malewa Sàrl s’efforce de travailler avec des produits frais et de saison, aussi se réserve-t-elle la possibilité de modifier le menu en fonction de la disponibilité de ces produits."]),
        ("Organisation de l’événement", [
            "La réservation du lieu de l’événement et le règlement de la location sont aux soins du client, qui, de ce fait, assume toute responsabilité sur les dommages pouvant être occasionnés au lieu par les convives.",
            "Les détails organisationnels tels que lieu, horaires, animation(s) prévue(s), etc. doivent être communiqués à Malewa Sàrl au plus tard 15 jours avant la date de l’événement."]),
        ("Annulation", [
            "- Par le client",
            "En cas d’annulation par le client, quelle qu’en soit la cause, la moitié de l’acompte de 10% versé à l’acceptation du devis, soit 5% du montant total de la prestation, reste en tout état de cause acquise à Malewa Sàrl à titre de participation forfaitaire aux frais de traitement du dossier.",
            "L’acompte de 10% versé lors de la confirmation sera acquis à Malewa Sàrl à titre d’indemnité forfaitaire en cas d’annulation par le client moins de 30 jours avant la date de l’événement.",
            "En cas d’annulation intervenant moins de 15 jours avant la date de l’événement, 70% de la valeur totale de la commande sera acquise à Malewa Sàrl à titre d’indemnités.",
            "La totalité de la valeur de la commande sera due en cas d’annulation intervenant moins de 48 heures avant la date de l’événement.",
            "- Par Malewa Sàrl",
            "Toute annulation incombant à Malewa Sàrl entraînera la restitution de toutes les sommes versées par le client, à l’exclusion de toute autre indemnité."]),
        ("Service", [
            "Lorsque la prestation comprend le service, le personnel sera engagé pour un minimum de 2 heures. Le nombre de personnes nécessaires au service sera estimé par Malewa Sàrl afin de garantir le bon déroulement de votre événement.",
            f"Le service est facturé au tarif horaire de CHF {t(d.get('tarif_h', 35))}.- par personnel de service, porté à CHF {t(d.get('tarif_hn', 42))}.- par personnel à partir de 22h."]),
        ("Retard ou non-respect de l’horaire", [
            "Le client s’engage à respecter strictement les horaires de début, de service et de fin de l’événement tels qu’indiqués au devis ou lors des discussions.",
            "Tout retard imputable au client entraînant une prolongation de la présence du personnel, du service ou de la mise à disposition du matériel pourra faire l’objet d’une facturation complémentaire, calculée sur la base du tarif horaire en vigueur pour le personnel et les prestations concernées, toute heure entamée étant due.",
            "En cas de modification d’horaire supérieure à 30 minutes sans accord préalable écrit de Malewa Sàrl, cette dernière se réserve le droit de facturer au client les frais supplémentaires engendrés (heures supplémentaires du personnel, surcoûts logistiques, etc.)."]),
        ("Matériel", [
            "Lorsque la prestation comprend le service, le matériel-buffet est inclus dans l’offre, notamment les plats réchauds, plateaux, chauffe-plats, supports à apéritifs, pinces à ciseaux et autres plats et couverts de service.",
            "- Location",
            "Les assiettes, couverts et verres peuvent être loués à un prix (sur demande) fonction de la qualité et de la quantité souhaitée.",
            "Lorsque la prestation de Malewa Sàrl ne comprend pas le service, le matériel-buffet énuméré ci-dessus peut être loué à un prix (sur demande) fonction de la qualité et de la quantité souhaitée.",
            "Le matériel loué doit être restitué propre et en bon état au plus tard 7 jours après l’événement. Le cas échéant, le nettoyage du matériel restitué sale sera facturé au prix de CHF 50.-/heure.",
            "- Perte et casse",
            "Le matériel perdu ou cassé par le client ou les convives lors de l’événement ou lors de la location sera facturé au client en supplément."]),
        ("Boissons et droit de bouchon", [
            "À la demande du client, Malewa Sàrl se charge de fournir et de servir les boissons à un tarif préalablement convenu avec le client.",
            "Lorsque les boissons sont fournies par le client, aucun droit de bouchon n’est demandé lorsque Malewa Sàrl ne s’occupe pas du service desdites boissons.",
            "Un droit de bouchon pourra être appliqué en fonction des prestations supplémentaires que requiert le service de boissons, notamment le transport, l’entreposage, la réfrigération et l’évacuation des déchets."]),
        ("Déplacement et transport", [
            "Les frais de déplacement dépendent de la zone du lieu de l’événement. Ils couvrent la durée du trajet et l’essence, ainsi que le déplacement du personnel de service et du matériel.",
            "* Lausanne et Pully : déplacement gratuit.",
            "* Zone 1, jusqu’à 15 km autour de Lausanne : CHF 20.-.",
            "* Zone 2, de 15 à 20 km : CHF 30.-.",
            "* Zone 3, de 20 à 25 km : CHF 40.-.",
            "* Zone 4, au-delà de 25 km : sur devis.",
            "Le client devra prévoir une place de parc pour le(s) véhicule(s) de transport. Le cas échéant, les frais de parking seront facturés au client."]),
        ("Tri et élimination des déchets", [
            "Lorsque la préparation et/ou le service se font au lieu de l’événement, le client met à la disposition de Malewa Sàrl le matériel nécessaire au tri des déchets.",
            "L’élimination des déchets est à la charge du client. Toute élimination par nos soins sera facturée au prix forfaitaire de CHF 50.-."]),
        ("Marque Malewa et droit à l’image", [
            "Toutes les photos présentes dans ce document ou sur notre site sont la propriété de Malewa Sàrl. Ces photos ne sont pas contractuelles.",
            "L’utilisation du nom et du logo « Malewa » est assujettie à un accord préalable.",
            "Lors de chaque événement, Malewa Sàrl est libre de présenter son nom de manière claire aux convives."]),
        ("Réclamations et litige", [
            "Toute réclamation sur la prestation fournie devra être effectuée par écrit dans un délai de 24 heures suivant la prestation.",
            "Toute contestation concernant la facture devra être formulée par écrit et ne pourra plus être prise en compte passé le délai de 7 jours après la prestation.",
            "À défaut de règlement amiable, le for juridique est Lausanne et seul le droit suisse est applicable."]),
    ]


def bloc_clause(n, titre, paragraphes):  # une clause numérotée
    tete = Table([[Paragraphe_num(n), Paragraph(t(titre), H)]], colWidths=[9 * mm, LARGEUR - 9 * mm])  # numéro doré + titre
    tete.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))  # sans marges
    corps = [Paragraph("• " + t(p[2:]), PUCE) if p.startswith("- ") else Paragraph("•&nbsp;&nbsp;" + t(p[2:]), LISTE) if p.startswith("* ") else Paragraph(p.replace("&", "&amp;").replace("&amp;amp;", "&amp;"), TXT) for p in paragraphes]  # textes (le gras <b> du taux de TVA est conservé)
    if len(corps) <= 7:  # clause courte : elle reste d'un seul bloc
        return [KeepTogether([tete] + corps), Spacer(1, 3 * mm)]
    return [KeepTogether([tete] + corps[:2]), *corps[2:], Spacer(1, 3 * mm)]  # le titre reste avec les deux premiers paragraphes


def Paragraphe_num(n):  # numéro de clause en doré
    return Paragraph("%02d" % n, style("cg_n", fontName="FigtreeGras", fontSize=9, leading=14, textColor=OR, charSpace=1))


def pages_cgv(d):  # éléments à ajouter au PDF : CG numérotées + zone de signature
    contenu = [Paragraph("CONDITIONS GÉNÉRALES 2026", ETIQUETTE), Spacer(1, 1.5 * mm), Paragraph('Conditions générales <font name="FigtreeSemi" size="10" color="#5b5778">· Malewa Sàrl</font>', TITRE),
               Paragraph("Sauf accord particulier, les présentes conditions générales font partie intégrante de toutes les prestations de Malewa Sàrl.", INTRO),
               HRFlowable(width="100%", thickness=0.8, color=TRAIT, spaceAfter=4 * mm)]  # en-tête
    for n, (titre, paragraphes) in enumerate(clauses(d), 1):  # chaque clause
        contenu += bloc_clause(n, titre, paragraphes)
    signature = Table([[Paragraph("<b>Conditions générales lues et approuvées</b>", style("cg_s1", fontSize=9.5, textColor=INDIGO))],
                       [Paragraph("Lieu, date et signature :", style("cg_s2", fontSize=9, textColor=GRIS))], [Spacer(1, 11 * mm)]], colWidths=[LARGEUR])  # zone de signature
    signature.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, TRAIT), ("LINEABOVE", (0, 0), (-1, 0), 2.2, OR), ("LEFTPADDING", (0, 0), (-1, -1), 4.5 * mm), ("TOPPADDING", (0, 0), (-1, -1), 2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1 * mm)]))  # encadré
    contenu += [Spacer(1, 2 * mm), KeepTogether([signature])]
    return contenu
