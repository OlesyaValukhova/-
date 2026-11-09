"""Export the page-structured research draft to PDF/DOCX; retain editable source."""
import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.tools/report-export'))
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, KeepInFrame, Image
from PIL import Image as RasterImage, ImageDraw, ImageFont
from docx import Document
from docx.shared import Pt, Cm
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.section import WD_SECTION_START, WD_ORIENT


def blocks(text):
    lines = text.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith('#'):
            yield 'heading', (len(line)-len(line.lstrip('#')), line.lstrip('#').strip())
            i += 1
        elif line.startswith('!['):
            match = re.fullmatch(r'!\[([^]]*)\]\((.+)\)', line)
            if not match:
                raise ValueError('Invalid diagram image markup')
            yield 'image', match.groups()
            i += 1
        elif line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                row = [x.strip() for x in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', x) for x in row):
                    rows.append(row)
                i += 1
            yield 'table', rows
        else:
            para = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].startswith(('#', '|', '![')):
                para.append(lines[i].strip())
                i += 1
            yield 'paragraph', ' '.join(para)


def plain(value):
    return value.replace('**', '').replace('`', '')


def rich(value):
    value = html.escape(value).replace('`', '')
    return re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', value)


def figures(output):
    font = ImageFont.truetype('C:/Windows/Fonts/times.ttf', 24)
    specifications = {
        'Схема 1.': [('Организация', 'Программа', 'Группа', 'Площадка'),
                     ('Возраст', 'Условия допуска', 'Маршрут', 'Жилая точка')],
        'Схема 2.': [('Вопрос', 'Сбор каталога', 'Проверка данных', 'Расчёт пути'),
                     ('Проверка решения', 'Интерпретация', 'Устойчивость', 'Сравнение')],
        'Схема 3.': [('Ближайший вариант', 'Выбор мест', 'Конкуренция', 'Цепочка действий'),
                     ('Близость', 'Накопленные места', 'Предложение/спрос', 'Временные рамки')],
    }
    paths = {}
    for number, (key, rows) in enumerate(specifications.items(), 1):
        picture = RasterImage.new('RGB', (1200, 260), 'white')
        draw = ImageDraw.Draw(picture)
        positions = []
        for row_index, labels in enumerate(rows):
            for col, label in enumerate(labels):
                x, y = 5+col*300, 10+row_index*140
                draw.rounded_rectangle((x, y, x+275, y+85), radius=8, fill='#f2f5f8', outline='#34506b', width=2)
                box = draw.textbbox((0,0), label, font=font)
                draw.text((x+(275-(box[2]-box[0]))/2, y+27), label, fill='#182c40', font=font)
                positions.append((x,y))
        if number == 1:
            links = [(0,1),(1,2),(2,3),(4,5),(5,1),(7,6),(6,3)]
        elif number == 2:
            links = [(0,1),(1,2),(2,3),(3,7),(7,6),(6,5),(5,4)]
        else:
            links = [(0,4),(1,5),(2,6),(3,7)]
        import math
        for source, target in links:
            sx, sy = positions[source]
            tx, ty = positions[target]
            if sy == ty:
                start=(sx+278,sy+43) if tx>sx else (sx-3,sy+43)
                finish=(tx-3,ty+43) if tx>sx else (tx+278,ty+43)
            else:
                start=(sx+137,sy+88) if ty>sy else (sx+137,sy-3)
                finish=(tx+137,ty-3) if ty>sy else (tx+137,ty+88)
            draw.line((start,finish),fill='#34506b',width=3)
            angle=math.atan2(finish[1]-start[1],finish[0]-start[0])
            arrow=[finish]+[(finish[0]-9*math.cos(angle+d),finish[1]-9*math.sin(angle+d)) for d in [-0.5,0.5]]
            draw.polygon(arrow,fill='#34506b')
        path=output/f'figure-{number}.png'
        picture.save(path)
        paths[key]=path
    return paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stem', default='nir-1-2-draft-2026-10-26')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    diagram_paths = figures(args.output)
    text = args.input.read_text(encoding='utf-8')
    pages = [p.strip() for p in text.split('<!-- PAGE -->') if p.strip()]
    for name, file in [('TimesNR', 'times.ttf'), ('TimesNR-Bold', 'timesbd.ttf'), ('TimesNR-Italic', 'timesi.ttf')]:
        pdfmetrics.registerFont(TTFont(name, str(Path('C:/Windows/Fonts') / file)))
    pdfmetrics.registerFontFamily('TimesNR', normal='TimesNR', bold='TimesNR-Bold', italic='TimesNR-Italic')
    body = ParagraphStyle('body', fontName='TimesNR', fontSize=12.5, leading=18.0,
                          alignment=TA_JUSTIFY, spaceAfter=8, splitLongWords=True)
    heading = ParagraphStyle('heading', fontName='TimesNR-Bold', fontSize=14, leading=18,
                             spaceBefore=2, spaceAfter=12)
    cell = ParagraphStyle('cell', fontName='TimesNR', fontSize=10.5, leading=13.0)
    width, height = 210 * mm, 297 * mm
    left, right, top, bottom = 30 * mm, 15 * mm, 20 * mm, 20 * mm
    available_w, available_h = width-left-right, height-top-bottom-10
    pdf_path = args.output / (args.stem + '.pdf')
    canvas = Canvas(str(pdf_path), pagesize=(width, height))
    canvas.setTitle('НИР-1 и НИР-2: возрастная доступность внешкольных занятий — рабочий черновик')
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin, section.right_margin = Cm(3), Cm(1.5)
    section.top_margin, section.bottom_margin = Cm(2), Cm(2)
    style = document.styles['Normal']
    style.font.name, style.font.size = 'Times New Roman', Pt(12)
    style.paragraph_format.line_spacing = 1.3
    style.paragraph_format.space_after = Pt(6)
    for name in ['Heading 1', 'Heading 2']:
        document.styles[name].font.name = 'Times New Roman'
        document.styles[name].font.size = Pt(14)
    footer = section.footer.paragraphs[0]
    footer.alignment = 1
    field = OxmlElement('w:fldSimple')
    field.set(qn('w:instr'), 'PAGE')
    footer._p.append(field)
    reference_pages = sum(p.lstrip().startswith(('## Источники', '# Список')) for p in pages)
    appendix_pages = sum('<!-- LANDSCAPE -->' in p for p in pages)
    manifest = {'source': str(args.input), 'pdf_pages': len(pages),
                'body_pages': len(pages)-reference_pages-appendix_pages,
                'references_pages': reference_pages, 'appendix_pages': appendix_pages,
                'characters': len(text), 'word_count': len(text.split()),
                'format': 'A4, margins 30/15/20/20 mm; research draft, not certified institutional layout',
                'page_layout': []}
    for index, page in enumerate(pages):
        landscape = '<!-- LANDSCAPE -->' in page
        page = page.replace('<!-- LANDSCAPE -->', '').strip()
        page_width, page_height = (height, width) if landscape else (width, height)
        available_w, available_h = page_width-left-right, page_height-top-bottom-10
        canvas.setPageSize((page_width, page_height))
        if index:
            previous_landscape = '<!-- LANDSCAPE -->' in pages[index-1]
            if previous_landscape != landscape:
                section = document.add_section(WD_SECTION_START.NEW_PAGE)
                section.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
                section.page_width, section.page_height = Cm(29.7 if landscape else 21), Cm(21 if landscape else 29.7)
            else:
                document.add_page_break()
        flowables = []
        for kind, content in blocks(page):
            if kind == 'heading':
                level, content = content
                flowables.append(Paragraph(rich(content), heading))
                document.add_heading(plain(content), level=min(3, level))
            elif kind == 'image':
                caption, relative_path = content
                from urllib.parse import unquote
                path = (args.input.parent/unquote(relative_path)).resolve()
                with RasterImage.open(path) as picture:
                    iw, ih = picture.size
                factor = min(available_w/iw, (available_h-95)/ih)
                flowables.extend([Image(str(path), width=iw*factor, height=ih*factor), Spacer(1,7)])
                flowables.append(Paragraph(rich(caption), cell))
                document.add_picture(str(path), width=Cm(iw*factor/mm/10))
                document.add_paragraph(plain(caption))
            elif kind == 'paragraph':
                for prefix, path in diagram_paths.items():
                    if content.startswith(prefix):
                        flowables.extend([Image(str(path), width=available_w, height=available_w*260/1200), Spacer(1,6)])
                        document.add_picture(str(path), width=Cm(16.0))
                flowables.append(Paragraph(rich(content), body))
                document.add_paragraph(plain(content))
            else:
                count = max(len(row) for row in content)
                data = [[Paragraph(rich(value), cell) for value in row] for row in content]
                table = Table(data, colWidths=[available_w/count]*count, repeatRows=1)
                table.setStyle(TableStyle([
                    ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#999999')),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EEEEEE')),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 5),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
                flowables.extend([table, Spacer(1, 9)])
                word_table = document.add_table(rows=0, cols=count)
                word_table.style = 'Table Grid'
                for row in content:
                    cells = word_table.add_row().cells
                    for col, value in enumerate(row):
                        cells[col].text = plain(value)
        natural_height = sum(item.wrap(available_w, available_h)[1] +
                             item.getSpaceBefore() + item.getSpaceAfter() for item in flowables)
        packed = KeepInFrame(available_w, available_h, flowables, mode='shrink', hAlign='LEFT', vAlign='TOP')
        packed.canv = canvas
        _, fitted_height = packed.wrap(available_w, available_h)
        packed.drawOn(canvas, left, page_height-top-fitted_height)
        canvas.setFont('TimesNR', 9)
        canvas.setFillColor(colors.HexColor('#666666'))
        canvas.drawString(left, 11*mm, 'Рабочий черновик • 26.10.2026 • для обсуждения и переработки')
        canvas.drawRightString(page_width-right, 11*mm, str(index+1))
        canvas.showPage()
        manifest['page_layout'].append({'page': index+1, 'characters': len(page),
                                        'natural_height_pt': round(natural_height, 1),
                                        'landscape': landscape,
                                        'fit_scale': round(float(getattr(packed, '_scale', 1)), 3)})
    canvas.save()
    document.save(str(args.output / (args.stem + '.docx')))
    (args.output/'export-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k!='page_layout'}, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
