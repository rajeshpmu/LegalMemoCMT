"""Pretty-print Clancy courtroom-affect candidate rows by affect."""
from __future__ import annotations
import argparse, csv, json
from collections import Counter
from pathlib import Path
from textwrap import shorten

def clean(v): return str(v or '').strip() or '[blank]'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-csv',required=True)
    p.add_argument('--output-csv',required=True)
    p.add_argument('--summary-json',required=True)
    p.add_argument('--affect',action='append',default=[],help='Affect value, repeat or comma-separate; ALL means every row')
    p.add_argument('--min-confidence',type=float,default=None)
    p.add_argument('--limit',type=int,default=0)
    p.add_argument('--print-rows',type=int,default=10)
    a=p.parse_args()
    with Path(a.input_csv).open(newline='',encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
    affects={x.strip().upper() for v in a.affect for x in v.split(',') if x.strip()}
    selected=[]
    for r in rows:
        affect=clean(r.get('proposed_courtroom_affect')).upper()
        try: conf=float(r.get('proposed_courtroom_affect_confidence',''))
        except ValueError: conf=-1
        if affects and 'ALL' not in affects and affect not in affects: continue
        if a.min_confidence is not None and conf<a.min_confidence: continue
        selected.append(r)
    if a.limit>0: selected=selected[:a.limit]
    out=Path(a.output_csv); out.parent.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0]) if rows else []
    with out.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(selected)
    summary={'input_csv':a.input_csv,'output_csv':a.output_csv,'requested_affects':sorted(affects),'input_rows':len(rows),'selected_rows':len(selected),'affect_counts':dict(Counter(clean(r.get('proposed_courtroom_affect')) for r in selected)),'confidence_values':{'min':min((float(r['proposed_courtroom_affect_confidence']) for r in selected),default=None),'max':max((float(r['proposed_courtroom_affect_confidence']) for r in selected),default=None)},'notes':['Candidates are weak labels for human review, not final affect annotations.','Do not interpret affect as credibility, truthfulness, deception, or reliability.']}
    report=Path(a.summary_json); report.parent.mkdir(parents=True,exist_ok=True); report.write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))
    fields_to_show=[('utterance_id','Utterance ID'),('youtube_id','Source'),('start_time','Start'),('end_time','End'),('clip_duration_seconds','Duration (sec)'),('speaker_role','Speaker role'),('witness_speaking_status','Witness speaking'),('phase1_basic_emotion','Phase 1 emotion'),('phase1_basic_emotion_confidence','Phase 1 confidence'),('proposed_basic_emotion','Proposed basic emotion'),('proposed_basic_emotion_confidence','Proposed basic confidence'),('proposed_courtroom_affect','Candidate affect'),('proposed_courtroom_affect_confidence','Candidate affect confidence'),('courtroom_affect_evidence','Evidence'),('courtroom_affect_missing_evidence','Missing evidence'),('courtroom_affect_review_required','Review required'),('utterance_text','Transcript'),('clip_video_path','Video clip'),('clip_audio_path','Audio clip')]
    if a.print_rows>0:
        print(f"\nPretty-printing {min(a.print_rows,len(selected))} row(s):")
        for i,r in enumerate(selected[:a.print_rows],1):
            print(f'\n--- Row {i} ---')
            for key,label in fields_to_show:
                val=clean(r.get(key))
                if key=='utterance_text': val=shorten(' '.join(val.split()),width=500,placeholder=' ...')
                print(f'{label}: {val}')

if __name__=='__main__': main()
