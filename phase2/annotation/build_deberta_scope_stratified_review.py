"""Create a deterministic stratified manual-review sample from comparison output."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--input-csv',required=True); p.add_argument('--output-csv',required=True); p.add_argument('--summary-json',required=True); p.add_argument('--per-stratum',type=int,default=5); p.add_argument('--seed',type=int,default=42); a=p.parse_args()
    df=pd.read_csv(a.input_csv,dtype=str).fillna('')
    for c in ['target_scope_disagreement','deberta_target_scope','deberta_temporal_scope']: 
        if c not in df: df[c]='UNKNOWN'
    df['review_stratum']=df['target_scope_disagreement'].replace('', 'UNKNOWN')+'|target='+df['deberta_target_scope'].replace('', 'UNKNOWN')+'|temporal='+df['deberta_temporal_scope'].replace('', 'UNKNOWN')
    pieces=[]
    for _,g in df.groupby('review_stratum',sort=True): pieces.append(g.sample(n=min(a.per_stratum,len(g)),random_state=a.seed))
    out=pd.concat(pieces,ignore_index=True) if pieces else df.head(0)
    out=out.sort_values(['review_stratum','utterance_id'])
    Path(a.output_csv).parent.mkdir(parents=True,exist_ok=True); out.to_csv(a.output_csv,index=False)
    summary={'input_csv':a.input_csv,'output_csv':a.output_csv,'rows_input':len(df),'rows_selected':len(out),'per_stratum':a.per_stratum,'seed':a.seed,'strata_selected':out['review_stratum'].value_counts().to_dict(),'notes':['Deterministic review sample; not a training set.','Original and DeBERTa fields are retained together.','Reviewers should inspect transcript, audio, video, role, and scope context.']}
    Path(a.summary_json).parent.mkdir(parents=True,exist_ok=True); Path(a.summary_json).write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n'); print(json.dumps(summary,indent=2,sort_keys=True))
if __name__=='__main__': main()
