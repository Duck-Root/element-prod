#!/usr/bin/env python3
"""Installer un certificat existant, ou utiliser DNS-01 DuckDNS, sans arrêter Nginx."""
import argparse
import datetime
import fcntl
import getpass
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlsplit

os.chdir(Path(__file__).resolve().parent.parent)
os.umask(0o077)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('mode', choices=['install', 'issue', 'renew'])
parser.add_argument('--cert', help='Chaîne complète PEM, pour install')
parser.add_argument('--key', help='Clé privée PEM, pour install')
parser.add_argument('--email', help='Contact ACME, pour issue')
args = parser.parse_args()
if os.geteuid() != 0:
    raise SystemExit('Exécuter avec sudo.')
env = dict(line.split('=',1) for line in Path('.env').read_text().splitlines()
           if line.strip() and not line.lstrip().startswith('#'))
host = env.get('MATRIX_DOMAIN', '')
if not re.fullmatch(r'[a-z0-9.-]+', host) or host == 'exemple.fr' or host.endswith('.exemple.fr'):
    raise SystemExit('MATRIX_DOMAIN doit être votre vrai domaine, sans https://.')
for key in ('SYNAPSE_URL','ELEMENT_URL','RTC_URL'):
    if env.get(key) != 'https://'+host:
        raise SystemExit(f'Profil domaine unique : {key}=https://{host}')
if env.get('TURN_HOST') != host:
    raise SystemExit('TURN_HOST doit correspondre à MATRIX_DOMAIN.')
acme = Path('data/acme')
acme.mkdir(parents=True, exist_ok=True, mode=0o700)
lock = (acme/'operation.lock').open('w')
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit('Une opération TLS est déjà en cours.')

def run(*cmd):
    return subprocess.run(cmd, check=True)

def output(*cmd):
    return subprocess.check_output(cmd)

try:
    if args.mode == 'install':
        if not args.cert or not args.key:
            raise SystemExit('install exige --cert FULLCHAIN.pem --key PRIVKEY.pem')
        source_crt = Path(args.cert).resolve()
        source_key = Path(args.key).resolve()
    else:
        if not host.endswith('.duckdns.org'):
            raise SystemExit('L’émission intégrée utilise DuckDNS. Sinon utiliser install avec votre certificat existant.')
        cert_dir = acme/'dns01/certificates'
        source_crt = cert_dir/(host+'.crt')
        source_key = cert_dir/(host+'.key')
        need_acme = True
        if args.mode == 'renew':
            if not source_crt.exists():
                raise SystemExit('Aucun certificat DNS-01 émis ici. Utiliser issue ou le renouvellement de votre gestionnaire externe.')
            if subprocess.run(['openssl','x509','-in',str(source_crt),'-checkend',str(30*86400),'-noout'],
                              stdout=subprocess.DEVNULL).returncode == 0:
                print('Certificat valide plus de 30 jours : vérification des copies installées.')
                need_acme = False
        elif source_crt.exists():
            raise SystemExit('Un certificat DNS-01 existe déjà : utiliser renew.')
        if need_acme:
            email_file = acme/'email'
            if args.email:
                email_file.write_text(args.email.strip()+'\n')
            if not email_file.exists():
                raise SystemExit('Ajouter --email votre-adresse@domaine.fr lors de la première émission.')
            token_file = acme/'duckdns-token'
            if not token_file.exists() or not token_file.read_text().strip():
                if not os.isatty(0):
                    raise SystemExit('Saisir le token en terminal interactif ou préparer data/acme/duckdns-token en mode 0600.')
                token = getpass.getpass('Token DuckDNS (saisie masquée, jamais affiché) : ').strip()
                if not token:
                    raise SystemExit('Token vide.')
                token_file.write_text(token+'\n')
            token_file.chmod(0o600)
            cmd = ['docker','compose','-p',env['COMPOSE_PROJECT_NAME']+'-acme',
                   '-f','compose.acme.yaml','run','--rm','--no-deps','acme',
                   '--path','/acme/dns01','--accept-tos','--email',email_file.read_text().strip(),
                   '--key-type','rsa3072','--dns','duckdns','--dns.resolvers','1.1.1.1:53',
                   '--dns.resolvers','8.8.8.8:53','--domains',host]
            cmd += ['run'] if args.mode == 'issue' else ['renew','--days','30']
            run(*cmd)
    roots = Path('/etc/ssl/certs/ca-certificates.crt')
    if output('openssl','x509','-in',str(source_crt),'-pubkey','-noout') != output('openssl','pkey','-in',str(source_key),'-pubout'):
        raise SystemExit('Clé et certificat différents.')
    run('openssl','x509','-in',str(source_crt),'-checkend','86400','-noout')
    run('openssl','verify','-CAfile',str(roots),'-untrusted',str(source_crt),
        '-purpose','sslserver','-verify_hostname',host,str(source_crt))
    tls = Path('data/tls')
    tls.mkdir(parents=True, exist_ok=True, mode=0o755)
    changes = []
    for source,name in [(source_crt,'server.crt'),(source_key,'server.key'),(roots,'ca.crt')]:
        target = tls/name
        if not target.exists() or target.read_bytes() != source.read_bytes():
            changes.append((source,target))
    if not changes:
        print('Certificat et confiance inchangés.')
        raise SystemExit(0)
    backup = acme/'backups'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True, mode=0o700)
    for source,target in changes:
        if target.exists():
            shutil.copy2(target,backup/target.name)
        temp = target.with_suffix(target.suffix+'.new')
        shutil.copyfile(source,temp)
        temp.chmod(0o644)
        os.replace(temp,target)
    # Les fichiers sont sous data/ en 0700 ; les montages doivent être lisibles par les services.
    if Path('configs/generated/jwt.env').exists():
        running = output('docker','compose','ps','--status','running','--services').decode().splitlines()
        if 'coturn' in running:
            run('docker','compose','restart','coturn')
        if 'jwt' in running and any(dst.name=='ca.crt' for _,dst in changes):
            run('docker','compose','up','-d','--no-deps','--force-recreate','jwt')
    if shutil.which('nginx') and subprocess.run(['systemctl','is-active','--quiet','nginx']).returncode == 0:
        run('nginx','-t')
        run('systemctl','reload','nginx')
    print('Certificat public installé. Aucun conteneur proxy et aucun arrêt de Nginx.')
except subprocess.CalledProcessError as exc:
    raise SystemExit(f'Échec TLS (code {exc.returncode}) : voir la cause ci-dessus. Les anciens fichiers sont sauvegardés si remplacés.') from None
