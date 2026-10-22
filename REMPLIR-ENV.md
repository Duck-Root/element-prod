# Comprendre et remplir le fichier .env

Le fichier `.env` est la fiche de paramètres de votre installation. Docker Compose
et les scripts y lisent les noms de domaine, l’IP, les ports et les secrets.
Il ne crée ni domaine DNS, ni redirection sur la box.

Le fichier `.env.example` est un modèle. On le copie une seule fois vers `.env`,
puis on modifie cette copie. Garder `.env` privé : il contiendra des mots de passe.

## Pourquoi plusieurs URL pour une seule machine ?

Tous les services tournent sur la même machine et peuvent utiliser **la même IP publique**.
Les noms servent au proxy Caddy à savoir à quel service transmettre une demande.
Ce profil neuf attend trois noms distincts ; il n’utilise pas le montage à URL
unique de l’ancien POC.

| Nom | Rôle | Qui l’utilise ? |
|---|---|---|
| `element.…` | La page web avec les salons, messages et boutons d’appel | Vos collègues : c’est le lien à leur transmettre |
| `matrix.…` | Le serveur qui gère les comptes, messages, salons et fichiers | Element en arrière-plan ; ce nom apparaît aussi dans les identifiants |
| `rtc.…` | Le service d’appels audio/vidéo et le relais réseau TURN | Les appareils des participants, automatiquement |

Les trois noms pointent vers votre IP publique. **Il ne faut pas trois serveurs,
ni trois IP publiques, ni trois redirections du port 443.** Une seule redirection
TCP 443 vers la machine suffit pour ces URL ; Caddy les distingue par leur nom.
Les ports média indiqués dans la procédure restent nécessaires pour les appels.

## Ce que chaque champ signifie

| Champ | Ce qu’il faut mettre | Exemple |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | Un nom local pour identifier les conteneurs Docker | `matric-poc-prod` |
| `MATRIX_DOMAIN` | Nom définitif du serveur Matrix, **sans** `https://` | `matrix.element-matrix-poc.duckdns.org` |
| `SYNAPSE_URL` | Adresse HTTPS de l’API Matrix, avec le même nom que ci-dessus | `https://matrix.element-matrix-poc.duckdns.org` |
| `ELEMENT_URL` | Adresse HTTPS de l’interface web à ouvrir dans le navigateur | `https://element.element-matrix-poc.duckdns.org` |
| `RTC_URL` | Adresse HTTPS des services d’appel | `https://rtc.element-matrix-poc.duckdns.org` |
| `TURN_HOST` | Nom du relais média, **sans** `https://` ; ici le même nom que RTC | `rtc.element-matrix-poc.duckdns.org` |
| `SERVER_IP` | IPv4 publique que les clients doivent contacter pour les médias | `88.169.112.139` si vous utilisez toujours la même connexion Internet |
| `BIND_IP` | Interface de la machine sur laquelle Docker publie les ports | Garder `0.0.0.0` |

`MATRIX_DOMAIN` devient une partie de l’identité des comptes. Avec cet exemple,
Alice sera `@alice:matrix.element-matrix-poc.duckdns.org`. Ce nom est à choisir
avant la création des comptes ; il ne se renomme pas sur une base déjà utilisée.

`0.0.0.0` signifie « écouter sur toutes les interfaces IPv4 de cette machine ».
Ce n’est ni une adresse à communiquer aux collègues, ni une valeur à mettre dans
le DNS, ni l’IP de destination à renseigner sur la box.

## Exemple avec votre domaine DuckDNS actuel

Si vous conservez le domaine `element-matrix-poc.duckdns.org` et la connexion dont
l’IP publique est `88.169.112.139`, vous pouvez utiliser les **sous-domaines suivants
à condition de vérifier qu’ils résolvent bien vers cette IP** :

```dotenv
COMPOSE_PROJECT_NAME=matric-poc-prod
MATRIX_DOMAIN=matrix.element-matrix-poc.duckdns.org
SYNAPSE_URL=https://matrix.element-matrix-poc.duckdns.org
ELEMENT_URL=https://element.element-matrix-poc.duckdns.org
RTC_URL=https://rtc.element-matrix-poc.duckdns.org
TURN_HOST=rtc.element-matrix-poc.duckdns.org
SERVER_IP=88.169.112.139
BIND_IP=0.0.0.0
```

Cet exemple définit une **nouvelle identité Matrix**, distincte de l’ancien
`matrix.duckyduckgator.duckdns.org`, puisque vous repartez avec une installation vide.
Le lien à communiquer aux collègues devient :
**https://element.element-matrix-poc.duckdns.org**.
L’ancien lien sans le préfixe `element.` n’est pas publié par ce profil par défaut.

Si le nom vous semble long, choisissez un autre domaine de base et remplacez-le
partout de manière cohérente. Avec un domaine d’entreprise `entreprise.fr`, on
pourrait utiliser `matrix.entreprise.fr`, `element.entreprise.fr` et `rtc.entreprise.fr`.
Les domaines d’exemple `exemple.fr` ne sont pas à conserver dans votre configuration.

Sur une autre connexion Internet, `SERVER_IP` et les DNS doivent utiliser l’IP
publique de cette connexion, pas automatiquement `88.169.112.139`.

## IP publique, IP locale et redirections

Si vous testez sur la même machine qu’avant, derrière la même box :

| Où ? | Valeur attendue |
|---|---|
| DNS des trois noms | `88.169.112.139`, votre IP publique actuelle à confirmer |
| `SERVER_IP` dans `.env` | La même IP publique |
| IP destination des règles NAT sur la box | L’IP LAN de la VM, auparavant `192.168.1.179` ; à vérifier |
| `BIND_IP` dans `.env` | `0.0.0.0` |

L’IP locale `192.168.1.179` n’est pas accessible directement depuis Internet.
L’adresse Tailscale n’est pas à annoncer pour les médias si vos collègues doivent
se connecter sans Tailscale. Si vous changez de VM, adapter la destination NAT.

## Les ports : conserver les valeurs du modèle

| Champs | Valeurs | Usage |
|---|---|---|
| `HTTP_PORT`, `HTTPS_PORT` | `80`, `443` | Pages, API, HTTPS et validation du certificat |
| `LIVEKIT_TCP_PORT` | `7881` | Transport média de secours en TCP |
| `LIVEKIT_UDP_START`, `LIVEKIT_UDP_END` | `15000`, `15100` | Plage audio/vidéo LiveKit |
| `TURN_PORT`, `TURN_TLS_PORT` | `3478`, `5349` | Accès au relais TURN |
| `TURN_UDP_START`, `TURN_UDP_END` | `15200`, `15300` | Plage média relayée par TURN |
| `TLS_MODE` | `provided` | Le script TLS fournit un certificat public à Caddy/TURN |

Ces plages restent sous votre limite de ports `16383`. Il faut que les règles
NAT/pare-feu correspondent exactement aux valeurs choisies. Ne pas ajouter les
ports dans les URL HTTPS de cet exemple ; le port 443 est implicite.

## Les images : ne pas les remplacer par des adresses web

Les champs `SYNAPSE_IMAGE`, `ELEMENT_IMAGE`, `JWT_IMAGE`, `LIVEKIT_IMAGE`,
`COTURN_IMAGE`, `POSTGRES_IMAGE` et `CADDY_IMAGE` désignent les logiciels Docker et
leurs versions. Par exemple `ghcr.io/element-hq/element-web:v1.12.31` est une image
Docker, pas l’adresse de votre interface Element. Conserver les valeurs du modèle
pour le premier test. Les mises à jour de version se préparent ensuite séparément.

## Les secrets : laisser les champs vides au premier remplissage

Laisser vides toutes ces lignes dans le `.env` neuf :

```dotenv
POSTGRES_PASSWORD=
REGISTRATION_SHARED_SECRET=
MACAROON_SECRET=
FORM_SECRET=
LIVEKIT_KEY=
LIVEKIT_SECRET=
TURN_SECRET=
AS_TOKEN=
HS_TOKEN=
```

`python3 scripts/render.py` génère leurs valeurs automatiquement après l’émission
du certificat. Elles servent à la base de données, à Synapse, aux appels et à la
communication entre services. Ce ne sont pas les mots de passe des utilisateurs.
**Une fois générées, ne pas les vider, les remplacer ou les partager.**
Les utilisateurs sont créés séparément avec `bash scripts/create-user.sh`.

## Remplissage et vérification pas à pas

En root, dans le dossier du nouveau projet :

```bash
cd /core/docker/Element_Matrix/matric-poc-prod
cp -n .env.example .env
chmod 0600 .env
nano .env
```

Dans Nano : modifier les valeurs, puis **Ctrl+O**, Entrée pour enregistrer et
**Ctrl+X** pour sortir. Le fichier utilise une ligne `NOM=valeur` par paramètre,
sans espace autour de `=`, sans virgule entre les lignes. Les lignes commençant
par `#` sont des commentaires. Pour ce profil, écrire les valeurs sans guillemets.

Vérifier les noms avec les valeurs réellement choisies, par exemple :

```bash
getent ahostsv4 matrix.element-matrix-poc.duckdns.org
getent ahostsv4 element.element-matrix-poc.duckdns.org
getent ahostsv4 rtc.element-matrix-poc.duckdns.org
```

Les trois doivent résoudre vers la bonne IP publique. Modifier `.env` ne suffit
pas à modifier DuckDNS. Vérifier également le NAT du port 80 avant l’émission TLS.

Continuer ensuite avec les étapes 7 et 8 de [DEPLOIEMENT.md](DEPLOIEMENT.md) :

```bash
python3 scripts/tls.py issue --email VOTRE_ADRESSE_EMAIL
python3 scripts/render.py
docker compose config --quiet
```

Remplacer `VOTRE_ADRESSE_EMAIL` par une adresse réelle pour le compte Let's Encrypt.
Ce paramètre est une adresse de contact, pas un compte SMTP et pas l’activation de
la connexion par e-mail. Le script accepte les conditions de Let's Encrypt.
Le rendu a besoin du certificat, d’où l’ordre des commandes.
Le contrôle Compose se fait après le rendu : avant, les secrets sont vides et les
fichiers générés n’existent pas encore.

Ce document ne configure pas le DNS, ne remplit pas votre `.env` actif et ne démarre
aucun conteneur. Une fois la stack initialisée, ne pas changer `MATRIX_DOMAIN` ou
relancer le rendu pour forcer une modification : suivre la reconfiguration décrite
dans la procédure.
