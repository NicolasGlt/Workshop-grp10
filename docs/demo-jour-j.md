# Démo du jour J

Fiche à suivre sur le PC Hôte (Windows, Docker Desktop), du déballage au passage devant le jury. Le back-office a sa propre fiche détaillée : [auth-faciale/docs/lancement.md](../auth-faciale/docs/lancement.md).

## Matériel

| Élément | Où | Contrôle |
|---|---|---|
| PC Hôte | Windows, Docker Desktop démarré, dépôt à jour, `.env` remplis | `just --list` répond |
| PC Attaquant | connecté uniquement au point d'accès `RESILIENCE-G10` | reçoit une IP en 192.168.137.0/24 |
| Webcam USB | branchée sur le PC Hôte | aucune autre application ne l'utilise (Teams…) |
| ESP8266 et LED | USB du PC Hôte, pour l'alimentation | `curl.exe http://192.168.137.200/health` |
| Câble secteur | les deux PC branchés | |

## Minute par minute

| Quand | Action | Résultat attendu |
|---|---|---|
| J − 30 min | Démarrer Docker Desktop, attendre « Engine running » | |
| J − 28 min | Paramètres Windows, Point d'accès sans fil mobile : activé, `RESILIENCE-G10`, bande 2,4 GHz, économie d'énergie désactivée | l'ESP se reconnecte en quelques secondes |
| J − 27 min | `just demo-prep` à la racine du dépôt | conteneurs sains, puis « Détecteur entraîné », puis la liste des URL (environ 5 min, 2 min d'apprentissage compris) |
| J − 20 min | `just smoke` | toutes les lignes en OK |
| J − 18 min | Dans un second terminal : `just backoffice` (le laisser ouvert) | http://127.0.0.1:8000 affiche la connexion |
| J − 15 min | Une connexion complète au back-office avec `jeremy`, test de la LED, déconnexion | vert clignotant puis vert fixe |
| J − 10 min | Ouvrir les onglets : Boutique (8082), NovaPay (8083), back-office (8000), Grafana dashboards 01 et 07 | Grafana : Origine sur `client` |
| J − 5 min | Ne plus rien lancer. Vérifier dans Grafana 07 : « Modèle entraîné » = 1 | |
| J | Démo, dans l'ordre ci-dessous | |

`just demo-prep` refait `just up`, sans perte de données : il peut être relancé à tout moment pour reprendre l'état.

## Ordre de la démo

| # | Montrer | Commande ou geste | Durée |
|---|---|---|---|
| 1 | Architecture : PC Hôte, PC Attaquant, point d'accès | schéma du [README](../README.md#architecture) | 2 min |
| 2 | Un achat client de bout en bout | Boutique, carte `5555 5555 5555 4444`, puis la transaction dans Grafana 01 | 2 min |
| 3 | Un paiement 3DS | Boutique avec la carte d'Alice `4242 4242 4242 4242`, validation dans NovaPay | 2 min |
| 4 | L'authentification forte du back-office | identifiant, visage, LED verte clignotante, mot de passe, LED verte fixe | 3 min |
| 5 | L'incident et la reprise autonome | `just demo`, Grafana 07 ouvert à côté | 2 min |
| 6 | La preuve de reprise | dernier paiement de `just demo` approuvé, IP bloquée dans Grafana 07 | 1 min |

## Grafana pendant l'incident (dashboard 07 · Résilience)

| Panneau | Ce qu'on dit |
|---|---|
| Modèle entraîné | à 1 avant de lancer : le détecteur a appris la normale du trafic simulé |
| Débit observé (req/s) | le flood fait sortir le débit de la normale apprise |
| Score d'anomalie et Drapeau anomalie | le Local Outlier Factor classe le point comme anormal, sans seuil écrit à la main |
| Remédiations déclenchées, Actions de remédiation | ml-detector appelle la remédiation Ansible, sans humain |
| IP bloquées actuellement | l'IP de l'attaquant est bloquée au WAF (`FLOOD_ACTION=block_ip`) |
| Disponibilité API | le service reste ou revient à 1 |
| Journal de la boucle autonome | la chaîne détection, décision, action, horodatée |

Le trafic simulé (service `traffic`) fait vivre la normale : il passe par le WAF comme un marchand, mais ses paiements portent `origin="simulated"` et ses transactions sont préfixées `[SIM]`. Les dashboards 00 et 01 ne montrent que les paiements clients par défaut, la variable **Origine des paiements** permet d'afficher le trafic simulé ou tout le trafic.

## Plan B

| Symptôme | Cause probable | Action |
|---|---|---|
| `just demo-prep` bloque sur les conteneurs | un conteneur redémarre en boucle | `just ps`, puis `just logs <service>` |
| `just demo-prep` bloque sur l'apprentissage | ml-detector ne lit pas Prometheus, ou pas de trafic | `just logs ml-detector traffic`, vérifier http://localhost:9090 |
| Grafana vide | Prometheus ou Loki pas encore prêt | attendre 1 min, recharger |
| `just demo` répond « détecteur non entraîné » | stack redémarrée il y a moins de 2 min | relancer `just demo-prep`, qui attend l'apprentissage |
| Pas de remédiation pendant le flood | normale apprise pendant une charge inhabituelle | `just down`, `just demo-prep`, ne rien lancer pendant l'apprentissage |
| Back-office : caméra indisponible, LED muette, compte bloqué | voir la fiche | [auth-faciale/docs/lancement.md](../auth-faciale/docs/lancement.md#en-cas-de-problème) |
| Tout est cassé à J − 5 min | | dérouler la démo à l'oral sur le schéma d'architecture et les dashboards |
