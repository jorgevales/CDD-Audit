#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CCLA mixed-file to per-change PDF merger. Windows-first, no OCR.

Performance edition: higher case-level parallelism, concurrent isolated Office
instances, faster footer mapping, and quiet non-fatal MuPDF diagnostics.
"""
from __future__ import annotations
import argparse, csv, gc, hashlib, json, math, os, re, shutil, subprocess, tempfile, time, traceback, uuid
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

MASTER_FOLDER = Path(os.environ.get(
    "CDD_MASTER_FOLDER",
    Path.home() / "CopilotCaseAutomation" / "IPs_Documents_Analysis" / "Temporary_100_batch_IP_files",
))
OUTPUT_FOLDER = Path(os.environ.get("CDD_MERGED_PDF_FOLDER", MASTER_FOLDER / "Merged_PDFs"))
CHANGE_RE = re.compile(r"^Change_(\d+)_Interested_Party_(.+)$", re.I)
PDFS={'.pdf'}; IMAGES={'.png','.jpg','.jpeg','.bmp','.gif','.tif','.tiff','.webp'}
WORDS={'.doc','.docx','.docm','.dot','.dotx','.rtf','.odt'}
EXCELS={'.xls','.xlsx','.xlsm','.xlsb','.ods','.csv','.tsv'}
PPTS={'.ppt','.pptx','.pptm','.pps','.ppsx','.odp'}
TEXTS={'.txt','.md','.log','.json','.xml','.html','.htm','.yaml','.yml','.ini','.cfg'}
EMAILS={'.msg','.eml'}
A4W,A4H,MARGIN=595.2756,841.8898,40
TARGET_DPI = 300
MAX_PART_PAGES = 100
MAX_WORKERS = 24
MAX_FILE_WORKERS = 6
DEFAULT_FILE_WORKERS = min(4, MAX_FILE_WORKERS)
DEFAULT_WORKERS = max(MAX_WORKERS, max(8, (os.cpu_count() or 8) + 4))
CASE_PROGRESS_DELAY_SECONDS = 10.0

# SETTINGS
OVERWRITE_EXISTING_FILES = False

@dataclass
class Item:
    index:int; filename:str; relative:str; ext:str; status:str; method:str
    pages:int; pdf:Optional[str]; error:str=''; sha256:str=''
    merged_start:Optional[int]=None; merged_end:Optional[int]=None

def say(s): print(s,flush=True)
def natural(s): return [int(x) if x.isdigit() else x.casefold() for x in re.split(r'(\d+)',s)]
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''): h.update(b)
    return h.hexdigest()
def files(folder):
    out=[]
    for p in folder.rglob('*'):
        if p.is_file() and p.name.casefold() not in {'thumbs.db','desktop.ini','.ds_store'} and not p.name.startswith('~$'): out.append(p)
    return sorted(out,key=lambda p:natural(str(p.relative_to(folder))))
def configure_mupdf():
    """Suppress noisy, non-fatal MuPDF ICC diagnostics in every process."""
    import fitz
    tools=getattr(fitz,'TOOLS',None)
    if tools is None: return
    for name in ('mupdf_display_errors','mupdf_display_warnings'):
        fn=getattr(tools,name,None)
        if callable(fn):
            try: fn(False)
            except Exception: pass
    reset=getattr(tools,'reset_mupdf_warnings',None)
    if callable(reset):
        try: reset()
        except Exception: pass

def inspect_pdf(p):
    import fitz
    configure_mupdf()
    d=fitz.open(p)
    try:
        if d.needs_pass: return {'pages':0,'password_required':True,'empty':False}
        n=d.page_count
        return {'pages':n,'password_required':False,'empty':n<1}
    finally: d.close()
def pdf_pages(p):
    info=inspect_pdf(p)
    if info['password_required']: raise PermissionError('PASSWORD_REQUIRED_UNAVAILABLE - password was not supplied')
    if info['empty']: raise RuntimeError('EMPTY_OR_INVALID_PDF - PDF contains no pages')
    return info['pages']

def soffice():
    for x in [shutil.which('soffice'),shutil.which('libreoffice'),r'C:\Program Files\LibreOffice\program\soffice.exe',r'C:\Program Files (x86)\LibreOffice\program\soffice.exe']:
        if x and Path(x).exists(): return str(x)
    return None

class OfficeLock:
    def __enter__(self):
        self.h=None
        if os.name=='nt':
            import ctypes
            k=ctypes.windll.kernel32; self.k=k
            self.h=k.CreateMutexW(None,False,r'Global\CCLA_PDF_OFFICE_CONVERSION')
            if not self.h or k.WaitForSingleObject(self.h,45000) not in (0,0x80): raise TimeoutError('Office conversion lock timeout')
        return self
    def __exit__(self,*a):
        if self.h: self.k.ReleaseMutex(self.h); self.k.CloseHandle(self.h)

def kill_office(kind):
    exe={'word':'WINWORD.EXE','excel':'EXCEL.EXE','powerpoint':'POWERPNT.EXE'}.get(kind)
    if exe and os.name=='nt': subprocess.run(['taskkill','/F','/IM',exe],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def word_com(src,out):
    import pythoncom,win32com.client; pythoncom.CoInitialize(); app=doc=None
    try:
        app=win32com.client.DispatchEx('Word.Application'); app.Visible=False; app.DisplayAlerts=0
        doc=app.Documents.Open(str(src),ReadOnly=True,AddToRecentFiles=False,ConfirmConversions=False,OpenAndRepair=True,NoEncodingDialog=True,Revert=False)
        doc.ExportAsFixedFormat(str(out),17,OpenAfterExport=False,OptimizeFor=0)
    finally:
        try:
            if doc: doc.Close(False)
            if app: app.Quit()
        finally: pythoncom.CoUninitialize()

def ppt_com(src,out):
    import pythoncom,win32com.client; pythoncom.CoInitialize(); app=deck=None
    try:
        app=win32com.client.DispatchEx('PowerPoint.Application')
        deck=app.Presentations.Open(str(src),WithWindow=False,ReadOnly=True); deck.SaveAs(str(out),32)
    finally:
        try:
            if deck: deck.Close()
            if app: app.Quit()
        finally: pythoncom.CoUninitialize()

def _set_excel_calculation_safely(app,value):
    """Best-effort only; this optimisation must never block conversion."""
    try: app.Calculation=value; return True
    except Exception: return False

def excel_com(src,out,original_name):
    import pythoncom,win32com.client; pythoncom.CoInitialize(); app=wb=None
    try:
        app=win32com.client.DispatchEx('Excel.Application'); app.Visible=False; app.DisplayAlerts=False; app.AskToUpdateLinks=False; app.EnableEvents=False; app.ScreenUpdating=False
        # Open first. Some Excel builds reject Application.Calculation before a workbook exists.
        wb=app.Workbooks.Open(str(src),UpdateLinks=0,ReadOnly=True,IgnoreReadOnlyRecommended=True,AddToMru=False,Notify=False)
        _set_excel_calculation_safely(app,-4135)
        rendered=0
        for ws in wb.Worksheets:
            try:
                ws.Visible=-1; used=ws.UsedRange; rows=max(1,int(used.Rows.Count)); cols=max(1,int(used.Columns.Count)); ps=ws.PageSetup
                ps.PrintArea=used.Address; ps.Zoom=False; ps.FitToPagesWide=1 if cols<=12 else (2 if cols<=24 else max(3,math.ceil(cols/12))); ps.FitToPagesTall=False
                ps.Orientation=2 if cols>7 else 1; ps.LeftMargin=app.InchesToPoints(.25); ps.RightMargin=app.InchesToPoints(.25)
                ps.TopMargin=app.InchesToPoints(.45); ps.BottomMargin=app.InchesToPoints(.45)
                ps.CenterHeader=f'Sheet: {ws.Name}'; ps.CenterFooter='Sheet print page &P of &N'
                try: ps.PrintTitleRows=used.Rows(1).Address if rows>45 else ''
                except Exception: pass
                rendered+=1
            except Exception: pass
        if not rendered: raise RuntimeError('Workbook contains no renderable worksheets')
        wb.ExportAsFixedFormat(0,str(out),Quality=0,IncludeDocProperties=True,IgnorePrintAreas=False,OpenAfterPublish=False)
    finally:
        try:
            if wb: wb.Close(False)
            if app: app.Quit()
        finally: pythoncom.CoUninitialize()

def lo_convert(src,out):
    exe=soffice()
    if not exe: raise RuntimeError('LibreOffice is not installed')
    od=out.parent/f'lo_{uuid.uuid4().hex[:8]}'; od.mkdir()
    try:
        r=subprocess.run([exe,'--headless','--convert-to','pdf','--outdir',str(od),str(src)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,errors='replace',timeout=300,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        made=od/(src.stem+'.pdf')
        if r.returncode or not made.exists(): raise RuntimeError((r.stderr or r.stdout or 'LibreOffice conversion failed').strip())
        shutil.copy2(made,out); pdf_pages(out)
    finally: shutil.rmtree(od,ignore_errors=True)

def office_convert(source,out,kind,original_name):
    # Short staging paths solve Windows/Office long-path failures.
    root=Path(tempfile.gettempdir())/'CCLA_PDF_STAGE'; root.mkdir(parents=True,exist_ok=True)
    token=uuid.uuid4().hex[:10]; src=root/f'i_{token}{source.suffix.lower()}'; made=root/f'o_{token}.pdf'; errs=[]
    try:
        shutil.copy2(source,src)
        if os.name=='nt':
            for attempt in range(1,4):
                try:
                    # DispatchEx creates an isolated Office instance and each worker
                    # has unique staged files, so conversions can safely run concurrently.
                    made.unlink(missing_ok=True)
                    if kind=='word': word_com(src,made); method='Microsoft Word'
                    elif kind=='excel': excel_com(src,made,original_name); method='Microsoft Excel'
                    else: ppt_com(src,made); method='Microsoft PowerPoint'
                    pdf_pages(made); shutil.copy2(made,out); return method
                except Exception as e:
                    errs.append(f'Office attempt {attempt}: {e}'); time.sleep(.6*attempt)
        try: lo_convert(src,made); shutil.copy2(made,out); return 'LibreOffice'
        except Exception as e: raise RuntimeError('; '.join(errs+[str(e)]))
    finally:
        gc.collect()
        for cleanup_file in (src,made):
            for cleanup_attempt in range(6):
                try: cleanup_file.unlink(missing_ok=True); break
                except PermissionError: time.sleep(.35*(cleanup_attempt+1))
                except OSError: break

def _ocr_ready_raster(frame, target_width, target_height):
    """Fast, conservative raster preparation for LLM/OCR readability.

    Vector PDFs and Office exports are never rasterized. Only image inputs are
    resized when their effective resolution on the PDF page is below TARGET_DPI.
    """
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    image=ImageOps.exif_transpose(frame).convert('RGB')
    target=(max(1,int(target_width)),max(1,int(target_height)))
    if image.width<target[0] or image.height<target[1]:
        scale=max(target[0]/image.width,target[1]/image.height)
        size=(max(target[0],round(image.width*scale)),max(target[1],round(image.height*scale)))
        image=image.resize(size,Image.Resampling.LANCZOS)
        image=ImageEnhance.Contrast(image).enhance(1.08)
        image=image.filter(ImageFilter.UnsharpMask(radius=.8,percent=115,threshold=3))
    return image

def image_pdf(src,out):
    import fitz,io
    from PIL import Image,ImageSequence
    d=fitz.open(); count=0
    with Image.open(src) as im:
        for fr in ImageSequence.Iterator(im):
            probe=fr.convert('RGB'); w,h=probe.size
            pw,ph=(A4H,A4W) if w>h else (A4W,A4H)
            scale=min((pw-80)/w,(ph-80)/h); dw,dh=w*scale,h*scale
            target_w=math.ceil((dw/72.0)*TARGET_DPI)
            target_h=math.ceil((dh/72.0)*TARGET_DPI)
            rgb=_ocr_ready_raster(fr,target_w,target_h)
            page=d.new_page(width=pw,height=ph); b=io.BytesIO()
            rgb.save(b,'PNG',compress_level=1,optimize=False,dpi=(TARGET_DPI,TARGET_DPI))
            page.insert_image(fitz.Rect((pw-dw)/2,(ph-dh)/2,(pw+dw)/2,(ph+dh)/2),stream=b.getvalue(),keep_proportion=True)
            count+=1
    if not count: raise RuntimeError('Image contains no readable frames')
    d.save(out,garbage=3,deflate=True,deflate_images=True); d.close(); return count

def text_pdf(src,out):
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    raw=src.read_text('utf-8',errors='replace'); st=getSampleStyleSheet(); mono=ParagraphStyle('Mono',parent=st['BodyText'],fontName='Courier',fontSize=7.5,leading=9.2)
    story=[Paragraph(src.name.replace('&','&amp;'),st['Heading1']),Spacer(1,8)]
    for line in raw.splitlines() or ['']:
        e=line.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace(' ','&nbsp;'); story.append(Paragraph(e or '&nbsp;',mono))
    SimpleDocTemplate(str(out),pagesize=A4,leftMargin=35,rightMargin=35,topMargin=40,bottomMargin=40).build(story); return pdf_pages(out)

def docx_python_fallback(src,out):
    """Render DOCX paragraphs and tables without Word or LibreOffice. No OCR."""
    from docx import Document
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape
    doc=Document(str(src)); styles=getSampleStyleSheet()
    body=ParagraphStyle('DocxBody',parent=styles['BodyText'],fontName='Helvetica',fontSize=9,leading=11,spaceAfter=5)
    heading=ParagraphStyle('DocxHeading',parent=styles['Heading2'],fontName='Helvetica-Bold',fontSize=12,leading=14,spaceBefore=7,spaceAfter=5)
    cell=ParagraphStyle('DocxCell',parent=body,fontSize=7.3,leading=8.5,spaceAfter=0)
    story=[Paragraph(escape(src.name),styles['Title']),Spacer(1,8)]
    for para in doc.paragraphs:
        value=para.text or ''
        if not value.strip(): story.append(Spacer(1,5)); continue
        style=heading if para.style and str(para.style.name).lower().startswith('heading') else body
        story.append(Paragraph(escape(value).replace('\n','<br/>'),style))
    for table_no,tbl in enumerate(doc.tables,1):
        story.append(Spacer(1,7)); story.append(Paragraph(f'Table {table_no}',heading)); data=[]
        max_cols=max((len(r.cells) for r in tbl.rows),default=0)
        for row in tbl.rows:
            vals=[Paragraph(escape(c.text or '').replace('\n','<br/>'),cell) for c in row.cells]
            vals += [Paragraph('',cell)]*(max_cols-len(vals)); data.append(vals)
        if data and max_cols:
            widths=[(A4[0]-56)/max_cols]*max_cols; rt=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
            rt.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.25,colors.grey),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)])); story.append(rt)
    if len(story)<=2: raise RuntimeError('DOCX contains no renderable paragraphs or tables')
    SimpleDocTemplate(str(out),pagesize=A4,leftMargin=28,rightMargin=28,topMargin=32,bottomMargin=32,title=src.name).build(story)
    return pdf_pages(out)

def xlsx_python_pdf(src,out,original_name):
    """Render XLSX/XLSM content without launching Excel.

    All worksheets are traversed. Non-empty cell values are rendered in bounded
    row/column blocks, and embedded worksheet images are appended as PDF pages.
    This avoids Excel COM hangs while preserving every workbook as PDF content.
    """
    from openpyxl import load_workbook
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image as RLImage
    from xml.sax.saxutils import escape
    import io

    wb=load_workbook(str(src),read_only=False,data_only=False,keep_links=False)
    styles=getSampleStyleSheet()
    title_style=styles['Heading1']
    small=ParagraphStyle('XCell',parent=styles['BodyText'],fontName='Helvetica',fontSize=5.7,leading=6.6,wordWrap='CJK')
    note=ParagraphStyle('XNote',parent=styles['BodyText'],fontName='Helvetica',fontSize=7,leading=8.5,textColor=colors.HexColor('#444444'))
    story=[Paragraph(escape(original_name),title_style),Spacer(1,6)]
    rendered_sheets=0; rendered_images=0
    max_rows_per_block=45; max_cols_per_block=10

    for ws in wb.worksheets:
        # Determine real occupied bounds from instantiated/non-empty cells rather
        # than Excel's often inflated UsedRange metadata.
        nonempty=[]
        for row in ws.iter_rows():
            vals=[]
            has_value=False
            for c in row:
                v=c.value
                if v is not None and str(v).strip()!='': has_value=True
                vals.append(v)
            if has_value: nonempty.append((row[0].row,vals))
        images=list(getattr(ws,'_images',[]) or [])
        if not nonempty and not images:
            story.append(Paragraph(f'Worksheet: {escape(ws.title)}',styles['Heading2']))
            story.append(Paragraph('Worksheet contains no populated cells or embedded images.',note))
            story.append(PageBreak()); rendered_sheets+=1; continue

        story.append(Paragraph(f'Worksheet: {escape(ws.title)}',styles['Heading2']))
        if nonempty:
            first_row=min(r for r,_ in nonempty); last_row=max(r for r,_ in nonempty)
            max_col=max((max((i+1 for i,v in enumerate(vals) if v is not None and str(v).strip()!=''),default=1) for _,vals in nonempty),default=1)
            story.append(Paragraph(f'Populated rows {first_row}-{last_row}; populated columns 1-{max_col}.',note)); story.append(Spacer(1,4))
            rowmap={r:vals for r,vals in nonempty}
            for col_start in range(1,max_col+1,max_cols_per_block):
                col_end=min(max_col,col_start+max_cols_per_block-1)
                rows_sorted=sorted(rowmap)
                for pos in range(0,len(rows_sorted),max_rows_per_block):
                    selected=rows_sorted[pos:pos+max_rows_per_block]
                    header=[Paragraph('Row',small)]+[Paragraph(str(c),small) for c in range(col_start,col_end+1)]
                    data=[header]
                    for r in selected:
                        vals=rowmap[r]
                        cells=[Paragraph(str(r),small)]
                        for c in range(col_start,col_end+1):
                            v=vals[c-1] if c-1<len(vals) else ''
                            text='' if v is None else str(v)
                            cells.append(Paragraph(escape(text).replace('\n','<br/>'),small))
                        data.append(cells)
                    avail=landscape(A4)[0]-40
                    widths=[26]+[(avail-26)/(col_end-col_start+1)]*(col_end-col_start+1)
                    table=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
                    table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.2,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E8EEF7')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),2),('RIGHTPADDING',(0,0),(-1,-1),2),('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
                    story.append(table); story.append(PageBreak())
        for img_no,img in enumerate(images,1):
            try:
                raw=img._data(); bio=io.BytesIO(raw)
                story.append(Paragraph(f'Worksheet {escape(ws.title)} - embedded image {img_no}',styles['Heading2']))
                pic=RLImage(bio)
                maxw,maxh=landscape(A4)[0]-50,landscape(A4)[1]-80
                scale=min(maxw/pic.imageWidth,maxh/pic.imageHeight,1.0)
                pic.drawWidth=pic.imageWidth*scale; pic.drawHeight=pic.imageHeight*scale
                story.append(pic); story.append(PageBreak()); rendered_images+=1
            except Exception as e:
                story.append(Paragraph(f'Embedded image {img_no} could not be rendered: {escape(str(e))}',note)); story.append(PageBreak())
        rendered_sheets+=1
    wb.close()
    if not rendered_sheets: raise RuntimeError('Workbook contains no worksheets')
    SimpleDocTemplate(str(out),pagesize=landscape(A4),leftMargin=20,rightMargin=20,topMargin=24,bottomMargin=24,title=original_name).build(story)
    return pdf_pages(out),rendered_images


def delimited_xlsx(src,out):
    from openpyxl import Workbook
    wb=Workbook(write_only=True); ws=wb.create_sheet('Data')
    with src.open('r',encoding='utf-8-sig',errors='replace',newline='') as f:
        for row in csv.reader(f,delimiter='\t' if src.suffix.lower()=='.tsv' else ','): ws.append(row)
    wb.save(out)

def convert(i,src,case,tmp,precomputed_hash=None):
    rel=str(src.relative_to(case)); ext=src.suffix.lower(); h=precomputed_hash or ''; out=tmp/f's_{i:05d}.pdf'
    try:
        if not h: h=digest(src)
        if ext in PDFS:
            if 'inspect_pdf' in globals():
                info=inspect_pdf(src)
                if info.get('password_required'): return Item(i,src.name,rel,ext,'PASSWORD_REQUIRED','Not merged',0,None,'Password required but unavailable',h)
                if info.get('empty'): return Item(i,src.name,rel,ext,'ACCEPTABLE_SOURCE_ERROR','Not merged',0,None,'EMPTY_OR_INVALID_PDF - source PDF contains no pages or has an invalid page tree and cannot be opened as a document',h)
                pages=info['pages']
            else: pages=pdf_pages(src)
            return Item(i,src.name,rel,ext,'CONVERTED_COMPLETE','Original PDF',pages,str(src),sha256=h)
        if ext in IMAGES: return Item(i,src.name,rel,ext,'CONVERTED_COMPLETE','Image to PDF (no OCR)',image_pdf(src,out),str(out),sha256=h)
        if ext in TEXTS: return Item(i,src.name,rel,ext,'CONVERTED_COMPLETE','Text rendered to PDF',text_pdf(src,out),str(out),sha256=h)
        actual=src
        if ext in {'.csv','.tsv'}: actual=tmp/f'd_{i}.xlsx'; delimited_xlsx(src,actual)
        if ext in WORDS:
            if ext in {'.docx','.docm','.dotx'}:
                try:
                    docx_python_fallback(actual,out); method='Fast Python DOCX renderer'
                except Exception as python_error:
                    try: method=office_convert(actual,out,'word',src.name)
                    except Exception as office_error: raise RuntimeError(f'Python DOCX renderer failed: {python_error}; Office conversion failed: {office_error}')
            else: method=office_convert(actual,out,'word',src.name)
        elif ext in EXCELS:
            if ext in {'.xlsx','.xlsm'}:
                try:
                    _,image_count=xlsx_python_pdf(actual,out,src.name)
                    method=f'Python XLSX complete renderer ({image_count} embedded image(s))'
                except Exception as python_error:
                    try: method=office_convert(actual,out,'excel',src.name)
                    except Exception as office_error: raise RuntimeError(f'Python XLSX renderer failed: {python_error}; Office conversion failed: {office_error}')
            else:
                method=office_convert(actual,out,'excel',src.name)
        elif ext in PPTS: method=office_convert(actual,out,'powerpoint',src.name)
        else: return Item(i,src.name,rel,ext or '[none]','UNSUPPORTED','None',0,None,'Unsupported file type',h)
        return Item(i,src.name,rel,ext,'CONVERTED_COMPLETE',method,pdf_pages(out),str(out),sha256=h)
    except Exception as e: return Item(i,src.name,rel,ext or '[none]','CONVERSION_FAILED','Failed',0,None,str(e),h)

def convert_case_files(srcs,case,tmp,file_workers=1,case_started=None):
    """Convert every source independently; Excel-family files run serially.
    Per-file output stays quiet for fast cases. After the case has run for the
    configured delay, subsequent file progress is printed in the existing format.
    """
    if not srcs: return []
    case_started=time.monotonic() if case_started is None else case_started
    progress_announced=False
    def progress(message):
        nonlocal progress_announced
        if time.monotonic()-case_started<CASE_PROGRESS_DELAY_SECONDS:
            return
        if not progress_announced:
            say(f'[{case.name}] Still processing after {CASE_PROGRESS_DELAY_SECONDS:g}s; showing per-file progress:')
            progress_announced=True
        say(message)
    file_workers=max(1,min(int(file_workers or 1),MAX_FILE_WORKERS,len(srcs)))
    entries=list(enumerate(srcs,1)); converted={}
    excel_entries=[e for e in entries if e[1].suffix.lower() in EXCELS]
    safe_entries=[e for e in entries if e[1].suffix.lower() not in EXCELS]
    def run(entry):
        idx,src=entry
        return idx,convert(idx,src,case,tmp)
    if safe_entries and file_workers>1:
        with ThreadPoolExecutor(max_workers=min(file_workers,len(safe_entries))) as pool:
            fm={pool.submit(run,e):e[0] for e in safe_entries}
            for done,f in enumerate(as_completed(fm),1):
                idx,item=f.result(); converted[idx]=item
                progress(f'[{case.name}] non-Excel {done}/{len(safe_entries)}: {item.filename} [{item.status}]')
    else:
        for done,e in enumerate(safe_entries,1):
            idx,item=run(e); converted[idx]=item
            progress(f'[{case.name}] non-Excel {done}/{len(safe_entries)}: {item.filename} [{item.status}]')
    for done,e in enumerate(excel_entries,1):
        progress(f'[{case.name}] Excel {done}/{len(excel_entries)} START: {e[1].name}')
        idx,item=run(e); converted[idx]=item
        progress(f'[{case.name}] Excel {done}/{len(excel_entries)} DONE: {item.filename} [{item.status}]')
    items=[converted[i] for i in range(1,len(srcs)+1)]
    if len(items)!=len(srcs): raise RuntimeError(f'Completeness failure: discovered {len(srcs)} source files but created {len(items)} conversion records')
    return items
def wrapped(page,text,rect,size=8,bold=False,color=(0,0,0)):
    page.insert_textbox(rect,text,fontsize=size,fontname='hebo' if bold else 'helv',color=color,lineheight=1.18)

def front(case,items,tmp,part_no,part_count):
    """Create a compact, fixed one-page cover so the 100-page cap is exact."""
    import fitz
    out=tmp/f'front_part_{part_no}.pdf'; d=fitz.open(); p=d.new_page(width=A4W,height=A4H)
    p.insert_text((40,72),case,fontsize=18,fontname='hebo',color=(.08,.2,.38))
    p.insert_text((40,102),f'Consolidated evidence PDF - part {part_no} of {part_count}',fontsize=12,fontname='hebo')
    msg=(f'This part contains {len(items)} complete source document(s). Source documents are never split between parts. '
         f'Raster image sources are prepared for a minimum effective rendering target of {TARGET_DPI} DPI; '
         'vector PDF and Office content is preserved without rasterization. Use the PDF bookmarks and source dividers for navigation.')
    wrapped(p,msg,fitz.Rect(40,130,A4W-40,235),10)
    bad=[x for x in items if x.status!='CONVERTED_COMPLETE']
    p.insert_text((40,275),'Package status',fontsize=12,fontname='hebo')
    p.insert_text((40,300),'COMPLETE' if not bad else 'PARTIAL - see source dividers',fontsize=11,fontname='hebo',color=(0,.45,.18) if not bad else (.75,.2,.05))
    p.insert_text((40,345),'Part contents',fontsize=12,fontname='hebo')
    converted=sum(1 for x in items if x.status=='CONVERTED_COMPLETE')
    source_pages=sum(x.pages for x in items if x.status=='CONVERTED_COMPLETE')
    details=(f'{converted} converted source file(s) | {source_pages} source page(s) | '
             f'{len(bad)} conversion exception(s) | maximum configured part size {MAX_PART_PAGES} pages')
    wrapped(p,details,fitz.Rect(40,365,A4W-40,430),9)
    note=('The 300-DPI target applies to raster image placement. Existing PDFs and Office exports retain their native vector text, '
          'fonts and images, which is normally clearer and faster for LLM reading than flattening every page to a bitmap.')
    wrapped(p,note,fitz.Rect(40,455,A4W-40,545),9,color=(.25,.25,.25))
    d.save(out,garbage=3,deflate=True); d.close(); return out

def divider(case,x,tmp):
    import fitz
    out=tmp/f'div_{x.index}.pdf'; d=fitz.open(); p=d.new_page(width=A4W,height=A4H); p.insert_text((40,70),f'Source document {x.index}',fontsize=18,fontname='hebo',color=(.08,.2,.38)); y=115
    rows=[('Original filename',x.filename),('Folder-relative name',x.relative),('Original format',x.ext),('Source extent',f'{x.pages} page(s)' if x.pages else 'Not converted'),('Merged PDF pages',f'{x.merged_start}-{x.merged_end}' if x.merged_start else 'Exception divider only'),('Conversion status',x.status),('Conversion method',x.method),('SHA-256',x.sha256 or 'Unavailable')]
    if x.error: rows.append(('Exception',x.error))
    for label,value in rows:
        p.insert_text((40,y),label,fontsize=9,fontname='hebo'); h=max(24,9*math.ceil(max(1,len(value))/72)); wrapped(p,value,fitz.Rect(160,y-10,A4W-40,y+h),8.5); y+=h+9
    d.save(out,garbage=3,deflate=True); d.close(); return out

def failure_file_entry(case, item):
    """Return a stable, machine-readable failure record for one source file."""
    source_path = case / item.relative
    return {
        'file_name': item.filename,
        'relative_path': item.relative,
        'file_path': str(source_path.resolve()),
        'extension': item.ext,
        'status': item.status,
        'error': item.error,
        'conversion_method': item.method,
        'sha256': item.sha256 or None,
    }

def package_failure_entry(case, error, failure_type='PACKAGE_FAILURE'):
    """Return a machine-readable non-file/package-level failure record."""
    return {
        'file_name': None,
        'relative_path': None,
        'file_path': str(case.resolve()),
        'extension': None,
        'status': failure_type,
        'error': str(error),
        'conversion_method': None,
        'sha256': None,
    }

def item_part_pages(item):
    """One divider page plus the converted document, or divider only on failure."""
    return 1+(item.pages if item.status=='CONVERTED_COMPLETE' and item.pdf else 0)

def pack_complete_documents(items,max_pages=MAX_PART_PAGES):
    """Best-fit-decreasing bin packing with one fixed cover page per output.

    This maximizes use of each part without splitting a source document. An item
    larger than the normal payload capacity is placed alone and may exceed the cap.
    """
    capacity=max(1,max_pages-1)
    ordered=sorted(items,key=lambda x:(-item_part_pages(x),natural(x.relative)))
    bins=[]
    for item in ordered:
        size=item_part_pages(item)
        candidates=[(capacity-used,idx) for idx,(used,_) in enumerate(bins) if used+size<=capacity]
        if candidates:
            _,idx=min(candidates)
            used,members=bins[idx]; members.append(item); bins[idx]=(used+size,members)
        else:
            bins.append((size,[item]))
    return [sorted(members,key=lambda x:x.index) for _,members in bins]

def _insert_document(merged,pdf_path):
    import fitz
    q=fitz.open(pdf_path)
    if q.needs_pass:
        q.close(); raise PermissionError('Password required but unavailable')
    try:
        merged.insert_pdf(q,links=False,annots=False,widgets=False)
    except Exception:
        for source_page_no in range(q.page_count):
            single=fitz.open()
            single.insert_pdf(q,from_page=source_page_no,to_page=source_page_no,links=False,annots=False,widgets=False)
            merged.insert_pdf(single,links=False,annots=False,widgets=False)
            single.close()
    finally:
        q.close()

def build(case_s,out_s,target_dpi=TARGET_DPI,max_part_pages=MAX_PART_PAGES,file_workers=1):
    global TARGET_DPI,MAX_PART_PAGES
    TARGET_DPI=max(300,int(target_dpi)); MAX_PART_PAGES=max(2,int(max_part_pages))
    import fitz
    configure_mupdf()
    case=Path(case_s); outdir=Path(out_s); started=time.time(); case_started=time.monotonic()
    intended_first=outdir/f'{case.name}_part_1.pdf'
    try:
        srcs=files(case)
        if not srcs:
            failure=package_failure_entry(case,'No source files found','NO_SOURCE_FILES')
            return {'case':case.name,'case_path':str(case.resolve()),'status':'FAILED','output':str(intended_first),'outputs':[],'related_documents':[],'failed_files':[failure],'failed_file_paths':[],'acceptable_errors':[],'seconds':round(time.time()-started,2)}
        work=outdir/'_working'; work.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='c_',dir=work) as td:
            tmp=Path(td); items=convert_case_files(srcs,case,tmp,file_workers,case_started)
            parts=pack_complete_documents(items,MAX_PART_PAGES)
            part_count=len(parts); staged=[]; related=[]
            for part_no,part_items in enumerate(parts,1):
                front_pdf=front(case.name,part_items,tmp,part_no,part_count)
                merged=fitz.open(); q=fitz.open(front_pdf); merged.insert_pdf(q); q.close()
                toc=[[1,f'{case.name} - part {part_no}',1]]
                cursor=2
                for x in part_items:
                    divider_page=cursor; cursor+=1
                    if x.status=='CONVERTED_COMPLETE' and x.pdf:
                        x.merged_start=cursor; x.merged_end=cursor+x.pages-1; cursor+=x.pages
                    else:
                        x.merged_start=None; x.merged_end=None
                    dv=divider(case.name,x,tmp); q=fitz.open(dv); merged.insert_pdf(q); q.close()
                    toc.append([1,x.relative,divider_page])
                    if x.status=='CONVERTED_COMPLETE' and x.pdf:
                        _insert_document(merged,x.pdf)
                total=merged.page_count
                for pi in range(total):
                    page=merged[pi]; gp=pi+1
                    footer=f'{case.name} | Part {part_no}/{part_count} | PDF page {gp}/{total}'
                    for x in part_items:
                        if x.merged_start is not None and x.merged_start<=gp<=x.merged_end:
                            footer=(f'{case.name} | Part {part_no}/{part_count} | Source: {x.filename} | '
                                    f'Source page {gp-x.merged_start+1}/{x.pages} | PDF page {gp}/{total}')
                            break
                    page.insert_textbox(type(page.rect)(18,page.rect.height-18,page.rect.width-18,page.rect.height-4),footer,fontsize=6.1,fontname='helv',color=(.28,.28,.28),align=1)
                try: merged.set_toc(toc)
                except Exception: pass
                stage=tmp/f'{case.name}_part_{part_no}.pdf'
                try: merged.save(stage,garbage=0,deflate=True,deflate_images=True,deflate_fonts=True)
                except Exception:
                    rebuilt=fitz.open()
                    for page_no in range(merged.page_count):
                        rebuilt.insert_pdf(merged,from_page=page_no,to_page=page_no,links=False,annots=False,widgets=False)
                    rebuilt.save(stage,garbage=0,deflate=False); rebuilt.close()
                merged.close(); actual_pages=pdf_pages(stage)
                oversized=actual_pages>MAX_PART_PAGES
                if oversized and len(part_items)>1:
                    raise RuntimeError(f'Internal packing error: part {part_no} has {actual_pages} pages')
                final=outdir/f'{case.name}_part_{part_no}.pdf'
                staged.append((stage,final,actual_pages,oversized))
            final.parent.mkdir(parents=True,exist_ok=True)
            for old in outdir.glob(f'{case.name}_part_*.pdf'):
                old.unlink(missing_ok=True)
            legacy=outdir/f'{case.name}.pdf'; legacy.unlink(missing_ok=True)
            for stage,final,actual_pages,oversized in staged:
                os.replace(stage,final)
                related.append({'file_name':final.name,'file_path':str(final.resolve()),'pages':actual_pages,'oversized_single_document':oversized})
            if len(items)!=len(srcs):
                raise RuntimeError(f'Completeness failure: {len(srcs)} discovered source files but {len(items)} packaged source records')
            packaged_indexes=sorted(x.index for part_items in parts for x in part_items)
            expected_indexes=list(range(1,len(srcs)+1))
            if packaged_indexes!=expected_indexes:
                missing=sorted(set(expected_indexes)-set(packaged_indexes))
                repeated=sorted(i for i in set(packaged_indexes) if packaged_indexes.count(i)>1)
                raise RuntimeError(f'Completeness failure in PDF packing. Missing source indexes: {missing}; repeated source indexes: {repeated}')
            failed=[failure_file_entry(case,x) for x in items if x.status not in {'CONVERTED_COMPLETE','ACCEPTABLE_SOURCE_ERROR'}]
            acceptable=[failure_file_entry(case,x) for x in items if x.status=='ACCEPTABLE_SOURCE_ERROR']
            return {
                'case':case.name,
                'case_path':str(case.resolve()),
                'status':'SUCCESS' if not failed else 'PARTIAL',
                'source_files_discovered':len(srcs),
                'source_records_packaged':len(items),
                'converted_source_files':sum(x.status=='CONVERTED_COMPLETE' for x in items),
                'source_exception_dividers':sum(x.status!='CONVERTED_COMPLETE' for x in items),
                'output':related[0]['file_path'] if related else str(intended_first),
                'outputs':[x['file_path'] for x in related],
                'related_documents':related,
                'failed_files':failed,
                'failed_file_paths':[x['file_path'] for x in failed],
                'acceptable_errors':acceptable,
                'seconds':round(time.time()-started,2),
            }
    except Exception as e:
        failure=package_failure_entry(case,e)
        return {'case':case.name,'case_path':str(case.resolve()),'status':'FAILED','output':str(intended_first),'outputs':[],'related_documents':[],'failed_files':[failure],'failed_file_paths':[],'acceptable_errors':[],'seconds':round(time.time()-started,2),'trace':traceback.format_exc()}

def cid(s):
    m=re.search(r'\d+',s.strip())
    if not m: raise ValueError(f'Invalid Change ID: {s}')
    return int(m.group())
def cases(a,b):
    out=[]
    for p in MASTER_FOLDER.iterdir():
        m=CHANGE_RE.match(p.name) if p.is_dir() else None
        if m and a<=int(m.group(1))<=b: out.append((int(m.group(1)),p))
    return sorted(out,key=lambda z:(z[0],natural(z[1].name)))

def previous_retry_cases(a,b):
    log=OUTPUT_FOLDER/f'merge_status_{a}_{b}.json'
    if not log.exists(): return set()
    try:
        data=json.loads(log.read_text(encoding='utf-8'))
        return {str(r.get('case')) for r in data.get('results',[]) if r.get('case') and r.get('status') in {'PARTIAL','FAILED'}}
    except Exception as e:
        say(f'WARNING: Could not read previous status log {log}: {e}'); return set()

def existing_pdf_is_valid(path):
    try: return path.exists() and pdf_pages(path)>0
    except Exception: return False

def existing_case_parts(case_name):
    def part_number(path):
        m=re.search(r'_part_(\d+)\.pdf$',path.name,re.I)
        return int(m.group(1)) if m else 10**9
    return sorted(OUTPUT_FOLDER.glob(f'{case_name}_part_*.pdf'),key=part_number)

def main():
    global TARGET_DPI,MAX_PART_PAGES
    configure_mupdf()
    ap=argparse.ArgumentParser()
    ap.add_argument('--from-id'); ap.add_argument('--to-id')
    ap.add_argument('--workers',type=int,default=DEFAULT_WORKERS,help=f'Parallel case workers (default: {DEFAULT_WORKERS}, maximum: {MAX_WORKERS})')
    ap.add_argument('--file-workers',type=int,default=DEFAULT_FILE_WORKERS,help=f'Parallel file conversions when only one case is queued (default: {DEFAULT_FILE_WORKERS}, maximum: {MAX_FILE_WORKERS})')
    ap.add_argument('--target-dpi',type=int,default=TARGET_DPI,help=f'Minimum effective DPI for raster image sources (default: {TARGET_DPI})')
    ap.add_argument('--max-pages',type=int,default=MAX_PART_PAGES,help=f'Maximum pages per part unless one complete document is larger (default: {MAX_PART_PAGES})')
    ap.add_argument('--overwrite',action=argparse.BooleanOptionalAction,default=OVERWRITE_EXISTING_FILES,help='--overwrite rebuilds all; --no-overwrite retries only missing and prior PARTIAL/FAILED cases')
    ap.add_argument('--yes',action='store_true',help='Skip the final start confirmation (for a parent script that already confirmed the run)')
    ns=ap.parse_args()
    TARGET_DPI=max(300,int(ns.target_dpi)); MAX_PART_PAGES=max(2,int(ns.max_pages))
    try: a=cid(ns.from_id or input('From Change ID: ')); b=cid(ns.to_id or input('To Change ID: '))
    except Exception as e: say(f'FAILED: {e}'); return 2
    if a>b:a,b=b,a
    if not MASTER_FOLDER.exists(): say(f'FAILED: Master folder does not exist: {MASTER_FOLDER}'); return 2
    OUTPUT_FOLDER.mkdir(parents=True,exist_ok=True); cs=cases(a,b)
    if not cs: say(f'FAILED: No matching Change ID folders for range {a}-{b}.'); return 1
    say(f'Confirmed working range: {a}-{b} ({len(cs)} matching Change folder(s)).')
    if not ns.yes:
        try:
            answer=input('Run PDF merge for this range now? Enter Y to continue: ').strip().upper()
        except (EOFError, KeyboardInterrupt):
            say('Cancelled.'); return 0
        if answer != 'Y':
            say('Cancelled. No PDFs were processed.'); return 0
    retry_cases=previous_retry_cases(a,b) if not ns.overwrite else set()
    pending=[]; results=[]
    for n,p in cs:
        existing=existing_case_parts(p.name)
        if not ns.overwrite and p.name not in retry_cases and existing and all(existing_pdf_is_valid(x) for x in existing):
            related=[{'file_name':x.name,'file_path':str(x.resolve()),'pages':pdf_pages(x),'oversized_single_document':pdf_pages(x)>MAX_PART_PAGES} for x in existing]
            results.append({'case':p.name,'case_path':str(p.resolve()),'status':'SUCCESS','output':related[0]['file_path'],'outputs':[x['file_path'] for x in related],'related_documents':related,'failed_files':[],'failed_file_paths':[],'acceptable_errors':[],'seconds':0,'skipped_existing':True})
            say(f'[SKIP] Change {n}: {len(existing)} valid existing PDF part(s) preserved'); continue
        pending.append((n,p))
    say(f'Range {a}-{b}: {len(pending)} queued, {len(results)} successful existing skipped, overwrite={ns.overwrite}, target_dpi={TARGET_DPI}, max_pages={MAX_PART_PAGES}')
    if retry_cases: say(f'Prior PARTIAL/FAILED cases selected: {len(retry_cases)}')
    if pending:
        workers=max(1,min(ns.workers if ns.workers>0 else DEFAULT_WORKERS,len(pending),MAX_WORKERS))
        file_workers=max(1,min(ns.file_workers if ns.file_workers>0 else DEFAULT_FILE_WORKERS,MAX_FILE_WORKERS)) if workers==1 else 1
        say(f'Execution plan: {workers} case worker(s), {file_workers} file worker(s) per case')
        with ProcessPoolExecutor(max_workers=workers) as pool:
            fm={pool.submit(build,str(p),str(OUTPUT_FOLDER),TARGET_DPI,MAX_PART_PAGES,file_workers):(n,p) for n,p in pending}
            for k,fut in enumerate(as_completed(fm),len(results)+1):
                n,p=fm[fut]
                try:r=fut.result()
                except Exception as e:
                    failure=package_failure_entry(p,e,'WORKER_FAILURE')
                    first=OUTPUT_FOLDER/f'{p.name}_part_1.pdf'
                    r={'case':p.name,'case_path':str(p.resolve()),'status':'FAILED','output':str(first),'outputs':[],'related_documents':[],'failed_files':[failure],'failed_file_paths':[],'acceptable_errors':[],'seconds':0}
                results.append(r); say(f'[{k}/{len(cs)}] Change {n}: {r["status"]} | {len(r.get("related_documents",[]))} PDF part(s)')
                if r['status']=='FAILED' and r['failed_files']: say(f'  Reason: {r["failed_files"][0]["error"]}')
    results.sort(key=lambda r:natural(r['case'])); bad=[r for r in results if r['status']!='SUCCESS']
    all_failed_files=[dict(x,case=r['case'],case_path=r.get('case_path')) for r in results for x in r.get('failed_files',[]) if x.get('file_name')]
    all_failed_file_paths=[x['file_path'] for x in all_failed_files]
    all_related_documents=[dict(x,case=r['case'],case_path=r.get('case_path')) for r in results for x in r.get('related_documents',[])]
    summary={'range_from':a,'range_to':b,'overall_status':'SUCCESS' if not bad else 'PARTIAL_OR_FAILED','target_dpi':TARGET_DPI,'max_pages_per_pdf':MAX_PART_PAGES,'cases_requested':len(cs),'source_files_discovered':sum(r.get('source_files_discovered',0) for r in results),'source_records_packaged':sum(r.get('source_records_packaged',0) for r in results),'cases_successful':sum(r['status']=='SUCCESS' for r in results),'cases_partial':sum(r['status']=='PARTIAL' for r in results),'cases_failed':sum(r['status']=='FAILED' for r in results),'related_documents':all_related_documents,'failed_file_count':len(all_failed_files),'failed_file_paths':all_failed_file_paths,'failed_files':all_failed_files,'results':results}
    log=OUTPUT_FOLDER/f'merge_status_{a}_{b}.json'; log.write_text(json.dumps(summary,indent=2,ensure_ascii=False),'utf-8')
    say('\nFINAL RANGE STATUS: '+summary['overall_status'])
    for r in bad:
        say(f'{r["case"]}: {r["status"]}')
        for x in r['failed_files']:
            path=x.get('file_path') or '[no file path]'
            say(f'  - {path} | {x.get("status")} | {x.get("error")}')
    say(f'Related PDF documents: {len(all_related_documents)}')
    say(f'Status log: {log}'); return 0 if not bad else 1

if __name__=='__main__':
    from multiprocessing import freeze_support
    freeze_support(); raise SystemExit(main())
