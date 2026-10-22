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
`matrix.exemple.fr`. Le DNS doit pointer vers l’IPv4
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
MATRIX_DOMAIN=matrix.exemple.fr
SYNAPSE_URL=https://matrix.exemple.fr
ELEMENT_URL=https://matrix.exemple.fr
RTC_URL=https://matrix.exemple.fr
TURN_HOST=matrix.exemple.fr
SERVER_IP=88.169.112.139
BIND_IP=0.0.0.0
ADMIN_VPN_IP=
ADMIN_OFFICE_IP=
```

Remplacer domaine et IP selon votre production. Renseigner les IP publiques de
SORTIE du VPN et des bureaux dans les deux dernières lignes. Vides, elles bloquent
l’administration pour tout le monde ; le reste d’Element reste public. Les secrets
applicatifs restent vides jusqu’au premier rendu.

Les ports locaux par défaut sont 18008 (Synapse), 18080 (Element), 18081 (JWT),
17880 (LiveKit HTTP) et 18082 (Ketesa). Vérifier qu’ils sont libres avec `ss -lnt`.
Ils sont toujours publiés sur `127.0.0.1`, indépendamment de `BIND_IP`.

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
  --cert /etc/letsencrypt/live/VOTRE_DOMAINE/fullchain.pem \
  --key /etc/letsencrypt/live/VOTRE_DOMAINE/privkey.pem
```

Remplacer les chemins par ceux de votre environnement. Le script vérifie le domaine,
la chaîne publique, la validité et la correspondance clé/certificat avant de remplacer
les copies dans `data/tls`. Le vhost généré lit ces copies, également montées dans
coturn ; JWT utilise la copie des racines publiques.

Le certificat doit être installé **avant le rendu et l’activation HTTPS du vhost**.
La commande peut être exécutée avant le démarrage des conteneurs. Le script ne
crée pas le certificat et ne modifie pas le DNS. Si le gestionnaire du serveur n’est
pas encore configuré, le préparer d’abord selon les pratiques de l’organisation.

L’ouverture publique du port 80 dépend de ce gestionnaire : une validation HTTP
l’exige généralement, une validation DNS peut s’en passer. Le vhost fourni ne fait
que rediriger HTTP vers HTTPS ; il ne configure aucun webroot de validation.
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
docker compose up -d --wait --wait-timeout 240
docker compose ps
```

Services attendus : postgres, synapse, element, jwt, livekit, coturn et ketesa.
**Aucun service `proxy`, Caddy ou Nginx dans Compose.** Le rendu crée notamment :

- `configs/generated/nginx/matrix.conf` : vhost pour Nginx installé sur l’hôte ;
- `configs/generated/ketesa/config.json` : serveur public restreint pour Ketesa ;
- configurations Synapse/Element/LiveKit/JWT/TURN et nouveaux secrets.

Les appels ne sont pas prêts avant activation de Nginx : JWT utilise son URL HTTPS
publique. Dans Docker, un alias `host-gateway` fait résoudre ce domaine vers l’hôte
pour JWT, afin d’éviter une dépendance au retour NAT. Nginx doit écouter sur les
interfaces IPv4 de l’hôte, comme dans le vhost généré. Son routage revient ensuite
sur les backends loopback.

En cas d’échec :

```bash
docker compose logs --tail=100 postgres synapse element jwt livekit coturn ketesa
```

Les images sont épinglées aux versions de travail ; vérifier leur compatibilité et
les avis de sécurité avant une ouverture durable. L’image Ketesa est le build
`v1.5.1-subpath-admin`, prévu pour `/admin`.

## 6. Installer le vhost dans Nginx hôte

Le modèle est dans `configs/nginx/matrix.conf.template`, mais **installer le fichier
généré**, qui contient votre domaine, vos IP et les chemins réels des certificats :

```bash
install -m 0600 configs/generated/nginx/matrix.conf /etc/nginx/sites-available/matrix-prod.conf
ln -s /etc/nginx/sites-available/matrix-prod.conf /etc/nginx/sites-enabled/matrix-prod.conf
nginx -t
systemctl reload nginx
```

Si le lien existe déjà, ne pas le recréer. Si Nginx était installé mais arrêté, après
un `nginx -t` réussi : `systemctl enable --now nginx`.
Sauvegarder et désactiver seulement un ancien vhost qui utiliserait le même domaine,
sans toucher aux autres sites. Sur une distribution n’utilisant pas sites-enabled,
installer le fichier dans un répertoire inclus par le contexte `http`.

Nginx reçoit directement le trafic Internet. S’il est lui-même derrière un proxy/CDN,
adapter la récupération de l’IP réelle en ne faisant confiance qu’aux proxies connus,
avant de considérer les restrictions d’administration comme effectives.

Les backends étant des ports loopback stables, une recréation des conteneurs ne
nécessite pas de mettre à jour des IP Docker dans Nginx. Si vous changez ces ports
ou les IP autorisées, suivre la reconfiguration de l’étape 11.

## 7. Vérifier les interfaces et l’administration

```bash
python3 scripts/check-endpoints.py
curl --fail http://127.0.0.1:18008/health
curl --fail http://127.0.0.1:18081/healthz
```

Avec votre domaine et depuis un réseau extérieur :

```bash
curl --fail https://VOTRE_DOMAINE/_matrix/client/versions
curl --fail https://VOTRE_DOMAINE/.well-known/matrix/client
curl --fail https://VOTRE_DOMAINE/livekit/jwt/healthz
```

Element doit s’ouvrir sur `https://VOTRE_DOMAINE/` sans avertissement TLS.
`/_matrix/federation/v1/version` doit renvoyer 404. La fédération générale reste
fermée ; l’exception OpenID nécessaire aux appels est accessible.

Tester `/admin/` et `/_synapse/admin/v1/server_version` depuis :

- une IP hors liste : 403 sur les deux ;
- le VPN/bureau autorisé : interface accessible, API exigeant toujours un jeton admin.

L’IP autorisée est la sortie publique du poste, pas l’IP du serveur. Le VPN doit
acheminer cette destination via sa sortie professionnelle. Vides, les deux champs
ADMIN bloquent tout accès d’administration.

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
  --cert /etc/letsencrypt/live/VOTRE_DOMAINE/fullchain.pem \
  --key /etc/letsencrypt/live/VOTRE_DOMAINE/privkey.pem
```

Un modèle prêt à adapter est disponible dans
[configs/certificates/deploy-hook.sh.example](configs/certificates/deploy-hook.sh.example).
Il filtre aussi les autres certificats si Certbot utilise un hook global.

Enregistrer le script adapté dans `/etc/letsencrypt/renewal-hooks/deploy/matrix-stack.sh`,
réservé à root et exécutable (`chmod 0700`). Employer les chemins absolus réels du
certificat. Avec un autre gestionnaire, configurer le même appel après renouvellement.
Ne pas installer de hook contenant littéralement `VOTRE_DOMAINE`.

Tester manuellement la commande `tls.py install` avec les chemins réels avant de
l’ajouter au mécanisme de renouvellement. Si les fichiers sont identiques et déjà
activés, aucune action sur les services n’est effectuée.

En cas de changement, les anciennes copies sont sauvegardées sous `backups/tls-*`.
Le script valide Nginx actif, redémarre coturn si le certificat a changé, recrée JWT
si les racines ont changé, puis recharge Nginx. Il n’arrête pas Nginx ; TURN peut
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
# Remplacer VOTRE_DOMAINE par votre vrai nom DNS :
openssl s_client -connect VOTRE_DOMAINE:443 -servername VOTRE_DOMAINE </dev/null 2>/dev/null | openssl x509 -noout -dates -issuer
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

La régénération garde l’identité et les secrets ; elle adapte le chemin absolu TLS
au dossier de restauration. Vérifier le vhost généré avant son installation dans le
Nginx de test. Le certificat est celui sauvegardé : s’il a expiré, le renouveler via
le gestionnaire approprié. Les sauvegardes serveur ne remplacent pas les clés de
récupération personnelles. Ne pas faire fonctionner simultanément deux copies
indépendantes de la même identité sur Internet.

## 11. Reconfiguration et mises à jour

Après modification des ports ou des IP administratives dans `.env` :

```bash
python3 scripts/render.py --update
docker compose config --quiet
docker compose up -d --wait --wait-timeout 240
install -m 0600 configs/generated/nginx/matrix.conf /etc/nginx/sites-available/matrix-prod.conf
nginx -t && systemctl reload nginx
```

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

Le profil est préparé et validé en environnement de test isolé : rendu, modèle Compose,
ports HTTP loopback, absence de proxy Docker et syntaxe du vhost Nginx.
Des backends de test ont aussi confirmé le routage et le retrait des préfixes RTC,
les ACL en accès refusé/autorisé, la conservation des secrets avec --update et le
refus de changement de l’identité Matrix.
L’image Ketesa pour `/admin` a été vérifiée dans le registre.
Le gestionnaire de certificats externe, l’installation dans votre Nginx de production et un appel réel
restent à valider sur le serveur cible. La préparation n’installe ni paquet ni vhost
système, et ne démarre pas les services de production.

Références officielles :
- https://docs.docker.com/engine/install/debian/
- https://docs.docker.com/engine/network/packet-filtering-firewalls/
- https://nginx.org/en/docs/http/websocket.html
- https://nginx.org/en/docs/http/ngx_http_access_module.html
- https://github.com/etkecc/ketesa#serving-ketesa-under-a-custom-path
