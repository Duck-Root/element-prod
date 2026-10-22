# Vhost Nginx : un domaine, accès public, administration filtrée

Le fichier `matrix.conf` est un modèle complet, à adapter avant activation.
Il ne modifie pas automatiquement la stack Caddy existante.

## Valeurs à remplacer

| Valeur dans le modèle | Remplacement |
|---|---|
| `nomdedomaine.fr` | Le domaine public définitif de la nouvelle installation |
| `198.51.100.10/32` | IP publique fixe de sortie du VPN professionnel |
| `203.0.113.20/32` | IP publique fixe des bureaux |
| `/tls/server.crt` | Certificat complet et intermédiaires, monté dans Nginx |
| `/tls/server.key` | Clé du certificat, montée dans Nginx |

Remplacer chacune des deux IP aux deux endroits : `/admin/` et
`/_synapse/admin/`. Ces adresses d'exemple n'autorisent pas votre réseau réel.
Le contrôle porte sur l'IP source du navigateur, pas celle du serveur Matrix.
Le compte administrateur et son mot de passe restent nécessaires.

## Réseau et services requis

Nginx est ici le point d'entrée DIRECT depuis Internet, dans le même réseau Docker
que les services `synapse:8008`, `element:80`, `jwt:8080`, `livekit:7880` et
`ketesa:8080`. Les noms ne sont pas résolus par un Nginx installé sur l'hôte sans
adaptation : dans ce cas, exposer les services sur des adresses privées/loopback
appropriées et remplacer les destinations du modèle. Ne pas exposer directement
les API internes sur Internet.

Le Compose neuf fourni précédemment utilise encore Caddy et ne contient pas Ketesa.
Pour utiliser ce modèle, il faudra remplacer le service proxy par Nginx, monter le
fichier en lecture seule vers `/etc/nginx/conf.d/default.conf`, monter `data/tls`
vers `/tls` en lecture seule, conserver les alias réseau correspondant au domaine
public et ajouter Ketesa au même réseau. Adapter aussi le healthcheck et les scripts
qui utilisent encore les commandes Caddy. Nginx et Caddy ne doivent pas publier
simultanément les mêmes ports 80/443 sur la même IP.

Nginx doit pouvoir résoudre les services au démarrage. Avec ce modèle à destinations
statiques, recharger Nginx après une recréation de services qui changerait leurs IP
Docker. En cas d'intégration dans un proxy existant, éviter les doublons de vhost.

Si un autre reverse proxy ou un CDN est placé devant Nginx, configurer d'abord
l'IP réelle avec une liste stricte de proxies de confiance ; sinon les règles
`allow` verront l'IP du proxy. Ne pas activer la confiance dans un X-Forwarded-For
arbitraire envoyé par Internet. Aucun réseau Tailscale n'est autorisé par ce modèle.

## Configuration des applications

Pour une installation neuve sur ce domaine unique :

- Synapse : `server_name: nomdedomaine.fr`, `public_baseurl: https://nomdedomaine.fr/`,
  `x_forwarded: true` sur son listener interne.
- Element : homeserver `https://nomdedomaine.fr`, permaliens sur cette même origine.
- Découverte RTC : `https://nomdedomaine.fr/livekit/jwt`.
- JWT : URL publique LiveKit `wss://nomdedomaine.fr/livekit/sfu`, identité du homeserver
  cohérente avec `server_name`, et accès interne à Synapse inchangé.
- TURN : nom `nomdedomaine.fr`, certificat couvrant ce nom, IPv4 publique annoncée.
- Ketesa : build **pour `/admin`**, avec serveur restreint à `https://nomdedomaine.fr`.

Ne pas appliquer un changement de `server_name` à une base Matrix déjà initialisée.
Le générateur `scripts/render.py` et le script TLS du profil précédent imposent
encore trois domaines distincts ; il faut les adapter avant d'utiliser ce profil
unique. Changer seulement les URL dans `.env` ne suffit donc pas.

Exemple de configuration Ketesa, à monter dans son répertoire public `config.json`
avec la version retenue :

```json
{
  "restrictBaseUrl": "https://nomdedomaine.fr",
  "wellKnownDiscovery": false
}
```

Ketesa fournit des builds `*-subpath-admin` et un argument de construction
`BASE_PATH=/admin`. Choisir une version épinglée compatible avec votre Synapse.
Nginx retire `/admin/` avant de transmettre au serveur de fichiers du conteneur.

## Certificats et ports

Ce vhost attend un certificat public déjà émis, par exemple via DNS-01 : aucun port
80 entrant n'est nécessaire pour cette méthode d'émission. Le serveur HTTP du modèle
ne fait que rediriger vers HTTPS ; il n'expose pas de webroot ACME HTTP-01.

Le port 443 reste nécessaire pour accéder à Element depuis Internet. Les médias
restent directs : TCP 7881, UDP 15000–15100, TURN TCP/UDP 3478, TCP 5349 et UDP
15200–15300 dans le profil précédent. Le vhost ne remplace pas ces redirections.
PostgreSQL et les ports HTTP internes n'ont pas à être publiés.

## Contrôles avant et après activation

D'abord remplacer les valeurs et adapter la stack, puis, dans le conteneur Nginx :

```bash
nginx -t
nginx -s reload
```

Tester depuis une IP autorisée puis une IP non autorisée. `/admin/` et
`/_synapse/admin/v1/server_version` doivent renvoyer 403 depuis le réseau non autorisé.
Depuis le réseau autorisé, l'API admin exige toujours un jeton administrateur :
une erreur d'authentification sans jeton est normale.

Vérifier Element, les versions Matrix, la découverte, la santé JWT puis un appel
avec partage d'écran depuis Internet. La fédération générale doit rester refusée.
Ne pas archiver les journaux contenant des jetons d'accès ; le journal d'accès de
l'endpoint OpenID est désactivé dans ce modèle.

Références :
- https://nginx.org/en/docs/http/ngx_http_access_module.html
- https://nginx.org/en/docs/http/websocket.html
- https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass
- https://github.com/etkecc/ketesa#serving-ketesa-under-a-custom-path
