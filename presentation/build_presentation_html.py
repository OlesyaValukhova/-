"""Assemble a single offline HTML presentation from 20 rendered PNG slides."""
import base64, html, json, pathlib, re, sys

images = pathlib.Path(sys.argv[1] if len(sys.argv)>1 else 'html_build')
script = pathlib.Path(sys.argv[2] if len(sys.argv)>2 else 'speaker_script_v6.md')
out = pathlib.Path(sys.argv[3] if len(sys.argv)>3 else 'output/age_accessibility_v6.html')
slides = sorted(images.glob('slide-??.png'))
if len(slides) != 20: raise ValueError('Expected 20 slide images')
notes = re.findall(r'^\d+\. (.+)$',script.read_text(encoding='utf-8'),re.M)
if len(notes) != 20: raise ValueError('Expected 20 numbered notes')
data = [{'image':'data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode('ascii'), 'note':n} for p,n in zip(slides,notes)]
payload=json.dumps(data,ensure_ascii=False).replace('</','<\\/')
template='''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Возрастная доступность внешкольных занятий</title>
<style>
:root{color-scheme:light;font-family:Arial,sans-serif;color:#25313a;background:#f2f4f5}
*{box-sizing:border-box}body{margin:0}main{max-width:1450px;margin:auto;padding:16px}
.slide{background:white;box-shadow:0 2px 14px #1729321c;aspect-ratio:16/9;display:flex;align-items:center;justify-content:center}
.slide img{width:100%;height:100%;object-fit:contain}nav{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:14px}
button{border:1px solid #a4b1b8;border-radius:4px;background:white;color:#25313a;padding:9px 13px;font-size:15px;cursor:pointer}
button:focus-visible{outline:3px solid #527f9e;outline-offset:2px}button:disabled{opacity:.45;cursor:default}
#count{min-width:56px;text-align:center;font-variant-numeric:tabular-nums}#notes{background:white;line-height:1.55;padding:16px 20px;margin-top:14px;border-left:3px solid #708c78;max-width:950px}
#notes[hidden]{display:none}small{color:#61717b} @media(max-width:600px){main{padding:8px}nav{gap:8px}button{font-size:14px;padding:8px}}
</style></head><body><main><div class="slide"><img id="slide" alt=""></div>
<nav aria-label="Управление презентацией"><button id="prev" type="button">← Назад</button><span id="count" aria-live="polite"></span><button id="next" type="button">Вперёд →</button><button id="toggle" type="button" aria-expanded="false" aria-controls="notes">Показать заметки</button><small>Стрелки клавиатуры · Home / End</small></nav>
<section id="notes" hidden aria-label="Текст выступления"><strong>Текст выступления</strong><p id="note"></p><small>Черновой текст: проверьте темп вслух. Переходы ручные.</small></section>
</main><script>
const slides=__DATA__;let current=0;
const image=document.getElementById('slide'),counter=document.getElementById('count'),note=document.getElementById('note'),previous=document.getElementById('prev'),next=document.getElementById('next'),toggle=document.getElementById('toggle'),notes=document.getElementById('notes');
function show(index){current=Math.max(0,Math.min(slides.length-1,index));image.src=slides[current].image;image.alt=`Слайд ${current+1} из ${slides.length}`;counter.textContent=`${current+1} / ${slides.length}`;note.textContent=slides[current].note;previous.disabled=current===0;next.disabled=current===slides.length-1;history.replaceState(null,'',`#${current+1}`)}
previous.addEventListener('click',()=>show(current-1));next.addEventListener('click',()=>show(current+1));toggle.addEventListener('click',()=>{notes.hidden=!notes.hidden;toggle.setAttribute('aria-expanded',String(!notes.hidden));toggle.textContent=notes.hidden?'Показать заметки':'Скрыть заметки'});
document.addEventListener('keydown',e=>{if(e.altKey||e.ctrlKey||e.metaKey)return;if(e.key==='ArrowRight'||e.key==='PageDown'){e.preventDefault();show(current+1)}else if(e.key==='ArrowLeft'||e.key==='PageUp'){e.preventDefault();show(current-1)}else if(e.key==='Home'){e.preventDefault();show(0)}else if(e.key==='End'){e.preventDefault();show(slides.length-1)}});
const initial=Number(location.hash.slice(1));show(Number.isInteger(initial)&&initial>=1&&initial<=slides.length?initial-1:0);
</script></body></html>'''
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(template.replace('__DATA__',payload),encoding='utf-8')
print(f'{out}: {len(slides)} slides, {out.stat().st_size} bytes')
