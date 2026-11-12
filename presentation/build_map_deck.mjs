import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';

const [source='inputs/itmo_age_accessibility_white_v2.pptx', maps='output', destination='output/age_accessibility_maps_draft_v4.pptx']=process.argv.slice(2);
const p=await PresentationFile.importPptx(await FileBlob.load(source));
const original=p.slides.items.map(s=>'sl/'+s.id);
for(let i=0;i<p.slides.items.length;i++) {
  const s=p.slides.items[i];
  const counter=s.shapes.items.find(x=>/^\d\d \/ 20$/.test(x.text?.toString()||''));
  if(counter) counter.text.replace(counter.text.toString(),`${String(i+1+(i>=13?2:0)).padStart(2,'0')} / 22`);
  if(s.speakerNotes.text) s.speakerNotes.text=s.speakerNotes.text.replace('Географические карты не воспроизведены, так как PNG/GPKG недоступны через подключение.','');
}
const additions=[];
for(const [id,label] of [['81','Программирование'],['38','Изобразительное искусство']]) {
  const slide=p.slides.add(); slide.background.fill='#FFFFFF';
  const b=await fs.readFile(`${maps}/blocks_state_${id}.png`);
  slide.images.add({blob:b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength),contentType:'image/png',alt:`${label}: преобладающее состояние доступности для 7 и 13 лет по кварталам`,fit:'contain',position:{left:0,top:0,width:1280,height:720}});
  slide.speakerNotes.text='Источник: age_profiles_blocks.gpkg, слой profiles; сценарий B1, 30 минут пешком. Карта показывает наиболее частое состояние среди жилых точек внутри квартала. Кварталы с менее чем тремя точками с сетевым покрытием и равенство наиболее частых состояний выделены отдельно. Данные характеризуют опубликованные координаты Navigator, а не места, запись, фактические поездки или самостоятельность детей.';
  additions.push('sl/'+slide.id);
}
p.slides.reorder([...original.slice(0,13),...additions,...original.slice(13)]);
await (await PresentationFile.exportPptx(p)).save(destination);
for(let i=13;i<15;i++) await fs.writeFile(`output/slide_${i+1}.png`,new Uint8Array(await (await p.slides.items[i].export({format:'png',scale:1})).arrayBuffer()));
