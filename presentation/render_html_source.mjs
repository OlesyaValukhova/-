import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const input=process.argv[2]||'output/age_accessibility_maps_v6_checked.pptx';
const dir=process.argv[3]||'html_build';
await fs.mkdir(dir,{recursive:true});
const p=await PresentationFile.importPptx(await FileBlob.load(input));
if(p.slides.items.length!==20) throw Error('Expected exactly 20 slides');
for(let i=0;i<p.slides.items.length;i++){
  const blob=await p.slides.items[i].export({format:'png',scale:1});
  await fs.writeFile(`${dir}/slide-${String(i+1).padStart(2,'0')}.png`,new Uint8Array(await blob.arrayBuffer()));
}
console.log(`Rendered ${p.slides.items.length} slides`);
