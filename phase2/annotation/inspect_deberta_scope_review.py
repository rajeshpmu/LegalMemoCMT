"""Pretty-print DeBERTa scope disagreements and uncertainty for manual review."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path
from textwrap import shorten

def val(row,key): return str(row.get(key,'')).strip() or '[blank]'
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--input-csv',required=True); p.add_argument('--mode',choices=['disagreement','low-confidence','all'],default='disagreement'); p.add_argument('--limit',type=int,default=20); p.add_argument('--min-confidence',type=float,default=.60); p.add_argument('--max-margin',type=float,default=.10); p.add_argument('--output-csv'); a=p.parse_args()
    with Path(a.input_csv).open(newline='',encoding='utf-8-sig') as h: rows=list(csv.DictReader(h))
    def selected(r):
        disagree=val(r,'target_scope_disagreement')=='YES'
        conf=any(float(r.get(k) or 1) < a.min_confidence for k in ['deberta_target_scope_confidence','deberta_temporal_scope_confidence'])
        margin=any(float(r.get(k) or 1) < a.max_margin for k in ['deberta_target_margin','deberta_temporal_margin'])
        return {'disagreement':disagree,'low-confidence':conf,'all':disagree or conf or margin}[a.mode]
    rows=[r for r in rows if selected(r)]
    if a.output_csv:
        Path(a.output_csv).parent.mkdir(parents=True,exist_ok=True)
        with Path(a.output_csv).open('w',newline='',encoding='utf-8') as h:
            w=csv.DictWriter(h,fieldnames=list(rows[0]) if rows else []); w.writeheader(); w.writerows(rows)
    print(f'rows selected={len(rows)} mode={a.mode} showing={min(a.limit,len(rows))}')
    fields=[('utterance_id','Utterance ID'),('youtube_id','Source'),('start_time','Start'),('end_time','End'),('speaker_role','Role'),('utterance_text','Transcript'),('emotion_target_scope','Original target scope'),('deberta_target_scope','DeBERTa target scope'),('deberta_target_scope_confidence','Target confidence'),('deberta_target_margin','Target margin'),('deberta_temporal_scope','DeBERTa temporal scope'),('deberta_temporal_scope_confidence','Temporal confidence'),('deberta_temporal_margin','Temporal margin'),('target_scope_disagreement','Disagreement'),('deberta_review_reason','Review reason')]
    for i,r in enumerate(rows[:a.limit],1):
        print(f'\n--- Row {i} ---')
        for k,label in fields:
            text=val(r,k)
            if k=='utterance_text': text=shorten(' '.join(text.split()),width=700,placeholder=' ...')
            print(f'{label}: {text}')
if __name__=='__main__': main()
