// Aperçu en direct du devis : reprend les mêmes règles que calcul.py (le serveur recalcule à l'enregistrement)
(function () {
  var formulaire = document.getElementById('formulaire-devis'); // formulaire de devis
  if (!formulaire) { return; } // autre page : rien à faire

  function nombre(nom) { // lit un champ en nombre positif (accepte 12'000 et 12,5)
    var champ = formulaire.elements[nom]; // champ du formulaire
    if (!champ) { return 0; } // champ absent
    var x = parseFloat(String(champ.value).replace(/['’\s]/g, '').replace(',', '.')); // nettoie puis convertit
    return isFinite(x) && x > 0 ? x : 0; // négatif ou invalide : zéro
  }
  function arrondi(x) { return Math.round(x * 100 + 1e-9) / 100; } // arrondi au centime
  function chf(x) { // CHF 1'234.50
    var parties = x.toFixed(2).split('.'); // sépare francs et centimes
    return 'CHF ' + parties[0].replace(/\B(?=(\d{3})+(?!\d))/g, "'") + '.' + parties[1]; // apostrophe pour les milliers
  }
  function afficher(nom, texte) { // écrit une valeur dans tous les emplacements qui la demandent
    var cibles = formulaire.querySelectorAll('[data-sortie="' + nom + '"]'); // emplacements
    for (var i = 0; i < cibles.length; i++) { cibles[i].textContent = texte; } // met à jour
  }

  function recalculer() { // refait tous les calculs
    var tarifH = nombre('tarif_h'); // tarif de jour
    var tarifHn = nombre('tarif_hn'); // tarif de nuit
    afficher('personnes', String(nombre('adultes') + nombre('enfants') / 2)); // enfant = demi-tête
    var nourriture = arrondi(nombre('forfait_nourriture')); // forfait nourriture
    var services = []; // montants retenus des deux services
    ['s1', 's2'].forEach(function (cle) { // pour chaque ligne de service
      var pers = nombre(cle + '_pers'); var h = nombre(cle + '_h'); var hn = nombre(cle + '_hn'); // saisie
      var calcule = pers > 0 && h + hn > 0 ? arrondi(pers * (h * tarifH + hn * tarifHn)) : 0; // montant au tarif horaire
      var forfait = arrondi(nombre(cle + '_forfait')); // forfait proposé
      var retenu = pers > 0 && h + hn > 0 ? (forfait > 0 ? forfait : calcule) : 0; // le forfait remplace le calcul
      afficher(cle + '_calcule', chf(calcule)); afficher(cle + '_retenu', chf(retenu)); // affichage
      services.push(retenu); // mémorise
    });
    var debarras = arrondi(nombre('debarras')); // forfait débarras
    var km = nombre('km'); var vehicules = nombre('vehicules'); // distance et véhicules
    var deplacement = km > 0 && vehicules > 0 ? arrondi(km * 2 * vehicules * nombre('tarif_km')) : 0; // aller-retour
    var totalHt = nourriture + services[0] + services[1] + debarras + deplacement; // somme des lignes
    var tva = formulaire.elements['tva_on'].checked ? arrondi(totalHt * nombre('taux_tva') / 100) : 0; // TVA facultative
    var total = totalHt + tva; // total à payer
    var a1 = arrondi(total * nombre('p1') / 100); var a2 = arrondi(total * nombre('p2') / 100); // acomptes
    var a3 = total - a1 - a2; // solde : le reste exact
    afficher('nourriture', chf(nourriture)); afficher('debarras_montant', chf(debarras)); afficher('deplacement', chf(deplacement)); // lignes
    afficher('total_ht', chf(totalHt)); afficher('montant_tva', chf(tva)); afficher('total_ttc', chf(total)); // totaux
    afficher('a1', chf(a1)); afficher('a2', chf(a2)); afficher('a3', chf(a3)); // échéancier
    afficher('p3', String(arrondi(100 - nombre('p1') - nombre('p2')))); // pourcentage du solde
  }

  var civilite = formulaire.elements['civilite']; // liste de civilité
  if (civilite) { civilite.addEventListener('change', function () { // la formule d'appel suit la civilité
    formulaire.elements['formule_appel'].value = civilite.options[civilite.selectedIndex].getAttribute('data-appel'); // ex. Chère Madame,
  }); }

  formulaire.addEventListener('input', recalculer); // à chaque frappe
  formulaire.addEventListener('change', recalculer); // à chaque case cochée
  recalculer(); // premier affichage
})();
