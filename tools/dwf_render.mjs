import fs from 'node:fs/promises';
import path from 'node:path';
import { inflateRawSync } from 'node:zlib';
import { openDwfDocument } from 'dwf-viewer';
const [source,output]=process.argv.slice(2);
const doc=await openDwfDocument(await fs.readFile(source),{fileName:path.basename(source),inflater:{inflateRaw:async x=>new Uint8Array(inflateRawSync(x))}});
const esc=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const num=x=>{if(!Number.isFinite(x))throw Error('Invalid DWF coordinate');return String(x)};
const matrix=p=>p.matrix?` transform="matrix(${[p.matrix.a,p.matrix.b,p.matrix.c,p.matrix.d,p.matrix.e,p.matrix.f].map(num).join(' ')})"`:'';
const pathData=commands=>commands.map(c=>{
 switch(c.type){case 'M':case 'L':return c.type+[c.x,c.y].map(num).join(' ');case 'C':return 'C'+[c.x1,c.y1,c.x2,c.y2,c.x,c.y].map(num).join(' ');case 'Q':return 'Q'+[c.x1,c.y1,c.x,c.y].map(num).join(' ');case 'A':return 'A'+[c.rx,c.ry,c.rotation,Number(c.largeArc),Number(c.sweep),c.x,c.y].map(num).join(' ');case 'Z':return 'Z';default:throw Error('Unsupported DWF path');}
}).join(' ');
await fs.mkdir(output,{recursive:true});const result=[];
for(let i=0;i<doc.pageData.length;i++){
 const p=doc.pageData[i];
 if(p.kind!=='w2d-text')throw Error('Only decoded 2D W2D sheets can be exported as faithful vectors');
 const diagnostics=[...(doc.diagnostics??[]),...(p.diagnostics??[])];
 if(diagnostics.some(d=>d.level!=='info'))throw Error(JSON.stringify(diagnostics));
 const b=p.bounds??{minX:0,minY:0,maxX:p.width,maxY:p.height};
 const pad=Math.max(1,...p.primitives.map(x=>(x.lineWidth??1)/2));
 const w=b.maxX-b.minX+2*pad,h=b.maxY-b.minY+2*pad;
 if(!(w>0&&h>0))throw Error('Empty DWF page');
 let svg=`<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="${num(1200*h/w)}" viewBox="${[b.minX-pad,-b.maxY-pad,w,h].map(num).join(' ')}"><g transform="scale(1,-1)">`;
 for(const q of p.primitives){
  const style=` fill="${esc(q.fill??'none')}" stroke="${esc(q.stroke??'#000000')}" stroke-width="${num(q.lineWidth??1)}"`;
  let body='';
  if(q.type==='polyline'||q.type==='polygon')body=`<${q.type} points="${q.points.map(num).join(' ')}"${style}/>`;
  else if(q.type==='path')body=`<path d="${pathData(q.commands)}"${style}/>`;
  else if(q.type==='rect')body=`<rect x="${num(q.x)}" y="${num(q.y)}" width="${num(q.width)}" height="${num(q.height)}"${style}/>`;
  else if(q.type==='text')body=`<g transform="translate(${num(q.x)} ${num(q.y)}) scale(1,-1)"><text font-family="sans-serif" font-size="${num(q.size??12)}" fill="${esc(q.fill??q.stroke??'#000000')}" xml:space="preserve">${esc(q.text)}</text></g>`;
  else throw Error('Unsupported DWF primitive');
  svg+=`<g${matrix(q)}>${body}</g>`;
 }
 svg+='</g></svg>';const filename=path.join(output,`page-${i+1}.svg`);await fs.writeFile(filename,svg);result.push(filename);
}
if(!result.length)throw Error('DWF has no pages');await fs.writeFile(path.join(output,'pages.json'),JSON.stringify(result));
