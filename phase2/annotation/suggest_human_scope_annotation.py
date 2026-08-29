"""Suggest human scope annotations using transparent text rules.

Suggestions are not gold labels and never overwrite existing scope fields.
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
import pandas as pd

PAST = re.compile(r"\b(that weekend|last weekend|earlier|previously|at the time|was|were|had|did|would|could|used to)\b", re.I)
ARTIFACT = re.compile(r"\b(text|message|email|letter|note|written|writing|words|statement|representation|observed|observation|purpose|meant to|intended to|encourage|discourage)\b", re.I)
# Do not treat apostrophes in contractions or possessives as quotation marks.
QUOTE = re.compile(r"(\"[^\"]+\"|“[^”]+”|\b(she|he|they|the witness)\s+(said|told|stated|reported)\b)", re.I)
OTHER = re.compile(r"\b(she|her|he|him|his|they|them|another person|someone|the children|the kids)\b", re.I)
SELF = re.compile(r"\b(i|me|my|myself|we|our)\b", re.I)

def suggest(text: str, deberta_target: str = '', deberta_confidence: str = '', no_emotion_threshold: float = .60):
    has_artifact=bool(ARTIFACT.search(text)); has_quote=bool(QUOTE.search(text)); has_other=bool(OTHER.search(text)); has_self=bool(SELF.search(text)); has_past=bool(PAST.search(text))
    try: deberta_score=float(deberta_confidence or 0)
    except ValueError: deberta_score=0.0
    if deberta_target == 'NO_EMOTION_CONTENT' and deberta_score >= no_emotion_threshold:
        target='NO_EMOTION_CONTENT'; reason=f'DeBERTa identified no emotion content with confidence {deberta_score:.3f}'; confidence='HIGH' if deberta_score >= .80 else 'MEDIUM'
    elif has_artifact and has_self and not has_quote:
        target='EVENT_DESCRIBED'; reason='first-person explanation of a message/written artifact without a clear exact quotation'; confidence='HIGH'
    elif has_quote:
        target='QUOTED_SPEECH'; reason='explicit quotation or reported speech marker'; confidence='MEDIUM'
    elif has_other:
        target='OTHER_PERSON_DESCRIBED'; reason='other-person reference with no stronger artifact interpretation'; confidence='MEDIUM'
    else:
        target='UNCLEAR'; reason='no decisive target-scope pattern'; confidence='LOW'
    if target == 'NO_EMOTION_CONTENT': temporal='UNCLEAR'
    elif has_past and has_other: temporal='PAST_OTHER'
    elif has_past and has_self: temporal='PAST_SELF'
    elif has_past: temporal='UNCLEAR'
    else: temporal='CURRENT'
    return target, temporal, confidence, reason

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--input-csv',required=True); p.add_argument('--output-csv',required=True); p.add_argument('--summary-json',required=True); p.add_argument('--utterance-id'); p.add_argument('--no-emotion-threshold',type=float,default=.60); a=p.parse_args()
    df=pd.read_csv(a.input_csv,dtype=str).fillna('')
    if a.utterance_id: df=df[df['utterance_id']==a.utterance_id].copy()
    if df.empty: raise SystemExit('No rows selected')
    values=df.apply(lambda r:suggest(str(r.get('utterance_text') or r.get('turn_text') or ''),str(r.get('deberta_target_scope','')),str(r.get('deberta_target_scope_confidence','')),a.no_emotion_threshold),axis=1,result_type='expand')
    values.columns=['auto_review_target_scope','auto_review_temporal_scope','auto_review_confidence','auto_review_reason']
    for c in values: df[c]=values[c].values
    df['auto_review_status']='AUTO_SUGGESTED'
    df['human_review_required']='YES'
    df['auto_review_basis']='deberta_no_emotion_precedence_plus_transparent_text_rules_v2'
    Path(a.output_csv).parent.mkdir(parents=True,exist_ok=True); df.to_csv(a.output_csv,index=False)
    summary={'input_csv':a.input_csv,'output_csv':a.output_csv,'rows_processed':len(df),'auto_target_counts':df['auto_review_target_scope'].value_counts().to_dict(),'auto_temporal_counts':df['auto_review_temporal_scope'].value_counts().to_dict(),'no_emotion_threshold':a.no_emotion_threshold,'notes':['Suggestions are machine-assisted review candidates, not gold annotations.','Existing emotion_target_scope and DeBERTa fields are preserved.','A sufficiently confident DeBERTa NO_EMOTION_CONTENT suggestion takes precedence over the rule fallback.','human_review_required remains YES for every suggested row.']}
    Path(a.summary_json).parent.mkdir(parents=True,exist_ok=True); Path(a.summary_json).write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n'); print(json.dumps(summary,indent=2,sort_keys=True))
    for _,r in df.head(10).iterrows(): print(f"{r['utterance_id']}: {r['auto_review_target_scope']} / {r['auto_review_temporal_scope']} ({r['auto_review_confidence']}) - {r['auto_review_reason']}")
if __name__=='__main__': main()
