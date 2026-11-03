# Journal de veille BTS CG

Site de veille (comptabilité, fiscalité, social, alternance), mis à jour automatiquement toutes les heures par GitHub.

Adresse du site : https://kirai76.github.io/veille-bts-cg/

## Fichiers

- `template.html` : la page. Le texte et le design se modifient ici.
- `data/journal.json` : les « Repères » écrits à la main. Ajoute-y une entrée pour une nouvelle info importante.
- `scripts/build.py` : collecte les actualités et construit le site. La liste des sujets suivis est dans `QUERIES`.
- `.github/workflows/update.yml` : lance la mise à jour toutes les heures.

## Si le site ne se met plus à jour

GitHub arrête les mises à jour planifiées d'un dépôt public après 60 jours sans activité. Ici le robot enregistre les nouveaux articles dans `data/news.json`, ce qui compte comme activité. En cas d'arrêt : onglet **Actions**, puis **Mise à jour du site**, puis **Run workflow**.
