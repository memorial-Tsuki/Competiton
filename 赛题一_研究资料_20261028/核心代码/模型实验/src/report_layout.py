from pathlib import Path
import html
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY,TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4

ROOT=Path(__file__).resolve().parents[1]
pdfmetrics.registerFont(TTFont('CN','C:/Windows/Fonts/msyh.ttc'))
pdfmetrics.registerFont(TTFont('CNB','C:/Windows/Fonts/msyhbd.ttc'))
STYLES={
 'title':ParagraphStyle('title',fontName='CNB',fontSize=19,leading=27,spaceAfter=10),
 'h1':ParagraphStyle('h1',fontName='CNB',fontSize=14.5,leading=21,spaceAfter=9),
 'h2':ParagraphStyle('h2',fontName='CNB',fontSize=12,leading=18,spaceBefore=8,spaceAfter=6),
 'body':ParagraphStyle('body',fontName='CN',fontSize=11.5,leading=19,spaceAfter=8,wordWrap='CJK',alignment=TA_JUSTIFY),
 'small':ParagraphStyle('small',fontName='CN',fontSize=9,leading=14,spaceAfter=7,wordWrap='CJK'),
 'cell':ParagraphStyle('cell',fontName='CN',fontSize=9,leading=13.5,wordWrap='CJK'),
 'formula':ParagraphStyle('formula',fontName='CN',fontSize=10,leading=16,spaceAfter=8,alignment=TA_CENTER),
}
class Writer:
    def __init__(self,label,total):self.story=[];self.md=[];self.label=label;self.total=total
    def p(self,text,kind='body'):
        text=str(text).replace('₀','0');self.story.append(Paragraph(html.escape(text),STYLES[kind]));self.md.append(text+'\n')
    def h(self,text):self.p(text,'h2')
    def page(self,text):
        if self.story:self.story.append(PageBreak());self.md.append('\n---\n')
        self.p(text,'title' if not self.story else 'h1')
    def table(self,headers,rows,widths=None):
        widths=widths or [485/len(headers)]*len(headers)
        data=[[Paragraph(html.escape(str(x)).replace('₀','0'),STYLES['cell']) for x in r] for r in [headers]+rows]
        t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E0E9EC')),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#D5D9DC')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        self.story.extend([t,Spacer(1,8)])
        self.md.extend(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,row))+' |' for row in rows]+[''])
    def fig(self,name,caption,width=485):
        from PIL import Image as PILImage
        path=ROOT/'results/figures'/name
        with PILImage.open(path) as im:ww,hh=im.size
        self.story.append(Image(str(path),width=width,height=width*hh/ww));self.p(caption,'small');self.md.append(f'![{caption}](../results/figures/{name})\n')
    def save(self,pdf_path,md_path):
        def footer(canvas,doc):
            canvas.saveState();canvas.setFont('CN',7.5);canvas.setFillColor(colors.HexColor('#666666'));canvas.drawString(48,27,self.label);canvas.drawRightString(A4[0]-48,27,f'{doc.page} / {self.total}');canvas.restoreState()
        SimpleDocTemplate(str(pdf_path),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=38,bottomMargin=47,title=self.label,author='匿名参赛团队').build(self.story,onFirstPage=footer,onLaterPages=footer)
        md_path.write_text('\n'.join(self.md),encoding='utf-8')
        from pypdf import PdfReader
        n=len(PdfReader(pdf_path).pages);print(pdf_path.name,'pages',n);assert n==self.total,(n,self.total)
