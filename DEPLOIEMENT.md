# Déploiement Matrix — Nginx installé sur le serveur

Profil refait le 22 octobre 2026 : **aucun service proxy Docker**. Le serveur utilise
Nginx installé sur l’hôte, un seul domaine HTTPS, des ports HTTP locaux et des ports
média publics. L’administration est limitée aux IP publiques fixes du VPN et des bureaux.

## 1. Préparer le serveur et le domaine

Prévoir pour la stack 2 vCPU, 2 Go de RAM et 30 Go SSD comme point de départ, **hors OS,
Nginx, autres services, sauvegardes et croissance des médias**. Pour moins de dix
utilisateurs, qualifier ensuite la charge avec le nombre maximal de participants.

Docker Engine et Compose doivent être installés. Nginx doit être installé et géré
sur CETTE machine, avec un processus maître capable de lire les clés TLS (installation
Debian standard : maître root). Aucun conteneur Nginx n’est nécessaire.

```bash
sudo apt update
sudo apt install -y python3 openssl ca-certificates curl nano tar util-linux
sudo docker version
sudo docker compose version
sudo nginx -v
```

Si nécessaire, suivre les instructions Docker officielles :
https://docs.docker.com/engine/install/debian/. Pour un serveur neuf sans Nginx :
`sudo apt install nginx`. Ne pas réinstaller ou remplacer la configuration d’un
Nginx existant sans vérifier ses autres sites.

Le dossier de travail est `/core/docker/Element_Matrix/matric-poc-prod`.
Les commandes suivantes s’exécutent en root dans ce dossier, sauf indication contraire.
Le répertoire est privé car il contiendra les clés et secrets.

Choisir un **seul domaine définitif** pour cette installation neuve. Exemple :
`chat.pro-gx.fr`. Le DNS doit pointer vers l’IPv4
publique de production. Le domaine devient le suffixe des comptes ; ne pas le changer
après création d’une base. Ne pas publier d’AAAA non fonctionnel.

Ce profil repart avec une base vide. Ne pas copier la base, les clés ou les secrets
d’un autre serveur Matrix pour créer un second serveur indépendant de même identité.

## 2. Configurer .env

```bash
cd /core/docker/Element_Matrix/matric-poc-prod
cp -n .env.example .env
chmod 0600 .env
nano .env
```

Voir [REMPLIR-ENV.md](REMPLIR-ENV.md). Exemple :

```dotenv
COMPOSE_PROJECT_NAME=matrix-prod
MATRIX_DOMAIN=chat.pro-gx.fr
SYNAPSE_URL=https://chat.pro-gx.fr
ELEMENT_URL=https://chat.pro-gx.fr
RTC_URL=https://chat.pro-gx.fr
TURN_HOST=chat.pro-gx.fr
SERVER_IP=88.169.112.139
BIND_IP=0.0.0.0
```

Remplacer domaine et IP selon votre production. Les whitelists sont gérées
directement dans votre Nginx et ne sont pas des paramètres de la stack.
Les secrets applicatifs restent vides jusqu’au premier rendu.

Les ports locaux par défaut sont 18008 (Synapse), 18080 (Element), 18081 (JWT),
17880 (LiveKit HTTP) et 18082 (Ketesa). Vérifier qu’ils sont libres avec `ss -lnt`.
Ils sont toujours publiés sur `127.0.0.1`, indépendamment de `BIND_IP`.

### 2.1 Vérifier la coexistence sur le serveur distant

Les ports TCP 3306 (MariaDB), 5100 (Password Pusher), 8090 (alert-monitor) et
8443 (Vaultwarden) sont déjà utilisés. Le profil Matrix utilise des ports distincts :

| Service Matrix | Port publié sur l’hôte | Port dans le conteneur |
|---|---|---|
| Synapse HTTP | `127.0.0.1:18008` | 8008/TCP |
| Element HTTP | `127.0.0.1:18080` | 80/TCP |
| JWT HTTP | `127.0.0.1:18081` | 8080/TCP |
| LiveKit HTTP / WebSocket | `127.0.0.1:17880` | 7880/TCP |
| Ketesa HTTP | `127.0.0.1:18082` | 8080/TCP |

Les ports média restent ceux de l’étape 3. Aucun port publié de la liste existante
ne chevauche ce profil. Le modèle inclut :

```dotenv
RESERVED_TCP_PORTS=3306,5100,8090,8443
```

Le générateur refusera une nouvelle configuration Matrix qui réutiliserait ces
ports TCP. Cette vérification compare la configuration à la liste déclarée, sans
se connecter au serveur distant. Compléter la liste si d’autres ports sont occupés.

Sur le serveur de production, avant démarrage :

```bash
ss -lntup
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

Les affichages `80/tcp` ou `443/tcp` sans flèche `->` sont internes aux conteneurs,
et ne réservent pas les ports de l’hôte. Le Nginx hôte existant peut servir plusieurs
domaines sur les mêmes ports 80/443 : ajouter seulement le vhost Matrix, sans
remplacer ses autres sites ou lancer un autre proxy.

## 3. Préparer le réseau public

| Protocole | Ports | Destination |
|---|---|---|
| TCP | 443 | Nginx hôte |
| TCP | 80, selon la politique du serveur | Redirection HTTPS et besoins éventuels du gestionnaire de certificats |
| TCP | 7881 | LiveKit, média |
| UDP | 15000–15100 | LiveKit, média |
| TCP/UDP | 3478 | TURN |
| TCP | 5349 | TURN TLS |
| UDP | 15200–15300 | Relais TURN |

Avec une IP publique directement portée par le serveur, autoriser ces flux dans le
pare-feu hôte/hébergeur. Derrière un routeur, rediriger ces ports vers l’IP LAN du
serveur, avec les mêmes ports internes/externes. Tailscale n’est pas requis.

Ne pas ouvrir publiquement 18008, 18080, 18081, 17880, 18082, 5432, 8008 ou 8080.
Les publications Docker peuvent contourner les règles UFW classiques : vérifier le
filtrage effectif au niveau Docker/réseau, pas seulement les règles UFW affichées.
Les médias WebRTC ne passent pas par les locations HTTP de Nginx.

## 4. Installer le certificat géré par le serveur

Le certificat est obtenu et renouvelé **hors de la stack**, par le gestionnaire du
serveur de production. Utiliser un certificat public valide couvrant exactement
`MATRIX_DOMAIN` (ou un wildcard qui le couvre), sa chaîne intermédiaire complète et
sa clé privée. Cette étape ne demande ni token DNS, ni conteneur supplémentaire.

Exemple avec les fichiers d’un gestionnaire utilisant l’arborescence Let's Encrypt :

```bash
python3 scripts/tls.py install \
  --cert /etc/letsencrypt/live/chat.pro-gx.fr/fullchain.pem \
  --key /etc/letsencrypt/live/chat.pro-gx.fr/privkey.pem
```

Remplacer les chemins par ceux de votre environnement. Le script vérifie le domaine,
la chaîne publique, la validité et la correspondance clé/certificat avant de remplacer
les copies dans `data/tls` montées dans coturn ; JWT utilise la copie des racines
publiques. Votre Nginx conserve ses propres chemins de certificat.

Le certificat doit être installé **avant le rendu et l’activation HTTPS du vhost**.
La commande peut être exécutée avant le démarrage des conteneurs. Le script ne
crée pas le certificat et ne modifie pas le DNS. Si le gestionnaire du serveur n’est
pas encore configuré, le préparer d’abord selon les pratiques de l’organisation.

L’ouverture publique du port 80 dépend de ce gestionnaire : une validation HTTP
l’exige généralement, une validation DNS peut s’en passer. Votre vhost doit être adapté
aux besoins de validation du gestionnaire de certificats que vous utilisez.
Ne pas supposer que le retrait du client de certificat de la stack supprime les
besoins réseau de l’outil externe.

## 4.1 Prévoir le hook après renouvellement

Les fichiers installés sont des **copies**, pas des liens vers le certificat source.
Il faut appeler `tls.py install` après chaque renouvellement réussi. Un exemple
pour Certbot est détaillé à l’étape 9 ; l’équivalent doit être configuré dans votre
outil si vous utilisez un autre gestionnaire.

## 5. Générer et démarrer les services Docker

```bash
python3 scripts/render.py
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose ps
```

Services attendus : postgres, synapse, element, jwt, livekit, coturn et ketesa.
**Aucun service `proxy`, Caddy ou Nginx dans Compose.** Le rendu crée notamment :

- `configs/generated/nginx/client.json` et `server.json` : données de découverte à intégrer à votre Nginx ;
- `configs/generated/ketesa/config.json` : serveur public restreint pour Ketesa ;
- configurations Synapse/Element/LiveKit/JWT/TURN et nouveaux secrets.

Les appels ne sont pas prêts avant activation de Nginx : JWT utilise son URL HTTPS
publique. Dans Docker, un alias `host-gateway` fait résoudre ce domaine vers l’hôte
pour JWT, afin d’éviter une dépendance au retour NAT. Nginx doit écouter sur les
interfaces IPv4 de l’hôte. Son routage revient ensuite
sur les backends loopback.

En cas d’échec :

```bash
docker compose logs --tail=100 postgres synapse element jwt livekit coturn ketesa
```

Les images sont épinglées aux versions de travail ; vérifier leur compatibilité et
les avis de sécurité avant une ouverture durable. L’image Ketesa est le build
`v1.5.1-subpath-admin`, prévu pour `/admin`.

### 5.1 Serveur sans IPv6 : Nginx interne d’Element

L’image Element intègre son propre serveur HTTP Nginx pour distribuer les fichiers
web. Il est distinct du reverse proxy Nginx que vous administrez sur l’hôte.
Un modèle interne IPv4 est monté depuis `configs/element/default.conf.template`
pour éviter l’erreur `socket() [::]:80 failed (97: Address family not supported by protocol)`
sur les serveurs dont IPv6 est désactivé. Aucun changement de votre vhost n’est requis.

Après transfert de cette correction sur le serveur :

```bash
docker compose up -d --no-deps --force-recreate element
docker compose logs --tail=50 element
curl --fail http://127.0.0.1:18080/config.json
```

Vérifier que le fichier modèle existe avant le démarrage : il doit être transféré
avec le Compose. Lors d’une mise à jour de l’image Element, comparer ce modèle à
celui de la nouvelle image pour conserver ses évolutions de configuration.

## 6. Intégrer la stack à votre Nginx

Le vhost est entièrement géré par l’exploitant. **Aucun modèle n’est généré ou
installé par ce projet ; aucun script ne valide ou recharge Nginx.**
Le contrat d’intégration (routes, ports, découverte, WebSocket et filtrage) est décrit
dans [configs/nginx/README.md](configs/nginx/README.md).

Configurer votre vhost pour `chat.pro-gx.fr` avec les ports loopback du Compose,
les JSON de découverte produits au rendu et vos propres certificats. Protéger
`/admin/` ET `/_synapse/admin/` par vos whitelists et garder les autres routes
internes/fédération fermées, sauf l’exception OpenID nécessaire aux appels.
Valider et recharger Nginx selon vos procédures d’exploitation, sans remplacer
les autres sites. Les fichiers de découverte ne contiennent pas de secrets, mais
le répertoire parent des configurations est privé : reprendre leur contenu dans
votre vhost ou les publier depuis un emplacement lisible adapté.

Une fois votre proxy actif, vérifier la santé complète :

```bash
docker compose up -d --wait --wait-timeout 240
```

Une modification de la whitelist s’effectue uniquement dans Nginx, sans modifier
`.env` ni régénérer les fichiers applicatifs.

## 7. Vérifier les interfaces et l’administration

```bash
python3 scripts/check-endpoints.py
curl --fail http://127.0.0.1:18008/health
curl --fail http://127.0.0.1:18081/healthz
```

Avec votre domaine et depuis un réseau extérieur :

```bash
curl --fail https://chat.pro-gx.fr/_matrix/client/versions
curl --fail https://chat.pro-gx.fr/.well-known/matrix/client
curl --fail https://chat.pro-gx.fr/livekit/jwt/healthz
```

Element doit s’ouvrir sur `https://chat.pro-gx.fr/` sans avertissement TLS.
`/_matrix/federation/v1/version` doit renvoyer 404. La fédération générale reste
fermée ; l’exception OpenID nécessaire aux appels est accessible.

Tester `/admin/` et `/_synapse/admin/v1/server_version` depuis :

- une IP hors liste : 403 sur les deux ;
- le VPN/bureau autorisé : interface accessible, API exigeant toujours un jeton admin.

L’IP autorisée est la sortie publique du poste, pas l’IP du serveur. Le VPN doit
acheminer cette destination via sa sortie professionnelle. Ces tests vérifient
la whitelist configurée par vos soins dans Nginx.

## 8. Créer les comptes et tester les usages

```bash
bash scripts/create-user.sh --admin
bash scripts/create-user.sh
```

Les identifiants et mots de passe sont demandés interactivement. L’administrateur
serveur n’est pas automatiquement administrateur des salons existants.
Chaque utilisateur doit activer la sauvegarde des clés dans Element et conserver sa
clé de récupération ; elle permet de valider un nouvel appareil sans l’ancienne session.
Les inscriptions libres, Scalar, MAS et les e-mails ne sont pas activés.

```bash
python3 scripts/test-rtc.py
```

Ce diagnostic teste les transports, OpenID et l’émission de jetons. Valider aussi
les médias avec deux vrais postes dont un extérieur : messages, photos, documents,
audio, vidéo et partage d’écran. Faire un test de 10–15 minutes au nombre maximal
de participants attendu, et suivre `docker stats $(docker compose ps -q)`.
Une page HTTPS correcte ne prouve pas que les plages UDP sont accessibles.

## 9. Synchroniser après chaque renouvellement externe

Conserver **un seul mécanisme d’émission et de renouvellement**, celui du serveur.
La stack ne fournit plus de timer ni de commande `issue`/`renew`.

Avec Certbot, exemple de deploy-hook à adapter :

```bash
#!/bin/sh
set -eu
/usr/bin/python3 /core/docker/Element_Matrix/matric-poc-prod/scripts/tls.py install \
  --cert /etc/letsencrypt/live/chat.pro-gx.fr/fullchain.pem \
  --key /etc/letsencrypt/live/chat.pro-gx.fr/privkey.pem
```

Un modèle prêt à adapter est disponible dans
[configs/certificates/deploy-hook.sh.example](configs/certificates/deploy-hook.sh.example).
Il filtre aussi les autres certificats si Certbot utilise un hook global.

Enregistrer le script adapté dans `/etc/letsencrypt/renewal-hooks/deploy/matrix-stack.sh`,
réservé à root et exécutable (`chmod 0700`). Employer les chemins absolus réels du
certificat. Avec un autre gestionnaire, configurer le même appel après renouvellement.
Vérifier le chemin réel du certificat : le répertoire de votre gestionnaire peut porter un autre nom ou un suffixe, par exemple `chat.pro-gx.fr-0001`.

Tester manuellement la commande `tls.py install` avec les chemins réels avant de
l’ajouter au mécanisme de renouvellement. Si les fichiers sont identiques et déjà
activés, aucune action sur les services n’est effectuée.

En cas de changement, les anciennes copies sont sauvegardées sous `backups/tls-*`.
Le script redémarre coturn si le certificat a changé et recrée JWT si les racines
ont changé. Il ne touche pas Nginx ; votre gestionnaire externe reste responsable
de son rechargement. TURN peut
interrompre les appels qui utilisent ses relais pendant son redémarrage.
Les services arrêtés liront les fichiers à leur prochain démarrage.

En cas d’échec d’activation après copie, le script renvoie une erreur et conserve
`data/tls-install.pending.json`. Corriger le problème puis **relancer la même
commande**, même si les sources n’ont pas changé, pour terminer l’activation.
Ne pas supprimer ce marqueur pour masquer une erreur. Surveiller aussi les erreurs
du hook dans votre gestionnaire de renouvellement.

Vérifier le certificat installé et celui réellement servi au domaine :

```bash
openssl x509 -in data/tls/server.crt -noout -dates -issuer
# Vérifier le certificat servi par le domaine de production :
openssl s_client -connect chat.pro-gx.fr:443 -servername chat.pro-gx.fr </dev/null 2>/dev/null | openssl x509 -noout -dates -issuer
```

Adapter le chemin du hook si le projet est déplacé. Une sauvegarde de la stack ne
remplace pas celle de la configuration du gestionnaire de certificats externe.

## 10. Sauvegarde et restauration

```bash
bash scripts/backup.sh
```

Le script suspend temporairement Synapse/JWT, réalise un dump PostgreSQL cohérent
avec les médias et archive les paramètres, scripts, clés et copies TLS. Un verrou
empêche une installation TLS concurrente pendant cette sauvegarde.
Il **n’arrête pas le Nginx hôte**, pour laisser ses autres sites accessibles.
Les requêtes Matrix peuvent échouer pendant la maintenance.
Sauvegarder aussi `/etc/nginx`, les fichiers du gestionnaire de certificats externe
et ses hooks. Conserver les archives chiffrées sur un autre stockage.

Pour restaurer, sur une machine isolée et vide, sans serveur Matrix actif de même
identité accessible publiquement :

```bash
# Placer le contenu d’une sauvegarde dans /root/restauration-matrix.
cd /root/restauration-matrix
sha256sum -c SHA256SUMS
install -d -m 0700 /opt/matrix-restauration
tar --numeric-owner -xzf files.tar.gz -C /opt/matrix-restauration
cd /opt/matrix-restauration
docker compose up -d --wait postgres
docker compose exec -T postgres pg_restore --exit-on-error --no-owner -U synapse -d synapse < /root/restauration-matrix/synapse.dump
python3 scripts/render.py --update
docker compose up -d --wait --wait-timeout 240
```

La régénération garde l’identité et les secrets. Adapter votre vhost de test
séparément avec les ports locaux et la découverte restaurée. Le certificat est
celui sauvegardé : s’il a expiré, le renouveler via
le gestionnaire approprié. Les sauvegardes serveur ne remplacent pas les clés de
récupération personnelles. Ne pas faire fonctionner simultanément deux copies
indépendantes de la même identité sur Internet.

## 11. Reconfiguration et mises à jour

Après modification des paramètres applicatifs ou des ports dans `.env` :

```bash
python3 scripts/render.py --update
docker compose config --quiet
docker compose up -d --wait --wait-timeout 240
```

Si les ports HTTP changent, mettre à jour séparément votre vhost Nginx.
La whitelist reste exclusivement gérée dans Nginx.

Le générateur sauvegarde `.env` et les configurations avant régénération. Le contenu
manuel des fichiers générés peut être remplacé ; modifier le modèle/générateur si
vous avez des personnalisations à conserver. Ne pas changer `server_name`, les
secrets ou le mot de passe PostgreSQL pour une simple mise à jour.

Avant mise à jour des images : sauvegarder, examiner les notes de version, tester
sur un environnement isolé, changer les versions dans `.env`, régénérer si nécessaire,
puis `docker compose pull` et `docker compose up -d --wait --wait-timeout 240`.
Prévoir une restauration si une migration de base rend un retour de version impossible.
Surveiller disque, médias, santé, charge, expiration TLS et réussite des sauvegardes.
Ne pas utiliser une suppression de `data/` ou de volumes comme dépannage.

## 12. État de vérification

Le rendu des configurations applicatives, le Compose et les ports HTTP loopback
sont vérifiables sans Nginx. Les scripts ne dépendent plus d’un modèle de vhost,
de whitelists dans `.env` ni de commandes Nginx/systemctl. Le certificat réel,
votre vhost, ses listes d’accès et les appels depuis Internet restent à valider
sur le serveur de production.

Références officielles :
- https://docs.docker.com/engine/install/debian/
- https://docs.docker.com/engine/network/packet-filtering-firewalls/
- https://nginx.org/en/docs/http/websocket.html
- https://nginx.org/en/docs/http/ngx_http_access_module.html
- https://github.com/etkecc/ketesa#serving-ketesa-under-a-custom-path

## Dépannage Ketesa : page « Static Web Server »

L’image `v1.5.1-subpath-admin` sert Ketesa sur `/admin/`, pas sur `/`.
Dans votre location `/admin/`, conserver la whitelist et transmettre le chemin
sans le supprimer : `proxy_pass http://127.0.0.1:18082;` (sans slash après le port).
Le montage du Compose doit cibler `/var/public/admin/config.json`.
Après mise à jour du Compose, recréer uniquement Ketesa :

```bash
docker compose up -d --no-deps --force-recreate ketesa
curl --fail http://127.0.0.1:18082/admin/config.json
```
