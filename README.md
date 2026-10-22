# Tests du nouveau déploiement Matrix

Installation vide : aucun compte, salon, secret ou média du POC n’est repris.

Lire `DEPLOIEMENT.md` pour la procédure complète. Les chemins de ce dossier et des
unités systemd sont adaptés à `/core/docker/Element_Matrix/matric-poc-prod`.

Avant de démarrer : choisir trois domaines distincts, renseigner leur DNS et
rediriger les ports vers cette machine. Puis, en root, depuis ce dossier :

```bash
cp -n .env.example .env
chmod 0600 .env
nano .env
python3 scripts/tls.py issue --email administrateur@votre-domaine.fr
python3 scripts/render.py
docker compose config --quiet
docker compose pull
docker compose up -d --wait --wait-timeout 240
bash scripts/create-user.sh --admin
```

Les noms `matrix.exemple.fr`, `element.exemple.fr`, `rtc.exemple.fr` et l’IP
`192.0.2.10` sont des exemples à remplacer. Aucun certificat de production
n’est émis et aucun conteneur neuf n’est démarré lors de la création du dossier.

L’ancien POC reste sauvegardé sous `../matrix-poc-tailscale/` ; ses conteneurs sont
retirés et son timer ACME désactivé pour libérer les ports de la machine.
