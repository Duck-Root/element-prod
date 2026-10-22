# Déployer une nouvelle stack Element / Matrix sur Debian

Procédure préparée le 22 octobre 2026 pour une **installation vide** sur une autre
machine. Les comptes, salons, messages, clés et secrets du POC ne sont pas copiés.
Les commandes ci-dessous sont à exécuter sur la machine de production, sauf mention
contraire. Aucun déploiement distant n’a été exécuté par cette préparation.

## 1. Périmètre et ressources

Le dossier contient PostgreSQL, Synapse, Element Web, LiveKit, le service JWT RTC,
coturn et Caddy. Authentification par mot de passe, validation des nouveaux appareils
par ancienne session ou clé de récupération. Inscriptions libres, fédération Matrix,
Scalar et serveur d’identité externe désactivés. La capacité LiveKit est configurée
à 10 participants par salle.

Réserver à la stack : **2 vCPU, 2 Go de RAM, 30 Go de SSD** pour commencer, hors OS,
autres services, sauvegardes et croissance future des médias. Il s’agit d’un point
de départ pour moins de 10 utilisateurs, pas d’une garantie de capacité. Dimensionner
la VM en ajoutant la marge nécessaire au système ; par exemple 4 Go de RAM totale
pour une VM dédiée. Prévoir un accès administrateur SSH et une IPv4 publique joignable.

Ce profil ne déploie ni Ketesa ni le récepteur Alertmanager. Ils pourront être ajoutés
ensuite avec leurs propres accès privés, en adaptant les guides du POC aux domaines
et chemins de production. Les fichiers Caddy vides prévus pour ces extensions ne
publient aucune console ni webhook.

Les images sont épinglées aux versions du POC pour rendre le premier déploiement
reproductible. Elles ne constituent pas une certification des dernières versions :
vérifier les avis de sécurité et tester les mises à jour avant une ouverture durable.

## 2. Choisir les noms définitifs

L’exemple utilise **trois noms distincts** :

| Usage | Exemple à remplacer | Variable |
|---|---|---|
| Identité / API Matrix | `matrix.exemple.fr` | `MATRIX_DOMAIN`, `SYNAPSE_URL` |
| Interface Element | `element.exemple.fr` | `ELEMENT_URL` |
| Appels et TURN | `rtc.exemple.fr` | `RTC_URL`, `TURN_HOST` |

`matrix.exemple.fr` devient une partie permanente des identifiants, par exemple
`@alice:matrix.exemple.fr`. Choisir ce nom avant de créer les comptes. **Ne pas
utiliser l’identité de la base du POC pour une nouvelle base indépendante.**

Avec DuckDNS, une variante possible est de créer un NOUVEAU domaine de base dans
votre compte, puis d’utiliser `matrix.NOUVEAU.duckdns.org`,
`element.NOUVEAU.duckdns.org` et `rtc.NOUVEAU.duckdns.org`. Les trois noms doivent
réellement résoudre vers la nouvelle IP publique. Le certificat décrit plus loin
couvre ces trois noms précis ; il ne demande pas de wildcard ni de token DuckDNS.

Créer les enregistrements DNS A pointant vers l’IPv4 publique de production.
Ne publier un AAAA que si IPv6 est effectivement routé, filtré et fonctionnel : un
AAAA incorrect peut faire échouer la validation HTTPS. En cas d’IP dynamique,
configurer séparément un mécanisme de mise à jour DNS ; le client ACME ne met pas
l’adresse publique à jour.

Sur une même IP publique, une redirection de port ne peut pas envoyer le même port
vers deux VM à la fois. Pour faire cohabiter POC et production derrière la même box,
il faut une autre IP publique ou un point d’entrée partagé adapté. Cette procédure
suppose que les ports ci-dessous peuvent être consacrés à la nouvelle machine.
La redirection du port 80 doit atteindre la nouvelle machine dès l’émission TLS.

## 3. Préparer le réseau

Si la machine est derrière un routeur, réserver son IP LAN dans le DHCP ou utiliser
une IP statique. Rediriger les ports suivants vers CETTE IP LAN, avec les mêmes
ports externes et internes et une source « Toutes » :

| Protocole | Début | Fin | Destination | Usage |
|---|---:|---:|---:|---|
| TCP | 80 | 80 | 80 | HTTP et émission/renouvellement TLS |
| TCP | 443 | 443 | 443 | Interfaces, API, WebSocket |
| TCP | 7881 | 7881 | 7881 | Média LiveKit TCP |
| UDP | 15000 | 15100 | 15000 | Média LiveKit UDP |
| UDP | 3478 | 3478 | 3478 | STUN / TURN |
| TCP | 3478 | 3478 | 3478 | TURN TCP |
| TCP | 5349 | 5349 | 5349 | TURN TLS |
| UDP | 15200 | 15300 | 15200 | Relais TURN |

Sur un serveur directement exposé, autoriser ces mêmes ports dans le pare-feu de
l’hébergeur et le filtrage de l’hôte. Garder SSH limité au réseau d’administration.
Ne publier ni 5432, ni 8008, ni 7880, ni 8080, ni 2019, ni 8448.

Les ports publiés par Docker peuvent contourner les règles UFW classiques : appliquer
le filtrage au bon niveau (pare-feu réseau/hébergeur ou règles Docker adaptées).
Ne pas supposer qu’un simple `ufw deny` protège un port Docker publié.

HTTPS sortant et résolution DNS sont nécessaires aux téléchargements et à ACME.
Les plages média doivent être routées directement, pas uniquement via un proxy HTTP.

## 4. Installer les prérequis Debian

Sur un Debian supporté, avec un utilisateur disposant de sudo :

```bash
sudo apt update
sudo apt install -y ca-certificates curl python3 openssl tar util-linux nano
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

Ajouter le dépôt Docker officiel :

```bash
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
```

Si Docker est déjà installé, vérifier sa provenance et sa compatibilité avant de
réinstaller des paquets. Ne pas mélanger sans examen Docker Debian, Docker CE et
Podman ; suivre la procédure officielle pour résoudre les conflits éventuels.

## 5. Transférer le dossier de déploiement

Depuis la machine où ce dépôt est présent, dans sa racine, créer une archive du
profil neuf uniquement (aucune donnée du POC) :

```bash
tar -czf /tmp/matrix-production-neuf.tar.gz -C deployment/production .
scp /tmp/matrix-production-neuf.tar.gz administrateur@IP_MACHINE_PRODUCTION:/tmp/
```

Sur la machine de production :

```bash
sudo install -d -m 0700 /core/docker/Element_Matrix/matric-poc-prod
sudo tar -xzf /tmp/matrix-production-neuf.tar.gz -C /core/docker/Element_Matrix/matric-poc-prod
sudo -i
cd /core/docker/Element_Matrix/matric-poc-prod
chmod 0700 scripts/*.sh scripts/*.py
cp -n .env.example .env
chmod 0600 .env
```

À partir d’ici, les blocs sont exécutés **en root** dans `/core/docker/Element_Matrix/matric-poc-prod`.
Le dossier est réservé à root car il contiendra des secrets. Ne pas y extraire de
sauvegarde du POC. Ne pas copier son `.env`, son `configs/generated/` ou son `data/`.

## 6. Renseigner la configuration

**Guide détaillé : [REMPLIR-ENV.md](REMPLIR-ENV.md)**. Il explique chaque URL,
la différence entre IP publique et locale, les ports, images et secrets. Les trois
URL servent trois fonctions sur la même machine, pas trois serveurs différents.

```bash
nano .env
```

Adapter uniquement les paramètres utiles avant le premier rendu :

```dotenv
COMPOSE_PROJECT_NAME=matric-poc-prod
MATRIX_DOMAIN=matrix.exemple.fr
SYNAPSE_URL=https://matrix.exemple.fr
ELEMENT_URL=https://element.exemple.fr
RTC_URL=https://rtc.exemple.fr
TURN_HOST=rtc.exemple.fr
SERVER_IP=VOTRE_IPV4_PUBLIQUE
BIND_IP=0.0.0.0
HTTP_PORT=80
HTTPS_PORT=443
LIVEKIT_TCP_PORT=7881
LIVEKIT_UDP_START=15000
LIVEKIT_UDP_END=15100
TURN_PORT=3478
TURN_TLS_PORT=5349
TURN_UDP_START=15200
TURN_UDP_END=15300
TLS_MODE=provided
```

Conserver les lignes d’images et les lignes de secrets vides : le rendu génère les
secrets automatiquement. Ne pas utiliser littéralement `VOTRE_IPV4_PUBLIQUE`.
`SERVER_IP` est l’IP annoncée aux clients pour les médias ; ce n’est pas l’IP LAN
quand le serveur est derrière un NAT. `BIND_IP=0.0.0.0` publie les ports sur toutes
les interfaces IPv4 de la machine.

Contrôler les noms avec vos vraies valeurs :

```bash
getent ahostsv4 matrix.exemple.fr
getent ahostsv4 element.exemple.fr
getent ahostsv4 rtc.exemple.fr
ss -lntup
```

Le port TCP 80 doit être libre sur cette machine. Vérifier les redirections depuis
un réseau extérieur ; la seule résolution DNS ne prouve pas l’accessibilité.

## 7. Émettre le certificat public

Ce profil utilise **HTTP-01** : le port public 80 doit atteindre directement le
conteneur ACME temporaire sur cette machine, pour les trois noms. Il n’utilise pas
les scripts DuckDNS spécifiques du POC. Vérifier cette condition avant l’émission
pour éviter des tentatives répétées et les limites de Let's Encrypt.

```bash
python3 scripts/tls.py issue --email administrateur@votre-domaine.fr
```

Cette commande accepte les conditions Let's Encrypt, crée un compte ACME local,
demande un certificat SAN couvrant Matrix, Element et RTC/TURN, puis vérifie la
chaîne et la correspondance clé/certificat. Les domaines du certificat apparaîtront
dans les journaux publics Certificate Transparency.

Les fichiers sont installés dans :

```text
data/tls/server.crt   certificat et intermédiaires
data/tls/server.key   clé privée
data/tls/ca.crt       racines publiques pour le service JWT
data/acme/           compte ACME et certificats de renouvellement
```

Le répertoire `data` est protégé par root. Les fichiers TLS doivent rester lisibles
par les UID des services qui montent le sous-répertoire TLS ; ne pas rendre la clé
illisible aux conteneurs en changeant ses permissions sans adapter les UID.

## 8. Générer et démarrer la stack

```bash
python3 scripts/render.py
docker compose config --quiet
docker compose pull
docker compose run --rm --no-deps proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose up -d --wait --wait-timeout 240
docker compose ps
```

Le rendu prépare les volumes, attribue `/data` Synapse à l’UID 991, génère les secrets
et écrit les configurations privées sous `configs/generated/`.

Le contrôle Caddy avant démarrage valide sa syntaxe et ses certificats ; les services
amont démarrent ensuite avec Compose. Si une image manque pour votre architecture,
résoudre sa compatibilité avant de continuer.

En cas d’échec :

```bash
docker compose logs --tail=100 postgres synapse proxy jwt livekit coturn element
```

Ne pas contourner un refus de rendu en supprimant des données. Après initialisation,
`render.py` refuse d’écraser des fichiers ou un environnement modifiés. Pour une
reconfiguration, sauvegarder et modifier les fichiers concernés de façon contrôlée,
ou reconstruire dans un autre dossier uniquement si l’installation est encore vide.

## 9. Vérifier les interfaces publiques

Depuis le serveur, si le retour NAT de votre routeur le permet :

```bash
python3 scripts/check-endpoints.py
```

Depuis un poste sur un réseau extérieur, sans Tailscale, remplacer les noms :

```bash
curl --fail https://matrix.exemple.fr/_matrix/client/versions
curl --fail https://matrix.exemple.fr/.well-known/matrix/client
curl --fail https://matrix.exemple.fr/.well-known/matrix/server
curl --fail https://rtc.exemple.fr/livekit/jwt/healthz
curl -I https://element.exemple.fr
```

Résultats attendus : API, découvertes et santé JWT en 200 ; Element accessible sans
avertissement TLS ; découverte client annonçant les URL Matrix et RTC choisies.
Si le retour NAT n’est pas disponible depuis le LAN, prévoir un DNS interne adapté
et confirmer quand même l’accès réel depuis Internet. Ne pas désactiver la validation TLS.

L’API admin et la fédération générale doivent être refusées :

```bash
curl -o /dev/null -s -w '%{http_code}\n' https://matrix.exemple.fr/_synapse/admin/v1/server_version
curl -o /dev/null -s -w '%{http_code}\n' https://matrix.exemple.fr/_matrix/federation/v1/version
```

Attendu : 404. Le seul endpoint de la famille fédération exposé est l’OpenID nécessaire
aux appels ; cela n’active pas les échanges de fédération entre serveurs.

## 10. Créer les comptes et préparer la récupération

```bash
bash scripts/create-user.sh --admin
bash scripts/create-user.sh
```

Le premier compte est administrateur du serveur, les suivants sont des utilisateurs
ordinaires. Les noms et mots de passe sont demandés en interactif. Ne pas renseigner
les mots de passe dans une commande ni réutiliser les secrets du POC.

Ouvrir `https://element.exemple.fr`, se connecter, créer un salon privé et inviter
l’autre utilisateur. Chacun doit activer la sauvegarde de ses clés dans les paramètres
de chiffrement et stocker sa clé de récupération dans un endroit sûr.
Cette clé permet de valider un nouvel appareil sans l’ancienne session.
La sauvegarde serveur ne remplace pas cette clé personnelle.

L’e-mail et MAS ne sont pas configurés dans ce profil ; il n’y a ni réinitialisation
par e-mail ni connexion par QR code.

## 11. Qualifier les appels et la charge

```bash
python3 scripts/test-rtc.py
```

Le script demande un compte de test, crée un salon temporaire et vérifie les
transports, OpenID et l’émission de jetons LiveKit, puis quitte et oublie le salon.
Il ne transporte pas de médias et ne prouve pas l’ouverture des plages UDP.

Faire ensuite une recette entre au moins deux postes, dont un hors LAN/Tailscale :
messages, 20 photos, téléchargement d’un fichier, appel audio, caméra, partage d’écran.
Faire aussi un appel au nombre maximal de participants prévu, pendant 10–15 minutes.

```bash
docker stats $(docker compose ps -q)
docker compose logs --tail=50 livekit jwt coturn
```

Suivre CPU, RAM, débit réseau et espace disque. Les problèmes de médias proviennent
souvent d’une mauvaise `SERVER_IP`, d’une redirection UDP absente ou d’un filtrage
réseau. Une page Element fonctionnelle ne prouve pas que les appels passent.

## 12. Automatiser le renouvellement TLS

Tester la commande : si le certificat est valide plus de 30 jours, elle ne provoque
aucune interruption.

```bash
python3 scripts/tls.py renew
install -m 0644 configs/systemd/matrix-production-acme.service /etc/systemd/system/
install -m 0644 configs/systemd/matrix-production-acme.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now matrix-production-acme.timer
systemctl list-timers matrix-production-acme.timer
```

Le contrôle est quotidien. Lorsqu’un renouvellement est nécessaire, le script arrête
Caddy pour libérer le port 80, renouvelle et valide les fichiers, redémarre TURN, puis
relance Caddy. **L’accès web et les appels peuvent être interrompus à cette occasion.**
Le bloc `finally` relance Caddy même si ACME échoue avant le remplacement des fichiers.
En cas d’arrêt brutal du processus ou de l’hôte, vérifier son retour en ligne.
Conserver les redirections et le DNS fonctionnels après l’installation.

Si `/core/docker/Element_Matrix/matric-poc-prod` est remplacé par un autre chemin, adapter WorkingDirectory
et ExecStart dans le service systemd avant de l’installer.

```bash
journalctl -u matrix-production-acme.service --no-pager -n 80
openssl x509 -in data/tls/server.crt -noout -dates -issuer
```

Pour un renouvellement sans arrêt web, prévoir ensuite DNS-01 ou un webroot ACME.
Le mécanisme HTTP-01 fourni ici privilégie une exploitation simple et explicite.

## 13. Sauvegarder et vérifier une restauration

```bash
bash scripts/backup.sh
```

Le script arrête temporairement proxy/JWT/Synapse, fait un `pg_dump` cohérent, archive
les configurations, clés, médias, états Caddy et le compte ACME, calcule les empreintes,
puis relance les services. Les archives contiennent tous les secrets.

Copier chaque sauvegarde sur un stockage distinct, chiffré et contrôlé. Programmer
ce script dans une fenêtre de maintenance, puis surveiller la réussite et l’ancienneté
des sauvegardes. Leur rétention doit être définie selon l’espace disponible.

Test de restauration sur une machine isolée, de même architecture avec les images
épinglées disponibles (ne jamais écraser une production active) :

```bash
# Copier synapse.dump, files.tar.gz et SHA256SUMS dans /root/restauration-matrix.
cd /root/restauration-matrix
sha256sum -c SHA256SUMS
install -d -m 0700 /opt/matrix-restauration
tar --numeric-owner -xzf files.tar.gz -C /opt/matrix-restauration
cd /opt/matrix-restauration
docker compose config --quiet
docker compose up -d --wait postgres
docker compose exec -T postgres pg_restore --exit-on-error --no-owner -U synapse -d synapse < /root/restauration-matrix/synapse.dump
docker compose up -d --wait --wait-timeout 240
```

Ce test doit avoir lieu dans un réseau isolé : l’archive restaure les noms publics,
le projet Compose, l’IP média et les identités du serveur. Ne pas lancer deux serveurs
indépendants utilisant la même identité sur le réseau public. Utiliser un DNS de test
ou un fichier hosts pour les vérifications. Pour un vrai remplacement après panne,
laisser l’ancien hôte arrêté puis basculer DNS/NAT vers le nouveau.

## 14. Exploitation et mises à jour

```bash
cd /core/docker/Element_Matrix/matric-poc-prod
docker compose ps
docker compose logs --tail=100 synapse proxy livekit jwt coturn
df -h
docker system df
```

Surveiller : espace disque et croissance des médias/BDD, expiration TLS, santé des
services, échec des sauvegardes, CPU/RAM et qualité des appels. Prévoir une alerte
hors Matrix si toute la VM tombe.

Avant une mise à jour : sauvegarder, examiner les notes des versions concernées,
tester la combinaison d’images sur une instance isolée, puis mettre à jour les
versions dans `.env` pendant une fenêtre de maintenance et lancer `docker compose
pull` puis `docker compose up -d --wait --wait-timeout 240`.
Ne pas descendre de version après une migration de base sans restauration adaptée.
Ne pas utiliser `docker compose down -v`, un nettoyage de volumes ou une suppression
de `data/` comme méthode de dépannage.

## 15. État de validation de ce dossier

Les modèles Compose, les syntaxes Python/Bash, le rendu d’une installation neuve
avec certificat de test local et sa relance sans écrasement ont été contrôlés.
Caddy a également validé cette configuration dans un conteneur isolé sans réseau
ni port publié dans l’environnement de préparation.
Ce profil utilise les configurations et versions du POC avec trois domaines séparés.

L’installation réelle sur votre machine de production, l’émission ACME HTTP-01,
le renouvellement avec interruption, la restauration PostgreSQL et la recette
multi-postes restent à exécuter sur l’environnement cible. La validation statique ne
remplace pas ces contrôles de déploiement.

## Références officielles

- Docker Debian : https://docs.docker.com/engine/install/debian/
- Docker et filtrage réseau : https://docs.docker.com/engine/network/packet-filtering-firewalls/
- Synapse : https://element-hq.github.io/synapse/latest/usage/configuration/config_documentation.html
- LiveKit et ports : https://docs.livekit.io/transport/self-hosting/ports-firewall/
- Lego HTTP-01 : https://go-acme.github.io/lego/usage/cli/obtain-a-certificate/
- Vérification Element : https://docs.element.io/latest/element-support/device-verification/how-to-verify-devices/
