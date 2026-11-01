"""Keep OCR line evidence, without asserting a character identity."""
from math import isfinite
from core.dialogue.context_models import OcrEvidence, OcrLine

def evidence_from_ocr(ocr):
    rows=[]
    for span in ocr.spans:
        try:
            if not span.text.strip() or not 0<=span.confidence<=1 or not isfinite(span.confidence) or not span.polygon or not all(isfinite(v) for p in span.polygon for v in p): continue
            rows.append((min(p[1] for p in span.polygon),min(p[0] for p in span.polygon),span.text.strip(),span.confidence))
        except (TypeError,ValueError,AttributeError): continue
    lines=[]; remaining=2000
    for _,__,text,confidence in sorted(rows):
        if len(lines)>=32 or len(text)>remaining: break
        lines.append(OcrLine(text,confidence,not lines and len(text)<=40 and len(rows)>1))
        remaining-=len(text)
    if not lines and ocr.text and len(ocr.text)<=2000: lines=[OcrLine(ocr.text)]
    return OcrEvidence(tuple(lines))
