# Contrat d’intégration au reverse proxy de production

Le vhost et les whitelists sont gérés par l’exploitant. La stack ne génère aucun
fichier de configuration Nginx, n’installe aucun site et n’exécute ni `nginx` ni `systemctl`.
Elle fournit des services sur des ports loopback et les données de découverte Matrix.

## Routes à configurer dans votre vhost

| Route publique sur `https://chat.pro-gx.fr` | Destination locale par défaut | Traitement |
|---|---|---|
| `/` | `http://127.0.0.1:18080` | Element, conserver le chemin |
| `/_matrix/client/`, `/_matrix/media/`, `/_synapse/client/` | `http://127.0.0.1:18008` | Synapse, conserver intégralement le chemin |
| `/_matrix/federation/v1/openid/userinfo` | `http://127.0.0.1:18008` | Exception OpenID pour les appels ; éviter de journaliser ses jetons |
| `/admin/` | `http://127.0.0.1:18082` | Whitelist ; conserver le chemin `/admin/` complet vers le build dédié |
| `/_synapse/admin/` | `http://127.0.0.1:18008` | Whitelist ; conserver intégralement le chemin |
| `/livekit/jwt/` | `http://127.0.0.1:18081` | Retirer le préfixe `/livekit/jwt/` |
| `/livekit/sfu` et `/livekit/sfu/` | `http://127.0.0.1:17880` | Retirer le préfixe ; gérer la connexion WebSocket |

Protéger **les deux** chemins d’administration. Autoriser l’accès depuis les IP
publiques fixes du VPN et des bureaux dans votre configuration Nginx, puis refuser
les autres sources. Aucun filtre IP n’est appliqué par les scripts applicatifs.
La connexion exige toujours un compte administrateur Matrix.
Refuser les autres routes `/_matrix/` et `/_synapse/`, notamment la fédération générale.

Ces ports HTTP sont publiés uniquement sur 127.0.0.1 : Nginx doit tourner sur le même
hôte. Les ports TCP 3306, 5100, 8090 et 8443 déjà utilisés ne sont pas réutilisés.
Si vous changez les ports dans `.env`, reporter les valeurs dans votre vhost.

## Découverte à publier

Le rendu crée deux fichiers JSON :

| URL publique à servir | Fichier contenant la réponse |
|---|---|
| `/.well-known/matrix/client` | `configs/generated/nginx/client.json` |
| `/.well-known/matrix/server` | `configs/generated/nginx/server.json` |

Servir les réponses en `application/json`. Pour la découverte client, prévoir
`Access-Control-Allow-Origin: *`. Les fichiers JSON ne contiennent pas de secrets,
mais leur répertoire parent est privé : reprendre leur contenu dans votre vhost ou
les copier vers un emplacement public lisible par Nginx, sans exposer le reste des
configurations générées. Actualiser ces réponses si les adresses applicatives changent.

Pour ce domaine, la réponse serveur est `{"m.server":"chat.pro-gx.fr:443"}` et la
réponse client annonce le homeserver `https://chat.pro-gx.fr` ainsi que le service
RTC `https://chat.pro-gx.fr/livekit/jwt`.

## Points d’attention pour le proxy

Transmettre Host, l’IP réelle du client et `X-Forwarded-Proto: https` à Synapse.
Ne faire confiance qu’aux proxies connus si un autre proxy/CDN est placé devant.
Activer la transmission des en-têtes WebSocket Upgrade/Connection pour LiveKit.
La taille d’envoi configurée côté Synapse est de 100 Mo : adapter la limite Nginx.
Les flux audio/vidéo utilisent les ports LiveKit/TURN décrits dans la procédure,
indépendamment du routage HTTP.

## Certificat et exploitation

Nginx utilise les fichiers et le renouvellement gérés de votre côté. Le hook
`scripts/tls.py install` ne fait que copier le certificat pour coturn, maintenir
les racines de JWT et actualiser ces conteneurs lorsqu’ils tournent.
Il ne vérifie ni ne recharge Nginx. Le mécanisme de renouvellement du serveur doit
assurer séparément le rechargement nécessaire de votre proxy.

La sauvegarde du projet ne remplace pas celle de votre configuration Nginx.
Après modification du proxy, réaliser vos contrôles habituels de syntaxe, rechargement,
whitelist depuis une IP autorisée/non autorisée et tests publics de messagerie/appels.

Références :
- https://nginx.org/en/docs/http/ngx_http_access_module.html
- https://nginx.org/en/docs/http/websocket.html
- https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass
- https://github.com/etkecc/ketesa#serving-ketesa-under-a-custom-path

## Chemin Ketesa : conserver /admin/

Avec l’image `v1.5.1-subpath-admin`, les fichiers sont sous `/var/public/admin/`.
Transmettre `/admin/` tel quel au backend : dans votre bloc location, utiliser
`proxy_pass http://127.0.0.1:18082;` **sans slash après le port**, en conservant
votre whitelist. Une URL amont avec slash retire le préfixe et sert la page
« Static Web Server » au lieu de Ketesa.
Le fichier applicatif est monté dans `/var/public/admin/config.json`.
