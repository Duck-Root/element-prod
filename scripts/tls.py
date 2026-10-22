#!/usr/bin/env python3
"""Certificats HTTP-01 pour une installation neuve à trois domaines."""
import argparse
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit

os.chdir(Path(__file__).resolve().parent.parent)
os.umask(0o077)
parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=['issue', 'renew'])
parser.add_argument('--email')
args = parser.parse_args()
if os.geteuid() != 0:
    raise SystemExit('Exécuter avec sudo.')
env = dict(line.split('=', 1) for line in Path('.env').read_text().splitlines()
           if line.strip() and not line.lstrip().startswith('#'))
hosts = sorted({env['MATRIX_DOMAIN'], env['TURN_HOST']} |
               {urlsplit(env[key]).hostname for key in ('SYNAPSE_URL', 'ELEMENT_URL', 'RTC_URL')})
if any(not host or not all(c in 'abcdefghijklmnopqrstuvwxyz0123456789.-' for c in host) for host in hosts):
    raise SystemExit('Noms DNS invalides.')
acme = Path('data/acme')
acme.mkdir(parents=True, exist_ok=True, mode=0o700)
lock = (acme/'operation.lock').open('w')
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit('Une opération ACME est déjà en cours.')
email_path = acme/'email'
if args.email:
    email_path.write_text(args.email.strip()+'\n')
if not email_path.exists():
    raise SystemExit('Première émission : ajouter --email administrateur@votre-domaine.fr')
crt = Path('data/tls/server.crt')
if args.mode == 'issue' and crt.exists():
    raise SystemExit('Certificat existant : utiliser renew.')
if args.mode == 'renew':
    if not crt.exists():
        raise SystemExit('Certificat absent : utiliser issue.')
    if subprocess.run(['openssl', 'x509', '-in', str(crt), '-checkend', str(30*86400), '-noout'],
                      stdout=subprocess.DEVNULL).returncode == 0:
        print('Certificat valide plus de 30 jours : aucune interruption.')
        raise SystemExit(0)

def run(*cmd):
    return subprocess.run(cmd, check=True)

stopped = False
try:
    if args.mode == 'renew':
        run('docker', 'compose', 'stop', 'proxy')
        stopped = True
    cmd = ['docker', 'compose', '-p', env['COMPOSE_PROJECT_NAME']+'-acme',
           '-f', 'compose.acme.yaml', 'run', '--rm', '--service-ports', 'acme',
           '--path', '/acme', '--accept-tos', '--email', email_path.read_text().strip(),
           '--key-type', 'rsa3072', '--http', '--http.port', ':80']
    for host in hosts:
        cmd += ['--domains', host]
    cmd += ['run'] if args.mode == 'issue' else ['renew', '--days', '30']
    run(*cmd)
    source = acme/'certificates'/hosts[0]
    source_crt = Path(str(source)+'.crt')
    source_key = Path(str(source)+'.key')
    def openssl(*cmd):
        return subprocess.check_output(['openssl', *cmd])
    if openssl('x509', '-in', str(source_crt), '-pubkey', '-noout') != openssl('pkey', '-in', str(source_key), '-pubout'):
        raise SystemExit('Clé et certificat différents.')
    run('openssl', 'x509', '-in', str(source_crt), '-checkend', '86400', '-noout')
    roots = Path('/etc/ssl/certs/ca-certificates.crt')
    for host in hosts:
        run('openssl', 'verify', '-CAfile', str(roots), '-untrusted', str(source_crt),
            '-verify_hostname', host, str(source_crt))
    tls = Path('data/tls')
    tls.mkdir(parents=True, exist_ok=True, mode=0o755)
    if crt.exists():
        import datetime
        backup = acme/'backups'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        backup.mkdir(parents=True, mode=0o700)
        for name in ('server.crt', 'server.key', 'ca.crt'):
            shutil.copy2(tls/name, backup/name)
    for src, name in [(source_crt, 'server.crt'), (source_key, 'server.key')]:
        tmp = tls/(name+'.new')
        shutil.copyfile(src, tmp)
        tmp.chmod(0o644)
        os.replace(tmp, tls/name)
    # Ce bundle reste inchangé lors des renouvellements : JWT le monte comme fichier.
    if not (tls/'ca.crt').exists():
        shutil.copyfile(roots, tls/'ca.crt')
        (tls/'ca.crt').chmod(0o644)
    if args.mode == 'renew':
        run('docker', 'compose', 'restart', 'coturn')
    print('Certificat public vérifié et installé.')
finally:
    if stopped:
        run('docker', 'compose', 'start', 'proxy')
