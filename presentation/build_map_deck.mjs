import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';

const [source='inputs/itmo_age_accessibility_white_v2.pptx', maps='output', destination='output/age_accessibility_maps_draft_v6.pptx']=process.argv.slice(2);
const p=await PresentationFile.importPptx(await FileBlob.load(source));
const original=p.slides.items.map(s=>'sl/'+s.id);
const replacedSlideNotes = String(p.slides.items[15].speakerNotes.text || '').replace('Географические карты не воспроизведены, так как PNG/GPKG недоступны через подключение.','');
for(let i=0;i<p.slides.items.length;i++) {
  const s=p.slides.items[i];
  if(s.speakerNotes.text) s.speakerNotes.text=s.speakerNotes.text.replace('Географические карты не воспроизведены, так как PNG/GPKG недоступны через подключение.','');
}
const additions=[];
for(const [id,label] of [['81','Программирование'],['38','Изобразительное искусство']]) {
  const slide=p.slides.add(); slide.background.fill='#FFFFFF';
  const b=await fs.readFile(`${maps}/blocks_state_${id}.png`);
  slide.images.add({blob:b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength),contentType:'image/png',alt:`${label}: преобладающее состояние доступности для 7 и 13 лет по кварталам`,fit:'contain',position:{left:0,top:0,width:1280,height:720}});
  slide.speakerNotes.text='Источник: age_profiles_blocks.gpkg, слой profiles; сценарий B1, 30 минут пешком. Карта показывает наиболее частое состояние среди жилых точек внутри квартала. Кварталы с менее чем тремя точками с сетевым покрытием и равенство наиболее частых состояний выделены отдельно. Данные характеризуют опубликованные координаты Navigator, а не места, запись, фактические поездки или самостоятельность детей.\n'+(id==='81'?'Доли подключённых жилых точек: оба возраста 43,65%; только 7 лет 2,76%; только 13 лет 19,59%; ни один 34,00%.':'Доли подключённых жилых точек: оба возраста 80,05%; только 7 лет 5,35%; только 13 лет 0,93%; ни один 13,66%.');
  additions.push('sl/'+slide.id);
}
// Replace the generic block-profile slide with its quantitative geographic view.
const delta=p.slides.add(); delta.background.fill='#FFFFFF';
const db=await fs.readFile(`${maps}/blocks_delta_81.png`);
delta.images.add({blob:db.buffer.slice(db.byteOffset,db.byteOffset+db.byteLength),contentType:'image/png',alt:'Медиана парной разницы числа достижимых координат программирования N13 минус N7',fit:'contain',position:{left:0,top:0,width:1280,height:720}});
delta.speakerNotes.text=replacedSlideNotes+'\nКарта: медиана по жилым точкам квартала парной разницы N13 − N7, а не разность квартальных медиан. N — число уникальных опубликованных координат, достижимых за 30 минут пешком. Менее трёх точек с сетевым покрытием выделены отдельно. Исходный слой: age_profiles_blocks.gpkg, profiles, B1.';
p.delete([original[8],original[13],original[15]]);
p.slides.reorder([...original.slice(0,8),...original.slice(9,13),...additions,original[14],'sl/'+delta.id,...original.slice(16)]);
for(let i=0;i<p.slides.items.length;i++) {
  const slide=p.slides.items[i], text=`${String(i+1).padStart(2,'0')} / 20`;
  const counter=slide.shapes.items.find(x=>/^\d\d \/ 20$/.test(x.text?.toString()||''));
  if(counter) counter.text.replace(counter.text.toString(),text);
  else {
    const c=slide.shapes.add({name:'slide-number',geometry:'textbox',position:{left:1170,top:30,width:80,height:25},fill:'none',line:{fill:'none',width:0}});
    c.text=text; c.text.style={fontFamily:'Arial',fontSize:'9pt',color:'#65737B'};
  }
}
await (await PresentationFile.exportPptx(p)).save(destination);
for(const i of [7,8,11,12,13,14,15,16]) await fs.writeFile(`output/v6_slide_${i+1}.png`,new Uint8Array(await (await p.slides.items[i].export({format:'png',scale:1})).arrayBuffer()));
