# Nginx installé directement sur le serveur

Source : `matrix.conf.template`. Généré : `../generated/nginx/matrix.conf`
(depuis la racine du projet : `configs/generated/nginx/matrix.conf`).

Le générateur remplace domaine, chemins des certificats, IP autorisées et ports
loopback à partir de `.env`. Ne pas installer le modèle avec ses marqueurs `__...__`.

| Route publique | Backend local par défaut |
|---|---|
| `/` | Element `127.0.0.1:18080` |
| `/_matrix/client/`, `/_matrix/media/`, `/_synapse/client/` | Synapse `127.0.0.1:18008` |
| `/_matrix/federation/v1/openid/userinfo` | Synapse, exception nécessaire aux appels |
| `/_synapse/admin/` | Synapse, IP VPN/bureaux uniquement |
| `/admin/` | Ketesa `127.0.0.1:18082`, IP VPN/bureaux uniquement |
| `/livekit/jwt/` | JWT `127.0.0.1:18081`, préfixe retiré |
| `/livekit/sfu` et `/livekit/sfu/` | LiveKit `127.0.0.1:17880`, préfixe retiré, WebSocket |
| `/.well-known/matrix/client` et `/server` | JSON de découverte généré |

Les autres routes `/_matrix/` et `/_synapse/` sont refusées. Le journal d’accès
OpenID est désactivé pour ne pas journaliser ses jetons. Les IP d’administration
vides bloquent tous les accès privés. Le contrôle suppose que Nginx reçoit directement
les connexions Internet : si un autre proxy/CDN est devant, configurer l’IP réelle
avec une liste stricte de proxies de confiance avant d’utiliser ces ACL.

Installation sur Debian, une fois les certificats installés et la stack démarrée :

```bash
install -m 0600 configs/generated/nginx/matrix.conf /etc/nginx/sites-available/matrix-prod.conf
ln -s /etc/nginx/sites-available/matrix-prod.conf /etc/nginx/sites-enabled/matrix-prod.conf
nginx -t
systemctl reload nginx
```

Si le lien existe déjà, le conserver et mettre à jour le fichier source. Retirer
un éventuel ancien vhost du même domaine, après sauvegarde. Ne pas désactiver les
autres sites du serveur. Ce fichier doit être chargé dans le contexte `http` de
Nginx ; l’installation Debian standard inclut `sites-enabled` dans ce contexte.

Les ports TCP 3306, 5100, 8090 et 8443 sont déjà publiés par d’autres applications.
Aucun backend du vhost Matrix ne les utilise. Conserver les ports loopback proposés,
et ajouter le vhost au Nginx existant sans changer les autres sites. Les ports HTTP
internes 80/8080 des conteneurs ne sont pas des réservations sur l’hôte.

Le vhost lit les certificats dans le chemin absolu `data/tls` de ce projet. Le
processus maître Nginx doit pouvoir les lire (installation standard avec maître root).
Le vhost ne monte aucun fichier dans un conteneur Nginx : il n’y en a pas.

Les ports 80/443 appartiennent à Nginx hôte ; les ports média restent indépendants.
Le certificat est géré par l’outil du serveur, puis copié avec `scripts/tls.py install`.
Ce vhost redirige HTTP vers HTTPS et n’inclut pas de webroot de validation : si votre
gestionnaire utilise une validation HTTP, adapter Nginx selon ses besoins.

Références :
- https://nginx.org/en/docs/http/ngx_http_access_module.html
- https://nginx.org/en/docs/http/websocket.html
- https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass
- https://github.com/etkecc/ketesa#serving-ketesa-under-a-custom-path
