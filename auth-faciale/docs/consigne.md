# Consigne additionnelle 1 — texte intégral

Transcription fidèle de la consigne papier (2 pages), d'après les photos `sujet-workshop/image.png` (page 1) et `sujet-workshop/IMG_5269.jpg` (page 2). Orthographe d'origine conservée.

---

**Workshop 2026-27 / M2 — Consigne Additionnelle 1**

À la suite de remontées inquiétantes du terrain concernant des attaques de sécurité physique et informatique nous vous demandons de renforcer l'authentification du back-office de notre SI.

Celui-ci intègre déjà une page dédiée d'authentification incluant identifiant / mot de passe. A cela nous vous demandons d'ajouter, juste après la saisie de l'identifiant, l'activation d'une caméra USB pour confirmer l'identificateur de l'utilisateur et si tel est le cas permettre la saisie du mot de passe. Dans le cas contraire, l'identifiant est remis à vide, la caméra s'éteint. L'utilisateur peut recommencer 1 fois puis est bloqué 5 minutes, etc.

La caméra doit OBLIGATOIREMENT être connectée sur le PC Hôte de votre solution. Pour rappel, le PC Hôte est celui qui délivre le point d'accès de votre solution, RESILIENCE-G<n> et qui héberge la solution Conteneurisée (Docker) avec son back-office, sa base de données, etc.

> Schéma de la consigne (trois encadrés) :
>
> - **PC HÔTE (OBLIGATOIRE)** : Windows + Docker Desktop (WSL2) ; SI cible, WAF, SIEM, Vault ; Prometheus / Grafana / Loki ; Moteur ML AIOps, orchestrateur, dashboard ; Connecté au WiFi du campus ; PA du groupe (Point d'accès sans fil mobile).
> - **PC ATTAQUANT (OBLIGATOIRE)** : Autre PC du groupe ; Connecté uniquement au PA du groupe ; Outils et playbooks Red Team ; Aucun composant défensif.
> - **PC DÉLESTAGE IA (OPTIONNEL)** : Troisième PC du groupe, si la RAM du PC Hôte est insuffisante ; Héberge uniquement Ollama, exposé en API sur le PA du groupe.
>
> PA du groupe RESILIENCE-G<n> (Point d'accès sans fil mobile Windows, réseau 192.168.137.0/24) — réseau du consortium.

Le PC Hôte doit donc intégrer en plus des éléments déjà demandé une IA légère capable de faire de la reconnaissance de visage. La gestion de cette reconnaissance doit être intégrée au back-office, gestion complète des habilitations.

Pour prévoir l'avenir, votre solution devra également intégrée un objet connecté ESP8266 (IDE obligatoire JETBrains CLion + PlatformIO), dans un premier ce dernier sera simplement équipé d'une LED Bicolore (rouge/vert). Ce module devra également être connecté en WiFi au point d'accès de votre solution. Par défaut la LED devra être éteinte, dès qu'une personne saisie son identifiant et qu'elle est reconnue (via la reconnaissance IA + Caméra USB), la LED passe au vert clignotant jusqu'à ce que le mot de passe soit saisie. Si le mot de passe est validé, la LED passe au vert fixe pendant 30 secondes puis s'éteint et la page du Back est disponible. Si le mot de passe n'est pas bon, la LED clignote en rouge 10 fois puis s'éteint et on recommence toute la phase identification (l'identifiant est remis à vide, la caméra s'éteint).

Sur la phase d'identification évoquée précédemment, si la personne n'est pas reconnue, la LED s'allume en rouge fixe pendant 30 secondes avant que la caméra ne s'éteigne et que ce dernier puisse ressaisir son identifiant.

Merci et soyez à l'écoute de toutes nouvelles consignes.

---

## Lecture : ce qui est imposé, ce qui reste ouvert

Imposé par le texte :

- l'ordre identifiant → caméra → mot de passe ;
- la caméra USB branchée sur le PC Hôte ;
- une IA légère de reconnaissance de visage sur le PC Hôte ;
- la gestion de la reconnaissance intégrée au back-office, avec gestion complète des habilitations ;
- l'ESP8266 développé avec CLion + PlatformIO, connecté en Wi-Fi au point d'accès du groupe ;
- les comportements de LED : éteinte par défaut ; vert clignotant après reconnaissance jusqu'au mot de passe ; vert fixe 30 s si mot de passe validé ; rouge clignotant 10 fois si mot de passe faux, puis tout recommence ; rouge fixe 30 s si non reconnu ;
- **la caméra reste allumée pendant les 30 s de rouge fixe** et ne s'éteint qu'ensuite (« avant que la caméra ne s'éteigne ») ;
- après un mot de passe faux : identifiant remis à vide et caméra éteinte.

Ouvert (nos hypothèses, voir `plan.md` section 6) :

- si l'échec de mot de passe compte dans la règle « recommencer 1 fois puis bloqué 5 minutes » ;
- si le back-office est accessible tout de suite ou seulement après les 30 s de vert (« vert fixe pendant 30 secondes puis s'éteint et la page du Back est disponible ») ;
- l'état de la LED pendant le blocage de 5 minutes ;
- le sens de « etc. » après « bloqué 5 minutes » (on le lit comme : le cycle recommence après le blocage).

À noter :

- le texte dit que le back-office est dans la solution conteneurisée (Docker). Notre partie caméra tourne hors Docker parce que Docker Desktop n'accède pas à une webcam USB : à justifier devant le jury (voir `plan.md` section 1) ;
- « Pour prévoir l'avenir » et « dans un premier [temps] » : l'ESP8266 recevra probablement d'autres consignes ; le firmware doit rester simple à étendre.
