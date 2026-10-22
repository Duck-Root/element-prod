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

Exemple générique à adapter à votre domaine réel (ne pas conserver `exemple.fr`) :

```dotenv
COMPOSE_PROJECT_NAME=matrix-prod
MATRIX_DOMAIN=matrix.exemple.fr
SYNAPSE_URL=https://matrix.exemple.fr
ELEMENT_URL=https://matrix.exemple.fr
RTC_URL=https://matrix.exemple.fr
TURN_HOST=matrix.exemple.fr
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

## Qui peut accéder à l’administration ?

```dotenv
ADMIN_VPN_IP=VOTRE_IP_PUBLIQUE_DE_SORTIE_VPN
ADMIN_OFFICE_IP=VOTRE_IP_PUBLIQUE_DES_BUREAUX
```

Remplacer les deux textes par de vraies IP, ou laisser une ligne vide si ce réseau
n’est pas utilisé. Accepte une IPv4/IPv6 ou un CIDR précis. Ne pas mettre d’URL,
de port ou l’IP du serveur. Les deux champs vides génèrent un `deny all`.
Un `/0` est refusé pour éviter une autorisation de tout Internet.

Ces IP autorisent l’accès à `/admin/` et `/_synapse/admin/` ; un compte administrateur
Matrix reste nécessaire. Avec un VPN en split tunneling, vérifier que la destination
Matrix utilise effectivement sa sortie professionnelle.

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

`HTTP_PORT=80` et `HTTPS_PORT=443` décrivent le point d’entrée Nginx hôte ; Docker
ne publie aucun de ces ports. Le profil exige HTTPS sur 443 pour la découverte.

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

Pour modifier les IP autorisées ou les ports locaux, sauvegarder, éditer `.env`, puis :

```bash
python3 scripts/render.py --update
docker compose config --quiet
docker compose up -d --wait --wait-timeout 240
install -m 0600 configs/generated/nginx/matrix.conf /etc/nginx/sites-available/matrix-prod.conf
nginx -t && systemctl reload nginx
```

`--update` sauvegarde les fichiers générés et le `.env` avant le rendu puis remplace
les configurations à partir des paramètres. Les personnalisations manuelles des
fichiers générés peuvent être écrasées : les reporter au préalable dans le modèle
ou le générateur. Les secrets existants sont conservés. Adapter les scripts de
renouvellement externes si le chemin du projet ou le certificat source change.
