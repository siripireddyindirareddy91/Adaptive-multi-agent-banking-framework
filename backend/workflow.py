"""Typed LangGraph with durable SQL workflow snapshots and a mandatory human gate.

No document text or model response can alter policy or invoke tools.
"""
import time, os
from typing import TypedDict
from difflib import SequenceMatcher
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy
from langchain_core.runnables import RunnableLambda
from backend.db import *
from backend.seed import AGENTS
from backend.ml import predict
from backend.llm import summarize

class State(TypedDict, total=False):
    customer_id:str
    profile:dict
    findings:list
    executions:list
    risk:float
    confidence:float
    status:str
    document_count:int
    scenario:int
    policy:dict

def finding(agent,rule,reason,severity=0,evidence=None):
    return {'agent':agent,'rule':rule,'reason':reason,'severity':severity,'evidence':evidence or {},'source':'Deterministic synthetic adapter'}

def execute(name,state):
    p=state['profile']; scenario=state.get('scenario',0); out=[]; changes={}
    if name=='Orchestrator': out.append(finding(name,'ROUTE-01','Workflow started with immutable human approval requirement.'))
    elif name=='Customer Profiling':
        missing=[k for k in ['name','email','source_of_funds'] if not p.get(k)]
        out.append(finding(name,'PROFILE-01',f'Missing fields: {", ".join(missing)}' if missing else 'Required profile fields are complete.',20 if missing else 0,{'missing':missing}))
    elif name=='Document Intelligence':
        count=state.get('document_count',0)
        out.append(finding(name,'DOC-01','No identity evidence uploaded; document verification remains unverified.' if not count else f'{count} evidence files registered. Image authenticity and biometric matching are not live integrations.',25 if not count else 0,{'document_count':count,'authenticity':'not verified'}))
    elif name=='KYC Verification':
        expired=bool(p.get('document_expiry') and p['document_expiry']<now().date().isoformat())
        mismatch=scenario in [2,7]
        out.append(finding(name,'KYC-01','Expired identity document.' if expired else 'Synthetic field inconsistency requires review.' if mismatch else 'Identity document evidence requires an authorized reviewer; no government lookup performed.',35 if expired or mismatch else 0))
    elif name=='AML Screening':
        watchlist=['Demo Watchlist Person','Synthetic Sanctions Subject','Test PEP Example']
        matches=[{'name':n,'similarity':round(SequenceMatcher(None,p.get('name','').lower(),n.lower()).ratio(),3)} for n in watchlist]
        best=max(matches,key=lambda x:x['similarity']);matched=best['similarity']>=.78 or scenario==3
        out.append(finding(name,'AML-DEMO-01','Potential synthetic watchlist match. Human verification required.' if matched else 'No close name match in the synthetic watchlist. This is not a live sanctions clearance.',45 if matched else 0,{'match':best,'watchlist_version':'synthetic-1.0','potential_match':matched}))
    elif name=='Fraud Detection':
        suspicious=scenario in [2,5,7]
        model=predict(10000,2,.95 if suspicious else .1,.9 if suspicious else .1)
        out.append(finding(name,'FRAUD-DEMO-01','Synthetic behavioral inconsistency detected.' if suspicious else 'No configured synthetic application-abuse indicators triggered.',30 if suspicious else 0,{'device_intelligence':'simulated','scenario':scenario,'ml':model}))
    elif name=='Transaction Monitoring':
        with Session() as s:
            rows=s.query(Transaction).filter_by(customer_id=state['customer_id']).all()
        threshold=state.get('policy',{}).get('transaction_threshold',200000)
        recent=[x for x in rows if (now().replace(tzinfo=None)-x.created_at.replace(tzinfo=None)).total_seconds()<3600]
        unusual=any(x.amount>threshold for x in rows) or len(recent)>5 or scenario in [4,6]
        model=predict(max((x.amount for x in rows),default=10000),max(len(recent),1),0,0)
        out.append(finding(name,'TX-01','Threshold or velocity anomaly requires review.' if unusual else 'No configured transaction threshold or velocity rules triggered.',30 if unusual else 0,{'transaction_count':len(rows),'recent_hour_count':len(recent),'threshold':threshold,'ml':model}))
    elif name=='Customer Risk Assessment':
        severity=sum(x['severity'] for x in state['findings']);risk=min(99,severity)
        changes={'risk':risk,'confidence':.48 if scenario==8 else .82 if state.get('document_count') else .58}
        out.append(finding(name,'RISK-01',f'Rule-based severity {risk}/100. This is not a calibrated fraud probability.',risk,{'method':'additive deterministic rules','model_version':'rules-1.0'}))
    elif name=='Regulatory Compliance':
        consent=bool(p.get('consent'));exception=scenario==9
        out.append(finding(name,'CONSENT-01','Consent recorded.' if consent else 'Consent missing. Final approval is blocked.',0 if consent else 50,{'passed':consent,'jurisdiction':'India','rule_pack':'demo-1.0','legal_status':'Illustrative internal policy; not current legal advice'}))
        if exception: out.append(finding(name,'EXCEPTION-01','Synthetic internal-policy exception requires compliance review.',30))
        with Session() as s:
            rules=s.query(Rule).filter_by(enabled=1).all()
        for rule in rules:
            passed={'documents':state.get('document_count',0)>=rule.threshold,'consent':consent,'risk':state.get('risk',0)<rule.threshold,'amount':True,'source_of_funds':bool(p.get('source_of_funds')),'human_review':True}.get(rule.condition,False)
            if rule.condition=='amount':
                with Session() as s:passed=not s.query(Transaction).filter(Transaction.customer_id==state['customer_id'],Transaction.amount>=rule.threshold).first()
            out.append(finding(name,rule.id,'Control passed: '+rule.name if passed else 'Control requires review: '+rule.name,0 if passed else 10,{'passed':passed,'condition':rule.condition,'threshold':rule.threshold,'jurisdiction':rule.jurisdiction,'version':rule.version}))
    elif name=='Investigation':
        out.append(finding(name,'INV-01','Enhanced due diligence recommended. Collect independent evidence before deciding.',0,{'linked_rules':[x['rule'] for x in state['findings'] if x['severity']>0]}))
    elif name=='Explainability':
        reasons=[x['reason'] for x in state['findings'] if x['severity']>0 and x['agent']!='Customer Risk Assessment']
        # Runnable interface allows replacement with structured LLM summaries without granting tools.
        summary=RunnableLambda(summarize).invoke(state['findings'])
        out.append(finding(name,'EXPLAIN-01',summary['output']['summary'],0,{'confidence':state.get('confidence',.5),'uncertainty':summary['output']['uncertainty'],'provider':summary['provider'],'tokens':summary['tokens']}))
    elif name=='Human Approval Router':
        changes['status']='Waiting for Human'
        out.append(finding(name,'HUMAN-01','Final authorization requires independent human review. AI cannot approve or reject.'))
    return {**changes,'findings':state.get('findings',[])+out}

def node(name):
    def run(state):
        start=time.perf_counter(); result=execute(name,state)
        result['executions']=state.get('executions',[])+[{'agent':name,'status':'Waiting for Human' if name=='Human Approval Router' else 'Completed','duration_ms':round((time.perf_counter()-start)*1000,2),'at':now().isoformat(),'provider':'Deterministic demo / LangChain','tokens':0,'output':result['findings'][-1]}]
        return result
    return run

builder=StateGraph(State)
for name in AGENTS: builder.add_node(name,node(name),retry_policy=RetryPolicy(max_attempts=3))
path=['Orchestrator','Customer Profiling','Document Intelligence','KYC Verification','AML Screening','Fraud Detection','Transaction Monitoring','Customer Risk Assessment','Regulatory Compliance']
builder.add_edge(START,path[0])
for a,b in zip(path,path[1:]):builder.add_edge(a,b)
builder.add_conditional_edges('Regulatory Compliance',lambda s:'Investigation' if s.get('risk',0)>=s.get('policy',{}).get('risk_threshold',65) or s.get('confidence',0)<.6 else 'Explainability')
builder.add_edge('Investigation','Explainability');builder.add_edge('Explainability','Human Approval Router');builder.add_edge('Human Approval Router',END)
graph=builder.compile()

def run_workflow(s,customer,scenario=0):
    wf=Workflow(customer_id=customer.id,status='Running',state={},executions=[]);s.add(wf);s.flush()
    policy=s.get(Setting,'policy').value
    state={'customer_id':customer.id,'profile':{**customer.profile,'name':customer.name,'email':customer.email},'findings':[],'executions':[],'risk':0,'confidence':0,'scenario':scenario,'document_count':s.query(Document).filter_by(customer_id=customer.id).count(),'status':'Running','policy':policy}
    try:
        # Save every completed node so a failed execution retains its prior evidence.
        for update in graph.stream(state,stream_mode='updates'):
            for values in update.values(): state={**state,**values}
            wf.state=state.copy();wf.executions=state['executions'];s.commit()
        wf.status='Waiting for Human';customer.risk=state['risk'];customer.status='Approval Pending'
        approval=Approval(customer_id=customer.id,workflow_id=wf.id,required=2 if customer.risk>=policy.get('dual_approval_threshold',75) else 1,decisions=[]);s.add(approval)
        if state['risk']>=policy.get('risk_threshold',65):
            s.add(Case(customer_id=customer.id,title=f'Enhanced review · {customer.name}',type='AML',priority='High',notes=[]))
            s.add(Alert(customer_id=customer.id,category='Workflow risk escalation',severity='High',evidence={'workflow_id':wf.id,'factors':[f for f in state['findings'] if f['severity']>0]}))
        s.add(Audit(actor='LangGraph orchestrator',action='Workflow awaiting human review',target=wf.id,detail={'risk':state['risk'],'approval_required':True}));s.commit()
    except Exception:
        s.rollback(); wf=s.get(Workflow,wf.id);wf.status='Failed';s.commit();raise
    return wf
