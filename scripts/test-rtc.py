#!/usr/bin/env python3
"""Test réel login -> salon -> transport -> OpenID -> JWT, sans navigateur."""
import base64, getpass, json, re, ssl, urllib.request, urllib.error, urllib.parse
from pathlib import Path
e=dict(line.split('=',1) for line in Path('.env').read_text().splitlines() if line and not line.startswith('#'))
ctx=ssl.create_default_context(cafile='data/tls/ca.crt')
base=e['SYNAPSE_URL']; token=None; room=None

def req(url, data=None, method=None):
    headers={'Content-Type':'application/json'}
    if token and url.startswith(base+'/'): headers['Authorization']='Bearer '+token
    r=urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(),headers=headers,method=method)
    try:
        with urllib.request.urlopen(r,context=ctx,timeout=30) as resp: return json.load(resp)
    except urllib.error.HTTPError as exc:
        print('ÉCHEC HTTP', exc.code, urllib.parse.urlsplit(url).path)
        try:
            detail = json.loads(exc.read(16384))
            # Afficher uniquement les champs d’erreur, jamais les réponses JWT.
            message = str(detail.get('error', ''))[:2000]
            sensitive = [token] + [v for k,v in e.items() if any(x in k for x in ('SECRET','TOKEN','PASSWORD','KEY'))]
            sensitive += [globals().get('oid', {}).get('access_token')]
            for value in sensitive:
                if value: message = message.replace(value, '[masqué]')
            message = re.sub(r'eyJ[A-Za-z0-9_.-]+', '[JWT masqué]', message)
            print('Code Matrix :', detail.get('errcode', 'absent'))
            print('Détail :', message)
        except (ValueError, AttributeError):
            print('Réponse non JSON ; consulter les logs serveur.')
        raise

user=input('Utilisateur de test : ')
login=req(base+'/_matrix/client/v3/login',{'type':'m.login.password','identifier':{'type':'m.id.user','user':user},'password':getpass.getpass()})
token=login['access_token']
try:
    room=req(base+'/_matrix/client/v3/createRoom',{'preset':'private_chat','name':'Diagnostic MatrixRTC','creation_content':{'m.federate':False}})['room_id']
    transport=req(base+'/_matrix/client/unstable/org.matrix.msc4143/rtc/transports')
    assert e['RTC_URL']+'/livekit/jwt' in json.dumps(transport), transport
    print('OK transport authentifié')
    # Delayed Event : programmer un état puis annuler immédiatement.
    import urllib.parse
    rid=urllib.parse.quote(room,safe='')
    delayed=req(base+'/_matrix/client/v3/rooms/'+rid+'/state/org.matrix.msc3401.call.member/diagnostic?org.matrix.msc4140.delay=60000',{},'PUT')
    did=urllib.parse.quote(delayed['delay_id'],safe='')
    req(base+'/_matrix/client/unstable/org.matrix.msc4140/delayed_events/'+did,{'action':'cancel'})
    print('OK MSC4140 programmation/annulation')
    oid=req(base+'/_matrix/client/v3/user/'+urllib.parse.quote(login['user_id'],safe='')+'/openid/request_token',{})
    discovery=req('https://'+e['MATRIX_DOMAIN']+'/.well-known/matrix/server')
    assert discovery['m.server'].endswith(':443')
    print('OK découverte OpenID sur HTTPS 443')
    result=req(e['RTC_URL']+'/livekit/jwt/sfu/get',{'room':room,'openid_token':oid,'device_id':login['device_id']})
    assert result.get('jwt')
    print('OK JWT via /sfu/get : authentification OpenID et création de salle LiveKit franchies')
    modern=req(base+'/_matrix/client/unstable/io.element.msc4195/rtc/livekit/get_token',{'server_name':e['MATRIX_DOMAIN'],'url':result['url'],'room_id':room,'slot_id':'m.call','member_id':'diagnostic'})
    assert modern['jwt']
    print('OK endpoint RTC délégué par Synapse (MSC4512)')
    jwt=result['jwt']; payload=jwt.split('.')[1]; claims=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
    assert result['url']==e['RTC_URL'].replace('https://','wss://')+'/livekit/sfu'
    assert claims['video']['roomJoin'] is True
    print('OK JWT LiveKit reçu (secret non affiché). Aucun flux média testé.')
finally:
    if room:
        req(base+'/_matrix/client/v3/rooms/'+urllib.parse.quote(room,safe='')+'/leave',{})
        req(base+'/_matrix/client/v3/rooms/'+urllib.parse.quote(room,safe='')+'/forget',{})
    req(base+'/_matrix/client/v3/logout',{})
