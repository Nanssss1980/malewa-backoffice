"""Phrases proposées pour la lettre d'introduction du devis (cases à cocher)."""  # description du fichier


def liste(demande, adultes, enfants, personnes):  # renvoie les phrases : (identifiant, texte, marque « à valider »)
    date = demande.get("date_evenement_fr") or "la date à confirmer"  # date lisible
    lieu = demande.get("lieu") or "le lieu à confirmer"  # lieu de l'événement
    return [
        ("a", f"Votre événement aura lieu le {date} (lieu : {lieu}).", ""),
        ("b", f"Le nombre de convives sera de {adultes} adultes et {enfants} enfants. Conformément à nos conditions générales, les enfants sont comptés à raison d'une demi-tête : le devis est proposé pour {personnes} personnes.", ""),
        ("c", "Nous nous chargerons de l'élaboration, du dressage et du service sur plateau de l'apéritif et au buffet des mets choisis, le matériel de service étant fourni par nos soins.", ""),
        ("d", "Le dessert est fourni par vos soins.", ""),
        ("e", "Le lieu disposant d'une cuisine professionnelle, nous y cuisinerons sur place dès le matin.", ""),
        ("f", "Le lieu ne disposant pas de cuisine, une préparation en amont est prévue, dont nous convenons ensemble les détails.", "à valider"),
        ("g", "Vous souhaitez également des boissons maison (Bissap et Tangawisi) pour l'apéritif.", ""),
        ("h", "Vous avez également souhaité une proposition pour le service des boissons lors de l'apéritif et à table, ainsi que pour le débarras et le nettoyage de la vaisselle (détail ci-dessous).", ""),
        ("i", "Un plat de champignons (pleurotes) est prévu pour les personnes végétariennes.", "à valider"),
        ("j", "Le nombre final de convives peut nous être communiqué au plus tard 15 jours avant l'événement, conformément à nos conditions générales.", "à valider"),
    ]  # la phrase sur les CGV jointes est ajoutée automatiquement quand la case « Joindre les CGV » est cochée


PHRASE_CGV = "Nos conditions générales sont jointes à ce courriel."  # ajoutée si les CGV sont jointes
