"""Repair ordering of the newly inserted canonical speaking section only."""
from pathlib import Path
from docx import Document

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'implementation_docments/LegalMemoCMT_Phase2_Second_Review_Call_Speaking_Doc.docx'

def main():
    doc=Document(PATH)
    paras=doc.paragraphs
    marker=next(p for p in paras if p.text.strip()=='CANONICAL_30_SLIDE_SPEAKING_ORDER_V1')
    anchor=next(p for p in paras if p.text.strip()=='Slide-by-slide speaking guidance')
    header=next(p for p in paras if p.text.strip()=='Canonical Current Deck Order: Slides 1-30')
    section=list(paras[paras.index(header):paras.index(anchor)])
    # Include the orphaned first inserted note immediately before the header.
    section.insert(0, paras[paras.index(header)-1])
    header=next(p for p in section if p.text.strip()=='Canonical Current Deck Order: Slides 1-30')
    intro=next(p for p in section if p.text.strip().startswith('Use this section as the primary reading sequence'))
    ordered=[header,marker,intro]
    for n in range(1,31):
        h=next(p for p in section if p.text.strip().startswith(f'Slide {n}: '))
        hi=paras.index(h)
        note=paras[hi+1]
        ordered.extend([h,note])
    body=doc._body._body
    for p in set(section+[header,marker,intro]):
        if p._p.getparent() is body:
            body.remove(p._p)
    # Insert directly at the anchor index so XML sibling ordering is deterministic.
    anchor_index = list(body).index(anchor._p)
    for offset, p in enumerate(ordered):
        body.insert(anchor_index + offset, p._p)
    doc.save(PATH)
    print('Repaired canonical slide order in',PATH)

if __name__=='__main__': main()
