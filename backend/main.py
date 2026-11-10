import os, io, csv, json, hashlib, base64, secrets, time, re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request, Query
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy import select, func, or_
from backend.db import *
from backend.security import *
from backend.seed import seed, AGENTS, SCENARIOS
from backend.workflow import run_workflow
from backend.ml import predict, MODEL

@asynccontextmanager
async def lifespan(app):
    seed()
    yield
app=FastAPI(title='NEXORA Banking Intelligence',version='1.0.0',description='Synthetic banking operations demonstration. No live identity, sanctions, or payment integrations.',lifespan=lifespan)
limits=defaultdict(list)
@app.middleware('http')
async def headers(request:Request,call_next):
    correlation=secrets.token_hex(8)
    if request.url.path.endswith('/login'):
        key=request.client.host if request.client else 'unknown';stamp=time.monotonic()
        limits[key]=[t for t in limits[key] if stamp-t<60]
        if len(limits[key])>=20: return Response('Too many login attempts',429)
        limits[key].append(stamp)
    response=await call_next(request)
    response.headers.update({'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'same-origin','X-Request-ID':correlation,'Cache-Control':'no-store'})
    return response

def audit(s,user,action,target,detail=None):
    s.add(Audit(actor=user.email,action=action,target=str(target),detail=detail or {}))
def required(s,model,id):
    obj=s.get(model,id)
    if not obj: raise HTTPException(404,'Record not found')
    return obj
class Login(BaseModel):
    email:str=Field(max_length=200)
    password:str=Field(max_length=256)
class TokenInput(BaseModel): refresh_token:str
@app.get('/api/v1/health')
def health():
    with Session() as s:s.execute(select(1))
    return {'status':'healthy','demo':DEMO,'storage':'PostgreSQL' if not url.startswith('sqlite') else 'Ephemeral demo SQLite' if os.getenv('VERCEL') else 'Local SQLite','durable':not os.getenv('VERCEL') or not url.startswith('sqlite')}
@app.post('/api/v1/auth/login')
def login(data:Login):
    with Session() as s:
        user=s.scalar(select(User).where(User.email==data.email.lower().strip()))
        try:
            if not user or not ph.verify(user.password_hash,data.password):raise ValueError()
        except Exception:raise HTTPException(401,'Invalid email or password')
        audit(s,user,'Signed in',user.id);return token_pair(s,user)
@app.post('/api/v1/auth/refresh')
def refresh(data:TokenInput):
    with Session() as s:
        token=s.scalar(select(Refresh).where(Refresh.digest==hashlib.sha256(data.refresh_token.encode()).hexdigest()).with_for_update())
        if not token or token.used or token.expires.replace(tzinfo=timezone.utc)<now():raise HTTPException(401,'Refresh token is invalid or already used')
        token.used=1;return token_pair(s,required(s,User,token.user_id))
@app.get('/api/v1/auth/me')
def me(user=Depends(current_user)):return serialize(user)

class OnboardingInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=2,max_length=150)
    email:str=Field(min_length=5,max_length=200)
    country:str=Field(default='India',max_length=80)
    dob:str=Field(default='',max_length=10)
    phone:str=Field(default='',max_length=30)
    address:str=Field(default='',max_length=500)
    occupation:str=Field(default='',max_length=100)
    income:float=Field(default=0,ge=0,le=1e12)
    account_type:str=Field(default='Savings',max_length=30)
    source_of_funds:str=Field(default='Salary',max_length=100)
    purpose:str=Field(default='',max_length=500)
    volume:float=Field(default=0,ge=0,le=1e12)
    channel:str=Field(default='Email',max_length=30)
    id_type:str=Field(default='Passport',max_length=50)
    id_last4:str=Field(default='',pattern=r'^\d{0,4}$')
    document_expiry:str=Field(default='',max_length=10)
    privacy_consent:bool=False
    kyc_consent:bool=False
    terms:bool=False
    draft:bool=False
    @field_validator('email')
    @classmethod
    def email_valid(cls,v):
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',v):raise ValueError('A valid email is required')
        return v.lower().strip()

@app.post('/api/v1/onboarding',status_code=201)
def onboarding(data:OnboardingInput,user=Depends(current_user)):
    authorize(user,{'Super Administrator','Banking Operations Manager','KYC Analyst'})
    if not data.draft and not all([data.privacy_consent,data.kyc_consent,data.terms]):raise HTTPException(422,'All three consents are required')
    if data.dob:
        try:
            age=(now().date()-datetime.strptime(data.dob,'%Y-%m-%d').date()).days/365.25
            if age<18 or age>120:raise ValueError()
        except ValueError:raise HTTPException(422,'Date of birth must identify an adult aged 18–120')
    with Session() as s:
        if s.scalar(select(Customer).where(Customer.email==data.email)):raise HTTPException(409,'An application already exists for this email')
        values=data.model_dump();values.pop('id_last4');values['id_masked']='**** **** '+(data.id_last4 or '----');values['consent']=all([data.privacy_consent,data.kyc_consent,data.terms]);values['synthetic']=True
        c=Customer(name=data.name,email=data.email,country=data.country,status='Draft' if data.draft else 'Submitted',profile=values,creator_id=user.id);s.add(c);s.flush()
        application=Application(customer_id=c.id,status=c.status,data=values);s.add(application);audit(s,user,'Draft saved' if data.draft else 'Application submitted',c.id);s.commit()
        return {'customer':serialize(c),'application':serialize(application)}
@app.patch('/api/v1/onboarding/{id}')
def resume_draft(id:str,data:OnboardingInput,user=Depends(current_user)):
    authorize(user,{'Super Administrator','Banking Operations Manager','KYC Analyst'})
    with Session() as s:
        c=required(s,Customer,id)
        if c.status!='Draft':raise HTTPException(409,'Only draft applications can be edited')
        if c.creator_id!=user.id and user.role!='Super Administrator':raise HTTPException(403,'This draft belongs to another operator')
        if not data.draft and not all([data.privacy_consent,data.kyc_consent,data.terms]):raise HTTPException(422,'All three consents are required')
        other=s.scalar(select(Customer).where(Customer.email==data.email,Customer.id!=id))
        if other:raise HTTPException(409,'Email already registered')
        values=data.model_dump();values.pop('id_last4');values['id_masked']='**** **** '+(data.id_last4 or '----');values['consent']=all([data.privacy_consent,data.kyc_consent,data.terms]);values['synthetic']=True
        c.name=data.name;c.email=data.email;c.country=data.country;c.profile=values;c.status='Draft' if data.draft else 'Submitted'
        a=s.scalar(select(Application).where(Application.customer_id==id));a.data=values;a.status=c.status
        audit(s,user,'Draft updated',id);s.commit();return serialize(c)

TABLES={'customers':Customer,'onboarding':Customer,'transactions':Transaction,'alerts':Alert,'cases':Case,'rules':Rule,'workflows':Workflow,'approvals':Approval,'audit':Audit,'documents':Document,'users':User}
@app.get('/api/v1/dashboard/summary')
def dashboard(days:int=Query(30,ge=1,le=365),user=Depends(current_user)):
    with Session() as s:
        customers=s.scalars(select(Customer)).all();transactions=s.scalars(select(Transaction).where(Transaction.created_at>=now()-timedelta(days=days))).all();alerts=s.scalars(select(Alert).where(Alert.created_at>=now()-timedelta(days=days))).all();apps=s.scalars(select(Application).where(Application.created_at>=now()-timedelta(days=days))).all();cases=s.scalars(select(Case)).all();workflows=s.scalars(select(Workflow)).all()
        risk=[{'name':n,'value':sum(1 for c in customers if lo<=c.risk<hi),'fill':color} for n,lo,hi,color in [('Low',0,35,'#34d399'),('Medium',35,65,'#fbbf24'),('High',65,101,'#fb7185')]]
        trend=[]
        for d in range(min(days,30)-1,-1,-1):
            date=(now()-timedelta(days=d)).date()
            trend.append({'date':date.strftime('%d %b'),'applications':sum(1 for x in apps if x.created_at.date()==date),'alerts':sum(1 for x in alerts if x.created_at.date()==date),'transactions':sum(1 for x in transactions if x.created_at.date()==date),'volume':round(sum(x.amount for x in transactions if x.created_at.date()==date))})
        executions=[x for w in workflows for x in w.executions]
        metrics={'customers':len(customers),'applications':len(apps),'pending_kyc':sum(c.status=='KYC Pending' for c in customers),'verified':sum(c.status=='Approved' for c in customers),'high_risk':sum(c.risk>=65 for c in customers),'fraud_alerts':len([a for a in alerts if a.status!='Resolved']),'suspicious_transactions':sum(t.status=='Flagged' for t in transactions),'pending_approvals':s.scalar(select(func.count()).select_from(Approval).where(Approval.status=='Pending')),'transaction_volume':sum(t.amount for t in transactions),'transactions':len(transactions),'open_cases':sum(c.status not in ['Closed','False Positive'] for c in cases),'agent_executions':len(executions)}
        return {'metrics':metrics,'risk':risk,'trend':trend,'funnel':[{'name':st,'value':sum(c.status==st for c in customers)} for st in ['Submitted','KYC Pending','Under Review','Approval Pending','Approved','Escalated']],'case_status':[{'name':st,'value':sum(c.status==st for c in cases)} for st in ['New','Investigating','Awaiting Evidence','Pending Approval','Closed']],'activity':[serialize(x) for x in s.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(10))],'agents':[{'name':n,'processed':sum(x['agent']==n for x in executions),'duration_ms':round(sum(x.get('duration_ms',0) for x in executions if x['agent']==n),2),'status':'Waiting for Human' if n=='Human Approval Router' and workflows else 'Ready','provider':'Deterministic demo','tokens':0} for n in AGENTS]}

@app.get('/api/v1/records/{resource}')
def records(resource:str,q:str='',status:str='',page:int=Query(1,ge=1),size:int=Query(20,ge=1,le=100),days:int=Query(365,ge=1,le=3650),user=Depends(current_user)):
    if resource not in TABLES:raise HTTPException(404,'Unknown resource')
    model=TABLES[resource]
    with Session() as s:
        query=select(model).where(model.created_at>=now()-timedelta(days=days))
        if q:
            fields=[getattr(model,k) for k in ['name','email','title','category','action','destination','id','customer_id','actor'] if hasattr(model,k)]
            query=query.where(or_(*[f.ilike('%'+q+'%') for f in fields]))
        if status and hasattr(model,'status'):query=query.where(model.status==status)
        total=s.scalar(select(func.count()).select_from(query.subquery()))
        rows=s.scalars(query.order_by(model.created_at.desc()).offset((page-1)*size).limit(size)).all()
        names={c.id:c.name for c in s.scalars(select(Customer))}
        return {'items':[{**serialize(x),**({'customer_name':names.get(x.customer_id,'Unknown')} if hasattr(x,'customer_id') else {})} for x in rows],'total':total,'page':page,'size':size}

@app.get('/api/v1/records/{resource}/{id}')
def record(resource:str,id:str,user=Depends(current_user)):
    if resource not in TABLES:raise HTTPException(404,'Unknown resource')
    with Session() as s:
        obj=required(s,TABLES[resource],id);result=serialize(obj)
        cid=obj.id if isinstance(obj,Customer) else getattr(obj,'customer_id',None)
        if cid:
            c=required(s,Customer,cid);result['customer']=serialize(c)
            for key,model in [('documents',Document),('workflows',Workflow),('alerts',Alert),('transactions',Transaction),('cases',Case),('approvals',Approval)]:
                result['related_'+key]=[serialize(x) for x in s.scalars(select(model).where(model.customer_id==cid).order_by(model.created_at.desc()).limit(30))]
        return result

@app.post('/api/v1/documents/{customer_id}',status_code=201)
async def upload(customer_id:str,file:UploadFile=File(...),kind:str=Query('Identity',pattern='^(Identity|Selfie|Address proof|Evidence)$'),user=Depends(current_user)):
    authorize(user,WRITE_ROLES)
    content=await file.read(5*1024*1024+1)
    if len(content)>5*1024*1024:raise HTTPException(413,'Maximum upload size is 5 MB')
    if not content:raise HTTPException(422,'Empty files are not accepted')
    mime='image/png' if content.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if content.startswith(b'\xff\xd8\xff') else 'application/pdf' if content.startswith(b'%PDF-') else None
    if not mime:raise HTTPException(415,'Upload a valid PDF, PNG, or JPEG document')
    digest=hashlib.sha256(content).hexdigest()
    with Session() as s:
        required(s,Customer,customer_id)
        duplicate=s.scalar(select(Document).where(Document.digest==digest))
        d=Document(customer_id=customer_id,name=os.path.basename(file.filename or 'evidence')[:200],kind=kind,digest=digest,content=base64.b64encode(content).decode(),mime=mime,findings={'duplicate':bool(duplicate),'size':len(content),'authenticity':'Unverified','ocr':'Not configured. Manual evidence review required.'});s.add(d);s.flush();audit(s,user,'Document uploaded',d.id,{'kind':kind,'duplicate':bool(duplicate)});s.commit();return serialize(d)
@app.get('/api/v1/documents/{id}/content')
def document_content(id:str,user=Depends(current_user)):
    with Session() as s:
        d=required(s,Document,id);audit(s,user,'Evidence viewed',id);s.commit()
        return Response(base64.b64decode(d.content),media_type=d.mime,headers={'Content-Disposition':'inline; filename="evidence"','Content-Security-Policy':"sandbox"})

class RunInput(BaseModel):
    customer_id:str
    scenario:int=Field(default=0,ge=0,le=9)
@app.post('/api/v1/workflows/run')
def run(data:RunInput,user=Depends(current_user)):
    authorize(user,WRITE_ROLES)
    with Session() as s:
        c=required(s,Customer,data.customer_id)
        if c.status=='Draft':raise HTTPException(409,'Submit the draft before running checks')
        if s.scalar(select(Approval).where(Approval.customer_id==c.id,Approval.status=='Pending')):raise HTTPException(409,'An approval is already pending. Complete it before rerunning.')
        audit(s,user,'Workflow requested',c.id);s.commit();return serialize(run_workflow(s,c,data.scenario))
class ScenarioInput(BaseModel): scenario:int=Field(ge=0,le=9)
@app.get('/api/v1/scenarios')
def scenarios(user=Depends(current_user)):return SCENARIOS
@app.get('/api/v1/models')
def models(user=Depends(current_user)):
    return {'available':bool(MODEL),'version':MODEL.get('version') if MODEL else None,'metrics':MODEL.get('metrics') if MODEL else {},'disclaimer':'Synthetic holdout evaluation only; not real-world banking performance.'}
@app.post('/api/v1/scenarios/launch')
def launch(data:ScenarioInput,user=Depends(current_user)):
    authorize(user,WRITE_ROLES)
    with Session() as s:
        c=Customer(name='Demo Watchlist Person' if data.scenario==3 else 'Scenario '+SCENARIOS[data.scenario],email=f'scenario-{uid()}@synthetic.example',profile={'source_of_funds':'Salary','consent':data.scenario!=9,'synthetic':True,'scenario':data.scenario},creator_id=user.id);s.add(c);s.flush();s.add(Application(customer_id=c.id,data={'scenario':data.scenario}));audit(s,user,'Demo scenario launched',c.id,{'scenario':SCENARIOS[data.scenario]});s.commit()
        wf=run_workflow(s,c,data.scenario);return {'customer':serialize(c),'workflow':serialize(wf)}

class DecisionInput(BaseModel):
    action:str=Field(pattern='^(Approve|Reject|Request Information|Investigate|Escalate|False Positive)$')
    reason:str=Field(min_length=10,max_length=2000)
@app.post('/api/v1/approvals/{id}/decision')
def decide(id:str,data:DecisionInput,user=Depends(current_user)):
    authorize(user,{'Approval Officer','Compliance Officer','Super Administrator'})
    with Session() as s:
        a=s.scalar(select(Approval).where(Approval.id==id).with_for_update())
        if not a:raise HTTPException(404,'Approval not found')
        if a.status!='Pending':raise HTTPException(409,'This approval has already been decided')
        c=required(s,Customer,a.customer_id)
        if c.creator_id==user.id:raise HTTPException(403,'Separation of duties: you cannot decide your own application')
        if any(d['reviewer_id']==user.id for d in a.decisions):raise HTTPException(409,'You have already reviewed this approval')
        if data.action=='Approve' and not c.profile.get('consent'):raise HTTPException(409,'Mandatory consent is missing. Request additional information.')
        if data.action=='Approve' and not s.scalar(select(Document).where(Document.customer_id==c.id)):
            raise HTTPException(409,'Identity evidence is missing. Upload evidence before approval.')
        decisions=a.decisions+[{'reviewer_id':user.id,'reviewer':user.name,'action':data.action,'reason':data.reason,'at':now().isoformat()}];a.decisions=decisions
        if data.action=='Approve':
            if sum(d['action']=='Approve' for d in decisions)>=a.required:a.status='Approved';c.status='Approved'
        else:
            a.status={'Reject':'Rejected','Request Information':'Information Requested','Investigate':'Investigating','Escalate':'Escalated','False Positive':'False Positive'}[data.action];c.status='Rejected' if data.action=='Reject' else 'Under Review'
        if a.workflow_id:
            wf=required(s,Workflow,a.workflow_id);wf.status='Waiting for Human' if a.status=='Pending' else a.status;wf.state={**wf.state,'human_decisions':decisions,'status':wf.status}
        audit(s,user,'Human decision: '+data.action,a.id,{'reason':data.reason,'status':a.status});s.commit();return serialize(a)

class CaseInput(BaseModel):
    customer_id:str
    title:str=Field(min_length=5,max_length=200)
    type:str=Field(default='AML',pattern='^(AML|Fraud|KYC|Compliance|Customer Verification)$')
    priority:str=Field(default='Medium',pattern='^(Low|Medium|High|Critical)$')
@app.post('/api/v1/cases',status_code=201)
def create_case(data:CaseInput,user=Depends(current_user)):
    authorize(user,WRITE_ROLES)
    with Session() as s:
        required(s,Customer,data.customer_id);c=Case(**data.model_dump(),assignee=user.name,notes=[]);s.add(c);s.flush();audit(s,user,'Case created',c.id);s.commit();return serialize(c)
class CasePatch(BaseModel):
    status:str|None=Field(default=None,pattern='^(New|Assigned|Investigating|Awaiting Evidence|Pending Approval|Escalated|Closed|False Positive)$')
    assignee:str|None=Field(default=None,max_length=150)
    note:str|None=Field(default=None,min_length=3,max_length=3000)
@app.patch('/api/v1/cases/{id}')
def case_patch(id:str,data:CasePatch,user=Depends(current_user)):
    authorize(user,WRITE_ROLES)
    with Session() as s:
        c=required(s,Case,id)
        if data.status:c.status=data.status
        if data.assignee:c.assignee=data.assignee
        if data.note:c.notes=c.notes+[{'author':user.name,'text':data.note,'at':now().isoformat()}]
        audit(s,user,'Case updated',id,data.model_dump(exclude_none=True));s.commit();return serialize(c)
class AlertPatch(BaseModel):status:str=Field(pattern='^(New|Investigating|Resolved|False Positive)$')
@app.patch('/api/v1/alerts/{id}')
def alert_patch(id:str,data:AlertPatch,user=Depends(current_user)):
    authorize(user,{'Super Administrator','Fraud Analyst','AML Investigator','Compliance Officer'})
    with Session() as s:
        a=required(s,Alert,id);a.status=data.status;audit(s,user,'Alert status updated',id,{'status':data.status});s.commit();return serialize(a)
class RuleInput(BaseModel):
    name:str=Field(min_length=5,max_length=150)
    jurisdiction:str=Field(default='India • synthetic policy',max_length=100)
    condition:str=Field(pattern='^(documents|consent|risk|amount|source_of_funds|human_review)$')
    threshold:float=Field(default=65,ge=0,le=1e12)
    enabled:int=Field(default=1,ge=0,le=1)
@app.post('/api/v1/rules',status_code=201)
def rule_create(data:RuleInput,user=Depends(current_user)):
    authorize(user,{'Super Administrator','Compliance Officer'})
    with Session() as s:
        r=Rule(**data.model_dump());s.add(r);s.flush();audit(s,user,'Policy rule created',r.id);s.commit();return serialize(r)
@app.patch('/api/v1/rules/{id}')
def rule_update(id:str,data:RuleInput,user=Depends(current_user)):
    authorize(user,{'Super Administrator','Compliance Officer'})
    with Session() as s:
        r=required(s,Rule,id)
        for k,v in data.model_dump().items():setattr(r,k,v)
        audit(s,user,'Policy rule updated',id);s.commit();return serialize(r)
class Policy(BaseModel):
    transaction_threshold:float=Field(gt=0,le=1e12)
    risk_threshold:float=Field(ge=1,le=99)
    dual_approval_threshold:float=Field(ge=1,le=99)
    retention_days:int=Field(ge=30,le=3650)
    jurisdiction:str=Field(max_length=100)
    version:str=Field(max_length=30)
@app.get('/api/v1/settings')
def settings(user=Depends(current_user)):
    with Session() as s:return s.get(Setting,'policy').value
@app.put('/api/v1/settings')
def put_settings(data:Policy,user=Depends(current_user)):
    authorize(user,{'Super Administrator','Compliance Officer'})
    with Session() as s:
        setting=s.get(Setting,'policy');setting.value=data.model_dump();audit(s,user,'Policy configuration updated','policy',data.model_dump());s.commit();return setting.value
@app.get('/api/v1/export/{resource}')
def export(resource:str,user=Depends(current_user)):
    if resource not in TABLES or resource=='users':raise HTTPException(404,'Report not available')
    with Session() as s:
        rows=[serialize(x) for x in s.scalars(select(TABLES[resource]).limit(10000))];buf=io.StringIO()
        if rows:
            writer=csv.DictWriter(buf,fieldnames=list(rows[0]));writer.writeheader()
            for row in rows:
                # Neutralize spreadsheet formulas from untrusted customer values.
                writer.writerow({k:(' '+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else json.dumps(v) if isinstance(v,(dict,list)) else v) for k,v in row.items()})
        audit(s,user,'CSV export',resource,{'rows':len(rows)});s.commit()
        return Response(buf.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="nexora-{resource}.csv"'})
@app.get('/api/v1/events')
def events(user=Depends(current_user)):
    def generate():
        with Session() as s:
            rows=[serialize(x) for x in s.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(5))]
        yield 'event: activity\ndata: '+json.dumps(rows)+'\n\n'
        yield 'event: heartbeat\ndata: {"status":"connected","reconnect_ms":15000}\nretry: 15000\n\n'
    return StreamingResponse(generate(),media_type='text/event-stream')

# Docker/local single-origin serving; Vercel serves the compiled assets directly.
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
if os.path.isdir('dist'):
    app.mount('/assets',StaticFiles(directory='dist/assets'),name='assets')
    @app.get('/{path:path}',include_in_schema=False)
    def frontend(path:str):
        if path.startswith('api/'):raise HTTPException(404,'Endpoint not found')
        return FileResponse('dist/index.html')
