import os, secrets, hashlib
from datetime import timedelta
import jwt
from argon2 import PasswordHasher
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.db import Session, User, Refresh, now

DEMO = os.getenv('DEMO_MODE','true').lower()=='true'
SECRET = os.getenv('JWT_SECRET')
if not SECRET:
    if not DEMO: raise RuntimeError('JWT_SECRET is required outside demo mode')
    SECRET = 'nexora-public-synthetic-demo-key-not-for-real-data-v1'
ph=PasswordHasher()
bearer=HTTPBearer(auto_error=False)
ROLES=['Super Administrator','Banking Operations Manager','KYC Analyst','Fraud Analyst','AML Investigator','Compliance Officer','Risk Manager','Approval Officer','Auditor','Read-Only Analyst']
WRITE_ROLES=set(ROLES[:8])
def current_user(credentials:HTTPAuthorizationCredentials|None=Depends(bearer)):
    try:
        if not credentials: raise ValueError()
        claims=jwt.decode(credentials.credentials,SECRET,algorithms=['HS256'])
        with Session() as s:
            user=s.get(User,claims['sub'])
            if not user: raise ValueError()
            return user
    except (ValueError, jwt.PyJWTError): raise HTTPException(401,'Your session has expired. Please sign in.')
def authorize(user,roles):
    if user.role not in roles: raise HTTPException(403,'Your role does not permit this action')
def token_pair(s,user):
    raw=secrets.token_urlsafe(48)
    s.add(Refresh(user_id=user.id,digest=hashlib.sha256(raw.encode()).hexdigest(),expires=now()+timedelta(days=1)))
    s.commit()
    return {'access_token':jwt.encode({'sub':user.id,'exp':now()+timedelta(minutes=45),'iat':now()},SECRET,algorithm='HS256'),'refresh_token':raw,'token_type':'bearer','user':{'id':user.id,'name':user.name,'email':user.email,'role':user.role}}
