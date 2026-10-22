#!/bin/sh
# nginx ne résout qu'une fois, au démarrage, un nom écrit en dur dans proxy_pass. Après un
# redémarrage de Docker ou du PC, les conteneurs reprennent des IP dans un autre ordre et le
# WAF envoyait vers une IP qui n'était plus celle du frontend : 502 sans fin. Avec une
# variable, nginx résout via le resolver Docker déjà configuré par l'image (valid=5s),
# comme le fait frontend/nginx.conf pour l'api.
set -e
sed -i 's#^proxy_pass \(.*\);$#set $backend \1; proxy_pass $backend;#' /etc/nginx/includes/proxy_backend.conf
