import os
os.environ['DATABASE_URL']='sqlite:///./test_nexora.db'
from fastapi.testclient import TestClient
from backend.main import app
from backend.db import Base, engine, Session, Customer, Approval, Document
import pytest

@pytest.fixture(scope='module')
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:yield c
    Base.metadata.drop_all(engine)

def auth(client,email='admin@nexora.demo'):
    r=client.post('/api/v1/auth/login',json={'email':email,'password':'NexoraDemo!2026'})
    assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['access_token']}

def test_unauthorized_and_invalid_login(client):
    assert client.get('/api/v1/dashboard/summary').status_code==401
    assert client.post('/api/v1/auth/login',json={'email':'admin@nexora.demo','password':'wrong'}).status_code==401

def test_seed_and_metrics(client):
    h=auth(client);r=client.get('/api/v1/dashboard/summary',headers=h)
    assert r.status_code==200
    assert r.json()['metrics']['customers']==500
    assert r.json()['metrics']['transactions']==1000
    assert len(r.json()['agents'])==12

def test_read_only_role_cannot_write(client):
    h=auth(client,'reviewer9@nexora.demo')
    assert client.post('/api/v1/scenarios/launch',headers=h,json={'scenario':0}).status_code==403
    assert client.put('/api/v1/settings',headers=h,json={'risk_threshold':30}).status_code in [403,422]

def test_scenario_stops_for_human_and_separation(client):
    h=auth(client);r=client.post('/api/v1/scenarios/launch',headers=h,json={'scenario':3})
    assert r.status_code==200,r.text
    result=r.json();wf=result['workflow'];assert wf['status']=='Waiting for Human'
    assert len(wf['executions'])==12
    approvals=client.get('/api/v1/records/approvals?q='+result['customer']['id'],headers=h).json()['items'];a=approvals[0]
    assert client.post('/api/v1/approvals/'+a['id']+'/decision',headers=h,json={'action':'Approve','reason':'Reviewed all available evidence'}).status_code==403
    reviewer=auth(client,'reviewer7@nexora.demo')
    assert client.post('/api/v1/approvals/'+a['id']+'/decision',headers=reviewer,json={'action':'Approve','reason':'Reviewed all available evidence'}).status_code==409
    bad=client.post('/api/v1/documents/'+result['customer']['id'],headers=h,files={'file':('bad.html',b'<script>alert(1)</script>','text/html')});assert bad.status_code==415
    good=client.post('/api/v1/documents/'+result['customer']['id'],headers=h,files={'file':('demo.pdf',b'%PDF-1.4\nsynthetic test evidence','application/pdf')});assert good.status_code==201
    first=client.post('/api/v1/approvals/'+a['id']+'/decision',headers=reviewer,json={'action':'Approve','reason':'Reviewed all available synthetic evidence'});assert first.status_code==200,first.text
    assert first.json()['status']=='Pending'
    assert client.post('/api/v1/approvals/'+a['id']+'/decision',headers=reviewer,json={'action':'Approve','reason':'Attempt duplicate reviewer authorization'}).status_code==409
    second=client.post('/api/v1/approvals/'+a['id']+'/decision',headers=auth(client,'reviewer5@nexora.demo'),json={'action':'Approve','reason':'Independent second reviewer checked evidence'});assert second.status_code==200,second.text
    assert second.json()['status']=='Approved'

def test_consent_duplicate_and_masking(client):
    h=auth(client);payload={'name':'Synthetic Test','email':'test@example.test','id_last4':'1234'}
    assert client.post('/api/v1/onboarding',headers=h,json=payload).status_code==422
    payload.update(privacy_consent=True,kyc_consent=True,terms=True)
    r=client.post('/api/v1/onboarding',headers=h,json=payload);assert r.status_code==201
    assert r.json()['customer']['profile']['id_masked']=='**** **** 1234'
    assert 'id_last4' not in r.json()['customer']['profile']
    assert client.post('/api/v1/onboarding',headers=h,json=payload).status_code==409

def test_case_notes_and_csv(client):
    h=auth(client);cid=client.get('/api/v1/records/customers?size=1',headers=h).json()['items'][0]['id']
    case=client.post('/api/v1/cases',headers=h,json={'customer_id':cid,'title':'Review synthetic evidence','type':'AML'}).json()
    r=client.patch('/api/v1/cases/'+case['id'],headers=h,json={'note':'Evidence received for review','status':'Investigating'});assert r.status_code==200
    assert r.json()['notes'][0]['text']=='Evidence received for review'
    r=client.get('/api/v1/export/cases',headers=h);assert r.status_code==200;assert 'text/csv' in r.headers['content-type']

def test_refresh_rotation(client):
    result=client.post('/api/v1/auth/login',json={'email':'admin@nexora.demo','password':'NexoraDemo!2026'}).json()
    token=result['refresh_token'];assert client.post('/api/v1/auth/refresh',json={'refresh_token':token}).status_code==200
    assert client.post('/api/v1/auth/refresh',json={'refresh_token':token}).status_code==401
