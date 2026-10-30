"""Selectable-text exports from approved claims, with extraction verification."""
import io
import re
import threading
from pathlib import Path
from xml.sax.saxutils import escape
from pypdf import PdfReader
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

_FONT_LOCK = threading.Lock()
_FONT_NAME = 'CareerDejaVu'

def _font():
    with _FONT_LOCK:
        if _FONT_NAME not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(_FONT_NAME, str(Path(__file__).parent / 'assets' / 'DejaVuSans.ttf')))
    return pdfmetrics.getFont(_FONT_NAME)

def normalized_text(text):
    return re.sub(r'\s+', ' ', text).strip()

def render_pdf(claims):
    font = _font()
    texts = [c['text'] for c in claims]
    # Fail closed rather than silently substituting glyphs or rasterizing text.
    if any(ord(ch) not in font.face.charToGlyph for text in texts for ch in text if not ch.isspace()):
        raise ValueError('PDF font does not support one or more approved characters; use DOCX')
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=54, rightMargin=54,
        topMargin=54, bottomMargin=54, title='Résumé', author='', invariant=True)
    style = ParagraphStyle('Claim', fontName=_FONT_NAME, fontSize=10.5, leading=15,
        alignment=TA_LEFT, splitLongWords=True, allowWidows=0, allowOrphans=0)
    story = []
    for text in texts:
        story += [Paragraph(escape(text).replace('\n', '<br/>'), style), Spacer(1, 10)]
    doc.build(story)
    data = out.getvalue()
    extracted = '\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(data)).pages)
    if normalized_text(extracted) != normalized_text('\n'.join(texts)):
        raise ValueError('PDF text does not match approved content')
    return data
