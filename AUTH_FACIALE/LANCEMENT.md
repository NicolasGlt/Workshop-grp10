# Fiche de lancement

Ordre à suivre sur le PC Hôte, le jour de la démo ou après un redémarrage. Compter environ 2 minutes.

## 1. Matériel

- Webcam USB branchée sur le PC Hôte.
- Carte ESP8266 branchée en USB (elle n'a besoin du câble que pour l'alimentation, le pilotage passe par le Wi-Fi).
- Vérifier que la LED est bien en place sur la plaque (pattes sur D7, D5, résistance vers G).

## 2. Point d'accès

Paramètres Windows → Réseau et Internet → Point d'accès sans fil mobile :

- interrupteur **activé** ;
- réseau `RESILIENCE-G10`, bande **2,4 GHz** ;
- économie d'énergie désactivée.

L'ESP se reconnecte seul en quelques secondes. Vérification, dans un terminal PowerShell :

```powershell
curl.exe http://192.168.137.200/health
```

Réponse attendue : `{"mode":"off","rssi":...}`. Rien ne répond : le point d'accès est coupé, ou la carte n'est pas alimentée.

## 3. Application

Prérequis : la stack `poc-resilience` tourne (`docker compose ps` : `db` en healthy), car les comptes, les visages et le journal sont dans sa base. Le fichier `AUTH_FACIALE\.env` contient `BACKOFFICE_DB_PASSWORD`, la même valeur que dans `poc-resilience\.env`. Vérification : `http://127.0.0.1:8000/api/health` doit répondre `"database": true`.

Dans un terminal PowerShell (pas besoin d'être administrateur) :

```powershell
cd "<chemin du dépôt>\AUTH_FACIALE"
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Laisser ce terminal ouvert pendant toute la démo. Au démarrage, la caméra s'allume une seconde (ouverture « à blanc ») puis s'éteint : c'est normal.

## 4. Vérifications avant de passer devant le jury

1. Ouvrir http://127.0.0.1:8000 : la page de connexion s'affiche.
2. Se connecter une fois avec `jeremy` (visage + mot de passe) pour valider la chaîne complète, puis se déconnecter.
3. Dans « Gestion des habilitations », cliquer sur « Tester la LED » : vert clignotant, puis rouge ×10.
4. Vérifier qu'aucun compte n'est bloqué (colonne « État »).

## En cas de problème

| Symptôme | Cause probable | Action |
|---|---|---|
| La LED ne réagit plus | Point d'accès coupé | Le réactiver, attendre 10 s |
| « Caméra indisponible » | Webcam débranchée ou prise par une autre application (Teams…) | Rebrancher, fermer l'autre application |
| « Poste occupé » | 30 s de rouge ou attente du mot de passe en cours | Attendre la fin du compte à rebours |
| Compte bloqué 5 min | 2 échecs sur cet identifiant | Bouton « Débloquer » dans les habilitations (avec un autre admin), ou attendre |
| Seul admin bloqué | 2 échecs sur `jeremy` | Attendre 5 min ; prévoir un 2e compte admin pour éviter ce cas |
| Le serveur ne démarre pas (port 8000 occupé) | Une ancienne instance tourne encore | Fermer l'autre terminal, ou `Get-NetTCPConnection -LocalPort 8000` pour trouver le processus |
