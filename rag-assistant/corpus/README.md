# Corpus libre de l'assistant

Déposer ici des textes supplémentaires (`.md` ou `.txt`) à indexer en plus des documents
de l'équipe listés dans [`app/config.py`](../app/config.py) : par exemple le **PCA/PRA**,
des procédures d'exploitation ou une FAQ d'incident.

Relancer ensuite `just assistant-index` pour les prendre en compte.

Ce dossier est en lecture seule du point de vue de l'assistant : il ne fait qu'y lire.
Ce fichier `README.md` est lui-même indexé ; le retirer n'a pas d'importance.
