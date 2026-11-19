"""Genera el PDF desde Markdown y figuras C4. Requiere reportlab y Pillow."""
import html
import re
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from PIL import Image as PILImage

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT/'docs'
fontdir = Path('C:/Windows/Fonts')
if (fontdir/'arial.ttf').exists():
    pdfmetrics.registerFont(TTFont('Body',str(fontdir/'arial.ttf')))
    pdfmetrics.registerFont(TTFont('BodyBold',str(fontdir/'arialbd.ttf')))
else:
    from reportlab import rl_config
    search = Path(rl_config.TTFSearchPath[0])
    pdfmetrics.registerFont(TTFont('Body',str(search/'Vera.ttf')))
    pdfmetrics.registerFont(TTFont('BodyBold',str(search/'VeraBd.ttf')))
pdfmetrics.registerFontFamily('Body',normal='Body',bold='BodyBold',italic='Body',boldItalic='BodyBold')
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyCustom',fontName='Body',fontSize=9.5,leading=14,spaceAfter=8,textColor=colors.HexColor('#263d43')))
styles.add(ParagraphStyle(name='H1Custom',fontName='BodyBold',fontSize=17,leading=22,spaceBefore=16,spaceAfter=11,keepWithNext=True,textColor=colors.HexColor('#123d43')))
styles.add(ParagraphStyle(name='H2Custom',fontName='BodyBold',fontSize=11.5,leading=16,spaceBefore=12,spaceAfter=7,keepWithNext=True,textColor=colors.HexColor('#146f68')))
styles.add(ParagraphStyle(name='CellCustom',fontName='Body',fontSize=8,leading=11,spaceAfter=0))
styles.add(ParagraphStyle(name='CellHeader',fontName='BodyBold',fontSize=8,leading=11,textColor=colors.white))
styles.add(ParagraphStyle(name='CoverTitle',fontName='BodyBold',fontSize=34,leading=41,textColor=colors.HexColor('#123d43'),spaceAfter=18))
styles.add(ParagraphStyle(name='CoverSub',fontName='Body',fontSize=14,leading=21,textColor=colors.HexColor('#42646b'),spaceAfter=14))

def inline(value):
    value = html.escape(value)
    value = re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',value)
    return value.replace('`','')

def footer(c, doc):
    c.saveState()
    c.setFont('Body',8)
    c.setFillColor(colors.HexColor('#6c848a'))
    c.drawString(42,28,'FRÍOALERTA  /  ARQUITECTURA DE SOFTWARE')
    c.drawRightString(A4[0]-42,28,str(doc.page))
    c.restoreState()

story=[]
story += [Spacer(1,80),Paragraph('Arquitectura de<br/>FríoAlerta',styles['CoverTitle']),Paragraph('Monitoreo de temperatura mediante sensores IoT',styles['CoverSub']),Spacer(1,25)]
story.append(Paragraph('Proyecto final de Arquitectura de Software<br/>Docente MSc. Feisar Moreno<br/>Versión 1.0 · 18 de noviembre de 2026',styles['CoverSub']))
story.append(Spacer(1,42))
story.append(Paragraph('Diseño e implementación de una aplicación con tres canales de entrada, procesamiento diferido y gestión de incidentes térmicos. Incluye modelo C4, decisiones de arquitectura, contrato de integración y evidencia de verificación.',styles['BodyCustom']))
story.append(Spacer(1,20))
story.append(Paragraph('El documento distingue las capacidades implementadas, las pruebas ejecutadas y las verificaciones pendientes del perfil distribuido.',styles['BodyCustom']))
story.append(PageBreak())
story.append(Paragraph('Contenido',styles['H1Custom']))
lines=(DOCS/'arquitectura.md').read_text(encoding='utf-8').splitlines()
for line in lines:
    if line.startswith('## '):
        story.append(Paragraph(inline(line[3:]),styles['BodyCustom']))
story.append(PageBreak())
i=next(i for i,line in enumerate(lines) if line.startswith('## 1 '))
while i<len(lines):
    line=lines[i].strip()
    if not line:
        i+=1;continue
    if line.startswith('## '):
        story.append(Paragraph(inline(line[3:]),styles['H1Custom']))
    elif line.startswith('### '):
        story.append(Paragraph(inline(line[4:]),styles['H2Custom']))
    elif line.startswith('!['):
        filename=re.search(r'\]\((.*?)\)',line).group(1)
        imagefile=DOCS/filename.replace('.pdf','.png')
        w,h=PILImage.open(imagefile).size
        width=490; height=width*h/w
        if height>460:
            width*=460/height; height=460
        story.append(Image(str(imagefile),width=width,height=height))
        story.append(Spacer(1,12))
    elif line.startswith('|'):
        rows=[]
        while i<len(lines) and lines[i].strip().startswith('|'):
            row=[cell.strip() for cell in lines[i].strip().strip('|').split('|')]
            if not all(re.fullmatch(r'[-: ]+',v) for v in row): rows.append(row)
            i+=1
        count=len(rows[0]); widths={3:[110,125,276],4:[86,128,148,149]}.get(count,[511/count]*count)
        if rows[0][0]=='ID': widths=[45,150,316]
        if rows[0][0]=='Método y ruta': widths=[195,95,221]
        table=Table([[Paragraph(inline(cell),styles['CellHeader'] if ri==0 else styles['CellCustom']) for cell in row] for ri,row in enumerate(rows)],colWidths=widths,repeatRows=1,hAlign='LEFT')
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#164c52')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f0f6f5')]),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#cfdddd')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
        story.extend([table,Spacer(1,12)]);continue
    else:
        story.append(Paragraph(inline(line),styles['BodyCustom']))
    i+=1

SimpleDocTemplate(str(DOCS/'Arquitectura_FrioAlerta.pdf'),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=40,bottomMargin=47,title='Arquitectura de FríoAlerta',author='Proyecto de Arquitectura de Software').build(story,onFirstPage=footer,onLaterPages=footer)
for name in ['c4_nivel_1','c4_nivel_2','c4_nivel_3']:
    imagefile=DOCS/'diagramas'/f'{name}.png'; w,h=PILImage.open(imagefile).size
    width=750; height=width*h/w
    c=canvas.Canvas(str(DOCS/'diagramas'/f'{name}.pdf'),pagesize=(width+40,height+40))
    c.drawImage(str(imagefile),20,20,width,height)
    c.save()
print('PDF generado:',DOCS/'Arquitectura_FrioAlerta.pdf')
