"""Train synthetic baseline models and export portable trees for serverless inference."""
import json, random, math
from pathlib import Path
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score

def tree_export(tree):
    t=tree.tree_
    return {'left':t.children_left.tolist(),'right':t.children_right.tolist(),'feature':t.feature.tolist(),'threshold':t.threshold.tolist(),'n':t.n_node_samples.tolist(),'value':t.value.tolist()}

def main():
    rng=np.random.default_rng(42)
    x=np.column_stack([rng.lognormal(9,1.4,3000),rng.integers(1,25,3000),rng.random(3000),rng.random(3000)])
    y=((x[:,0]>200000)|(x[:,1]>17)|((x[:,2]>.8)&(x[:,3]>.7))).astype(int)
    train,test,yt,yv=train_test_split(x,y,test_size=.25,random_state=42,stratify=y)
    risk=RandomForestClassifier(n_estimators=24,max_depth=6,random_state=42,class_weight='balanced').fit(train,yt)
    iso=IsolationForest(n_estimators=32,max_samples=128,contamination=.12,random_state=42).fit(train)
    pred=risk.predict(test);prob=risk.predict_proba(test)[:,1]
    model={'version':'synthetic-1.0','features':['amount','hourly_frequency','device_inconsistency','profile_inconsistency'],'risk_trees':[tree_export(t) for t in risk.estimators_],'isolation_trees':[tree_export(t) for t in iso.estimators_],'sample_size':128,'offset':float(iso.offset_),'feature_importance':risk.feature_importances_.tolist(),'metrics':{'classification':classification_report(yv,pred,output_dict=True),'confusion_matrix':confusion_matrix(yv,pred).tolist(),'roc_auc':float(roc_auc_score(yv,prob))},'disclaimer':'Synthetic holdout performance only. Not real-world banking accuracy.'}
    out=Path(__file__).resolve().parents[1]/'backend'/'baseline_models.json';out.write_text(json.dumps(model,separators=(',',':')))
    print(json.dumps({'artifact':str(out),'roc_auc_synthetic':model['metrics']['roc_auc'],'features':model['features']}))
if __name__=='__main__':main()
