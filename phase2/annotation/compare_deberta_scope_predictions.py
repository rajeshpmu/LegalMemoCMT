"""Compare original scope fields with DeBERTa suggestions without overwriting either."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd

def clean(v):
    s=str(v or '').strip()
    return '' if s.lower() in {'nan','none'} else s

def margin(value):
    try:
        d=json.loads(value) if isinstance(value,str) else value
        vals=sorted((float(x) for x in d.values()), reverse=True)
        return round(vals[0]-vals[1],6) if len(vals)>1 else 0.0
    except Exception: return 0.0

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original-csv',required=True); p.add_argument('--deberta-csv',required=True)
    p.add_argument('--output-csv',required=True); p.add_argument('--disagreements-csv',required=True)
    p.add_argument('--summary-json',required=True); p.add_argument('--low-confidence',type=float,default=.60)
    p.add_argument('--low-margin',type=float,default=.10)
    a=p.parse_args()
    original=pd.read_csv(a.original_csv,dtype=str).fillna('')
    deberta=pd.read_csv(a.deberta_csv,dtype=str).fillna('')
    if 'utterance_id' not in original or 'utterance_id' not in deberta: raise SystemExit('Both files need utterance_id')
    evidence=[c for c in deberta.columns if c.startswith('deberta_')]
    right=deberta[['utterance_id']+evidence].drop_duplicates('utterance_id')
    out=original.merge(right,on='utterance_id',how='left',validate='one_to_one')
    out['target_scope_agreement']=out.apply(lambda r:'YES' if clean(r.get('emotion_target_scope')) and clean(r.get('emotion_target_scope'))==clean(r.get('deberta_target_scope')) else ('NO' if clean(r.get('deberta_target_scope')) else 'UNKNOWN'),axis=1)
    out['target_scope_disagreement']=out['target_scope_agreement'].map({'YES':'NO','NO':'YES'}).fillna('NO')
    out['deberta_target_margin']=out.get('deberta_target_scope_scores','').map(margin)
    out['deberta_temporal_margin']=out.get('deberta_temporal_scope_scores','').map(margin)
    out['deberta_target_low_confidence']=pd.to_numeric(out.get('deberta_target_scope_confidence',''),errors='coerce').lt(a.low_confidence).map({True:'YES',False:'NO'}).fillna('UNKNOWN')
    out['deberta_temporal_low_confidence']=pd.to_numeric(out.get('deberta_temporal_scope_confidence',''),errors='coerce').lt(a.low_confidence).map({True:'YES',False:'NO'}).fillna('UNKNOWN')
    out['deberta_review_reason']=out.apply(lambda r:'; '.join(x for x in [
        'target_scope_disagreement' if r['target_scope_disagreement']=='YES' else '',
        'target_low_confidence' if r['deberta_target_low_confidence']=='YES' else '',
        'temporal_low_confidence' if r['deberta_temporal_scope'] != 'NOT_APPLICABLE' and r['deberta_temporal_low_confidence']=='YES' else '',
        'target_low_margin' if float(r['deberta_target_margin'])<a.low_margin else '',
        'temporal_low_margin' if r['deberta_temporal_scope'] != 'NOT_APPLICABLE' and float(r['deberta_temporal_margin'])<a.low_margin else ''] if x) or 'NO_PRIORITY_TRIGGER',axis=1)
    out['deberta_review_required']=out['deberta_review_reason'].ne('NO_PRIORITY_TRIGGER').map({True:'YES',False:'NO'})
    disagreements=out[out['deberta_review_required']=='YES'].copy()
    Path(a.output_csv).parent.mkdir(parents=True,exist_ok=True); out.to_csv(a.output_csv,index=False)
    Path(a.disagreements_csv).parent.mkdir(parents=True,exist_ok=True); disagreements.to_csv(a.disagreements_csv,index=False)
    summary={'original_csv':a.original_csv,'deberta_csv':a.deberta_csv,'output_csv':a.output_csv,'disagreements_csv':a.disagreements_csv,'rows_compared':len(out),'rows_with_deberta':int(out['deberta_target_scope'].ne('').sum()),'target_agreement_counts':out['target_scope_agreement'].value_counts().to_dict(),'review_priority_counts':out['deberta_review_required'].value_counts().to_dict(),'target_margin_mean':round(float(out['deberta_target_margin'].mean()),6),'temporal_margin_mean':round(float(out['deberta_temporal_margin'].mean()),6),'thresholds':{'low_confidence':a.low_confidence,'low_margin':a.low_margin},'notes':['Original scope and annotation fields are preserved.','DeBERTa fields are additional machine evidence only.','Review priority is a screening rule, not a gold-label decision.']}
    Path(a.summary_json).parent.mkdir(parents=True,exist_ok=True); Path(a.summary_json).write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    print(json.dumps(summary,indent=2,sort_keys=True))
if __name__=='__main__': main()
