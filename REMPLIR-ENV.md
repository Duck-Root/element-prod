# Remplir .env — un domaine unique, Nginx sur l’hôte

`.env` contient les paramètres lus par Docker Compose et le générateur. Il ne crée
ni DNS ni règle de pare-feu. Il devient privé dès que les secrets sont générés.

```bash
cd /core/docker/Element_Matrix/matric-poc-prod
cp -n .env.example .env
chmod 0600 .env
nano .env
```

## Un seul nom public pour les fonctions web

Le domaine de production est prérempli avec **chat.pro-gx.fr** :

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

Remplacer le domaine et l’IP si la production utilise d’autres valeurs. Les trois
URL sont **identiques**, sans `/element`, `/synapse` ou `/livekit` dans `.env` :
le générateur ajoute les chemins RTC lui-même. `MATRIX_DOMAIN` et `TURN_HOST`
s’écrivent sans `https://`, les trois URL avec `https://`.

| Champ | Rôle |
|---|---|
| `COMPOSE_PROJECT_NAME` | Nom local des conteneurs Docker |
| `MATRIX_DOMAIN` | Identité permanente du serveur : `@alice:ce-domaine` |
| `SYNAPSE_URL` | Origine de l’API de comptes, salons, messages et fichiers |
| `ELEMENT_URL` | Adresse à communiquer aux collègues, interface à la racine `/` |
| `RTC_URL` | Origine publique des services d’appels |
| `TURN_HOST` | Nom public du relais média, ici le même domaine |
| `SERVER_IP` | IPv4 publique annoncée pour les médias, jamais l’IP LAN/Tailscale |
| `BIND_IP` | Publication des ports média : garder `0.0.0.0` pour toutes les interfaces IPv4 |

Le DNS du domaine doit résoudre vers `SERVER_IP`. Nginx reçoit le HTTPS sur le port
443 et distingue les services par leur chemin. L’administration est sur `/admin/`.
Le profil ne dépend pas de Tailscale. Si la machine est derrière une box, les règles
NAT ciblent son IP LAN, pas `0.0.0.0` ni l’IP publique.

**Ne pas changer `MATRIX_DOMAIN` après initialisation d’une base.** Le générateur
refuse ce changement même avec `--update`.

## Administration et vhost gérés hors de la stack

Configurer vos whitelists directement dans Nginx, pour `/admin/` et
`/_synapse/admin/`. Aucun paramètre d’IP d’administration n’est lu par la stack.
Les scripts ne génèrent ni n’installent de vhost et ne rechargent pas Nginx.
Un compte administrateur Matrix reste nécessaire après le filtrage IP.

## Ports locaux pour Nginx : ne pas les ouvrir sur Internet

```dotenv
SYNAPSE_HTTP_PORT=18008
ELEMENT_HTTP_PORT=18080
JWT_HTTP_PORT=18081
LIVEKIT_HTTP_PORT=17880
KETESA_HTTP_PORT=18082
```

Ils sont publiés uniquement sur **127.0.0.1**, même si `BIND_IP=0.0.0.0`.
Nginx installé sur la même machine les utilise directement ; il n’a pas besoin de
résoudre des noms Docker. Garder ces valeurs si elles sont libres.
Les cinq ports doivent être distincts et ne pas chevaucher les ports TCP publics.

Les ports 80/443 sont configurés dans votre Nginx, pas dans `.env` ni dans Docker.
Le profil applicatif attend HTTPS sur 443 pour la découverte.

## Ports déjà utilisés par les autres applications

```dotenv
RESERVED_TCP_PORTS=3306,5100,8090,8443
```

Cette liste correspond à MariaDB, Password Pusher, alert-monitor et Vaultwarden.
Le rendu refuse d’utiliser l’un de ces ports pour une publication TCP de Matrix.
Elle ne change pas les applications existantes et n’ajoute aucune règle de pare-feu.
Les ports Matrix actuels (18008, 18080, 18081, 17880, 18082, 7881, 3478, 5349)
ne chevauchent pas la liste : conserver leurs valeurs.

Mettre à jour cette liste sur un autre serveur ou si vous ajoutez des applications.
Les valeurs sont séparées par des virgules. Les ports UDP ne sont pas concernés
par cette liste TCP. Les ports 80/443 du Nginx hôte sont partagés par les vhosts,
et ne sont pas des publications Docker Matrix.

## Ports média publics : à conserver dans le pare-feu/NAT

```dotenv
LIVEKIT_TCP_PORT=7881
LIVEKIT_UDP_START=15000
LIVEKIT_UDP_END=15100
TURN_PORT=3478
TURN_TLS_PORT=5349
TURN_UDP_START=15200
TURN_UDP_END=15300
```

TCP 7881, TCP/UDP 3478, TCP 5349, UDP 15000–15100 et UDP 15200–15300 doivent être
accessibles directement pour les médias. Le vhost HTTPS ne remplace pas ces flux.

## Certificats et images

Garder `TLS_MODE=provided`. Le certificat est émis et renouvelé par le gestionnaire
de certificats du serveur de production. `tls.py install` copie et valide ses
fichiers dans `data/tls`, puis actualise les services concernés. Aucun compte ACME,
token DNS ou adresse e-mail de certificat n’est à renseigner dans `.env`.
Le domaine peut être hébergé chez le fournisseur DNS de votre choix. Voir le hook
de renouvellement dans DEPLOIEMENT.md.

Les champs `*_IMAGE` sont les versions des logiciels Docker, pas des URL web.
`KETESA_IMAGE` doit rester une version **construite pour `/admin`**, par exemple
`ghcr.io/etkecc/ketesa:v1.5.1-subpath-admin`. Garder les versions proposées pour le
premier test, puis préparer les mises à jour séparément.

## Secrets applicatifs

Laisser vides au premier rendu : `POSTGRES_PASSWORD`, `REGISTRATION_SHARED_SECRET`,
`MACAROON_SECRET`, `FORM_SECRET`, `LIVEKIT_KEY`, `LIVEKIT_SECRET`, `TURN_SECRET`,
`AS_TOKEN`, `HS_TOKEN`. Le générateur les remplit après installation du certificat.
Ce ne sont pas les mots de passe des utilisateurs. Ne jamais les vider ou les
régénérer sur une base utilisée. Ne pas partager le `.env` complet dans un message.

## Modifier après le premier rendu

Pour modifier les ports locaux, sauvegarder, éditer `.env`, puis :

```bash
python3 scripts/render.py --update
docker compose config --quiet
docker compose up -d --wait --wait-timeout 240
```

`--update` sauvegarde les fichiers générés et le `.env` avant le rendu puis remplace
les configurations à partir des paramètres. Les personnalisations manuelles des
fichiers générés peuvent être écrasées : les reporter au préalable dans le modèle
ou le générateur. Les secrets existants sont conservés. Adapter les scripts de
renouvellement externes si le chemin du projet ou le certificat source change.

Après un changement de port local, adapter séparément les destinations de votre
vhost Nginx. La régénération applicative ne touche pas votre whitelist.
