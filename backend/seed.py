"""Reproducible synthetic data, never copied from real customers."""
import os, random
import uuid
from datetime import timedelta
from sqlalchemy import select, func
from backend.db import *
from backend.security import ph, ROLES

AGENTS=['Orchestrator','Customer Profiling','Document Intelligence','KYC Verification','AML Screening','Fraud Detection','Transaction Monitoring','Customer Risk Assessment','Regulatory Compliance','Investigation','Explainability','Human Approval Router']
SCENARIOS=['Normal onboarding','Incomplete identity documents','Potential synthetic identity','Potential watchlist match','Suspicious transaction velocity','Account takeover indicators','Unusual transaction pattern','Conflicting customer information','Low-confidence assessment','Compliance exception']
def stable(kind,index):return str(uuid.uuid5(uuid.NAMESPACE_DNS,f'nexora.synthetic.{kind}.{index}'))
def seed():
    Base.metadata.create_all(engine)
    with Session() as s:
        if s.scalar(select(func.count()).select_from(Customer)): return
        rng=random.Random(42)
        users=[]
        for i,role in enumerate(ROLES):
            u=User(email=('admin' if i==0 else f'reviewer{i}')+'@nexora.demo',name=['Alex Morgan','Priya Sharma','Arjun Mehta','Maya Patel','James Wilson','Sofia Chen','Rohan Das','Sarah Mitchell','Ava Brooks','Noah Kim'][i],password_hash=ph.hash(os.getenv('DEMO_PASSWORD','NexoraDemo!2026')),role=role)
            u.id=stable('user',i);s.add(u); users.append(u)
        s.flush()
        customers=[]
        first=['Aarav','Priya','Ishaan','Ananya','Vihaan','Meera','Arjun','Diya','Rohan','Kavya','Aditya','Sana','Kabir','Nisha','Dev','Sara','Reyansh','Aisha','Neel','Tara']
        last=['Sharma','Patel','Reddy','Mehta','Singh','Gupta','Iyer','Rao','Das','Nair','Kapoor','Shah','Khan','Verma','Bose','Joshi','Malhotra','Kulkarni','Chopra','Menon','Bhat','Sethi','Roy','Jain','Kumar']
        for i in range(500):
            risk=rng.randint(3,97); status=rng.choices(['Approved','KYC Pending','Under Review','Approval Pending','Escalated'],[55,15,12,12,6])[0]
            c=Customer(name=f'{first[i%20]} {last[i//20]}',email=f'customer{i+1}@synthetic.example',risk=risk,status=status,country=rng.choices(['India','United Kingdom','Singapore','United States'],[85,5,5,5])[0],created_at=now()-timedelta(days=rng.randint(0,29),hours=rng.randint(0,23)),profile={'account_type':rng.choice(['Savings','Current','Business']),'occupation':rng.choice(['Engineer','Consultant','Entrepreneur','Teacher']),'income':rng.randint(3,80)*100000,'id_masked':f'**** **** {1000+i}','source_of_funds':'Salary','consent':True,'synthetic':True},creator_id=users[1].id)
            c.id=stable('customer',i);s.add(c);customers.append(c)
        s.flush()
        for i,c in enumerate(customers[:300]): s.add(Application(customer_id=c.id,status=c.status,data={'synthetic':True},created_at=c.created_at))
        for i in range(1000):
            c=rng.choice(customers);amount=round(rng.lognormvariate(9,1.5),2);risk=min(99,round(amount/6000+rng.randint(0,40),1))
            s.add(Transaction(customer_id=c.id,amount=amount,currency='INR',destination=rng.choice(['Mumbai • HDFC','Bengaluru • ICICI','Delhi • SBI','Singapore • DBS','London • HSBC']),type=rng.choice(['NEFT','RTGS','UPI','Wire']),risk=risk,status='Flagged' if risk>=65 else 'Cleared',created_at=now()-timedelta(days=rng.randint(0,29),minutes=i)))
        for i in range(100):
            c=customers[i*3];s.add(Alert(customer_id=c.id,category=['Identity Fraud','Transaction Anomaly','Application Abuse','Account Takeover','Synthetic Watchlist Match'][i%5],severity=['High','Medium','Critical'][i%3],status=['New','Investigating','Resolved'][i%3],evidence={'source':'Synthetic scenario generator','rule':'DEMO-FRAUD-01','reason':'Unusual profile or transaction pattern requires analyst review'},created_at=c.created_at))
        for i in range(50):
            c=customers[i*5];s.add(Case(customer_id=c.id,title=f'{["Enhanced due diligence","Transaction pattern review","Identity inconsistency","Watchlist investigation"][i%4]} · {c.name}',type=['AML','Fraud','KYC','Compliance'][i%4],priority=['High','Medium','Critical'][i%3],status=['New','Investigating','Awaiting Evidence','Pending Approval','Closed'][i%5],assignee=users[4 if i%2 else 3].name,notes=[]))
        for i in range(30): s.add(Rule(name=['Mandatory identity evidence','Consent verification','Elevated risk review','Large transaction review','Source of funds evidence','Independent human approval'][i%6]+f' · {i+1:02}',condition=['documents','consent','risk','amount','source_of_funds','human_review'][i%6],threshold=[1,1,65,200000,1,1][i%6]))
        for c in customers[300:325]: s.add(Approval(customer_id=c.id,required=2 if c.risk>=75 else 1,decisions=[]))
        for i in range(100): s.add(Audit(actor='Synthetic seed service',action=['Application received','KYC evidence recorded','Review routed','Alert generated','Case updated'][i%5],target=customers[i].id,detail={'synthetic':True},created_at=now()-timedelta(minutes=100-i)))
        s.add(Setting(id='policy',value={'transaction_threshold':200000,'risk_threshold':65,'dual_approval_threshold':75,'retention_days':365,'jurisdiction':'India','version':'demo-1.0'}))
        s.commit()
