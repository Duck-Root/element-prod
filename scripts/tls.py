#!/usr/bin/env python3
"""Valider et installer un certificat géré par le serveur de production."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

os.chdir(Path(__file__).resolve().parent.parent)
os.umask(0o077)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('mode', choices=['install'])
parser.add_argument('--cert', required=True, help='Chaîne PEM complète du gestionnaire externe')
parser.add_argument('--key', required=True, help='Clé privée PEM correspondante')
args = parser.parse_args()
if os.geteuid() != 0:
    raise SystemExit('Exécuter avec sudo.')
env = dict(line.split('=',1) for line in Path('.env').read_text().splitlines()
           if line.strip() and not line.lstrip().startswith('#'))
host = env.get('MATRIX_DOMAIN', '')
if not re.fullmatch(r'[a-z0-9.-]+', host) or host == 'exemple.fr' or host.endswith('.exemple.fr'):
    raise SystemExit('MATRIX_DOMAIN doit être votre vrai domaine, sans https://.')
if any(env.get(key) != 'https://'+host for key in ('SYNAPSE_URL','ELEMENT_URL','RTC_URL')) or env.get('TURN_HOST') != host:
    raise SystemExit('Profil domaine unique : les URL et TURN_HOST doivent correspondre à MATRIX_DOMAIN.')
state = Path('data')
state.mkdir(parents=True, exist_ok=True, mode=0o700)
lock = (state/'tls-install.lock').open('w')
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit('Une installation TLS est déjà en cours.')

def run(*cmd):
    return subprocess.run(cmd, check=True)

def output(*cmd):
    return subprocess.check_output(cmd)

try:
    source_crt = Path(args.cert).resolve()
    source_key = Path(args.key).resolve()
    roots = Path('/etc/ssl/certs/ca-certificates.crt')
    if not source_crt.is_file() or not source_key.is_file():
        raise SystemExit('Certificat ou clé source absent : vérifier --cert et --key.')
    if output('openssl','x509','-in',str(source_crt),'-pubkey','-noout') != output('openssl','pkey','-in',str(source_key),'-pubout'):
        raise SystemExit('Clé et certificat différents : aucun remplacement effectué.')
    run('openssl','x509','-in',str(source_crt),'-checkend','86400','-noout')
    run('openssl','verify','-CAfile',str(roots),'-untrusted',str(source_crt),
        '-purpose','sslserver','-verify_hostname',host,str(source_crt))
    tls = state/'tls'
    tls.mkdir(parents=True, exist_ok=True, mode=0o755)
    changes = []
    for source,name in [(source_crt,'server.crt'),(source_key,'server.key'),(roots,'ca.crt')]:
        target = tls/name
        if not target.exists() or target.read_bytes() != source.read_bytes():
            changes.append((source,target))
    pending_file = state/'tls-install.pending.json'
    pending = json.loads(pending_file.read_text()) if pending_file.exists() else {'certificate':False,'trust':False}
    if not changes and not pending_file.exists():
        print('Certificat et confiance inchangés : aucune action sur les services.')
        raise SystemExit(0)
    pending['certificate'] |= any(dst.name in ('server.crt','server.key') for _,dst in changes)
    pending['trust'] |= any(dst.name == 'ca.crt' for _,dst in changes)
    if changes:
        backup = Path('backups')/('tls-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        backup.mkdir(parents=True, mode=0o700)
        for name in ('server.crt','server.key','ca.crt'):
            if (tls/name).exists():
                shutil.copy2(tls/name,backup/name)
    # Une activation en échec sera retentée au prochain appel avec le même certificat.
    pending_file.write_text(json.dumps(pending)+'\n')
    for source,target in changes:
        temp = target.with_suffix(target.suffix+'.new')
        shutil.copyfile(source,temp)
        temp.chmod(0o644)
        os.replace(temp,target)
    # data/ est privé ; les sous-montages TLS doivent rester lisibles par les UID des services.
    if Path('configs/generated/jwt.env').exists():
        running = output('docker','compose','ps','--status','running','--services').decode().splitlines()
        if 'coturn' in running and pending['certificate']:
            run('docker','compose','restart','coturn')
        if 'jwt' in running and pending['trust']:
            run('docker','compose','up','-d','--no-deps','--force-recreate','jwt')
    pending_file.unlink(missing_ok=True)
    print('Certificat installé pour les services Docker. Le proxy et le renouvellement restent gérés hors de la stack.')
except subprocess.CalledProcessError as exc:
    raise SystemExit(f'Échec de l’installation TLS (code {exc.returncode}). Corriger la cause ci-dessus puis réexécuter la même commande.') from None
