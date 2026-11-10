"""Inference of exported scikit-learn trees without heavyweight deployment dependencies."""
import json, math
from pathlib import Path
PATH=Path(__file__).with_name('baseline_models.json')
MODEL=json.loads(PATH.read_text()) if PATH.exists() else None
def c(n):return 0 if n<=1 else 1 if n==2 else 2*(math.log(n-1)+.5772156649)-2*(n-1)/n
def leaf(tree,x):
    i=0;depth=0
    while tree['left'][i]!=-1:
        i=tree['left'][i] if x[tree['feature'][i]]<=tree['threshold'][i] else tree['right'][i];depth+=1
    return i,depth
def predict(amount,frequency=1,device=0,profile=0):
    if not MODEL:return {'available':False,'reason':'Run scripts/train_models.py to create model artifacts'}
    x=[amount,frequency,device,profile];prob=[];paths=[]
    for tree in MODEL['risk_trees']:
        i,_=leaf(tree,x);v=tree['value'][i][0];prob.append(v[1]/max(sum(v),1e-12))
    for tree in MODEL['isolation_trees']:
        i,depth=leaf(tree,x);paths.append(depth+c(tree['n'][i]))
    anomaly=2**(-sum(paths)/len(paths)/c(MODEL['sample_size']))
    return {'available':True,'model_version':MODEL['version'],'synthetic_risk_probability':round(sum(prob)/len(prob),4),'anomaly_score':round(anomaly,4),'anomalous':anomaly>-MODEL['offset'],'feature_importance':dict(zip(MODEL['features'],MODEL['feature_importance'])),'uncertainty':'Trained on synthetic data; not calibrated for real customers. Global importance is not a local causal explanation.'}
