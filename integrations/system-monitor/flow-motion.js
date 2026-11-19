/* Execution diagram: read-only live data and isolated browser replay. */
window.attachFlowMotion = function({box,graph,svg,nodes,edges,fit}){
 const toolbar=document.createElement('section');toolbar.className='flow-live-tools';
 graph.parentElement.before(toolbar);
 const make=(tag,text,cls)=>{const n=document.createElement(tag);n.textContent=text;if(cls)n.className=cls;return n};
 const mode=make('strong','Trực tiếp','fm-mode'), summary=make('span','Đang đọc thống kê…'), controls=make('div','','fm-controls');
 const replay=make('button','Phát lại hôm nay'),demo=make('button','Mô phỏng các nhánh'),pause=make('button','Tạm dừng'),back=make('button','Về trực tiếp');
 controls.append(replay,demo,pause,back);toolbar.append(mode,summary,controls);
 const note=make('small','Số trong ô = số hồ sơ/lượt theo ngày của bước (UTC+7), không cộng dồn giữa các bước. — = chưa có bộ đếm.');toolbar.append(note);
 const badge={};for(const [id] of nodes){const b=document.getElementById('fg-'+id);badge[id]=make('span','—','fm-badge');b.append(badge[id]);}
 const paths=[...svg.querySelectorAll('path[data-edge]')];
 // Multiple upstream routes converge here. Animate only the receiving end while exporting.
 const entries={};for(const [id] of nodes){const n=nodes.find(x=>x[0]===id),p=document.createElementNS(svg.namespaceURI,'path');
 p.setAttribute('d','M '+(n[3]-20)+' '+(n[4]+34)+' h 18');p.setAttribute('fill','none');p.style.display='none';p.setAttribute('marker-end','url(#fg-arrow)');svg.append(p);entries[id]=p;}

 // A replay mark under the receiving step remains legible even for repeated
 // intake events, where there is no preceding edge to animate.
 const replayMark=document.createElementNS(svg.namespaceURI,'path');
 replayMark.id='fg-replay-underline';replayMark.setAttribute('fill','none');
 replayMark.setAttribute('marker-end','url(#fg-arrow)');svg.append(replayMark);
 let live=null,kind='live',events=[],pos=0,counts={},active=[],last='',paused=false,playing=null,busy=false;
 const name=id=>nodes.find(n=>n[0]===id)?.[1]||id;
 const runningEdges={agent:'source:agent',redraw:'source:redraw',redraw_delivery:'redraw:redraw_delivery',psd:'match:psd'};
 function paint(){
  const simulated=kind!=='live', values=simulated?counts:(live?.counts||{});
  graph.classList.toggle('fm-sim',simulated);toolbar.classList.toggle('fm-sim',simulated);
  const fresh=live && Date.now()/1000-live.asof<35;
  const ids=simulated?active:(fresh?Object.keys(live.active).filter(k=>live.active[k]>0):[]);
  for(const [id] of nodes){const value=values[id];badge[id].textContent=value==null?'—':String(simulated?value:value.n);
   badge[id].title=simulated?'Số của phiên phát':value?.unit||'Chưa có dữ liệu theo ngày';
   const b=badge[id].parentElement;b.classList.toggle('fm-working',ids.includes(id));b.setAttribute('aria-label',name(id)+' · '+badge[id].textContent+(ids.includes(id)?' · đang xử lý':''));
  }
  const markNode=kind==='history'&&active.length?document.getElementById('fg-'+active[0]):null;
  replayMark.style.display=markNode?'':'none';
  if(markNode){
   const y=markNode.offsetTop+markNode.offsetHeight+5;
   replayMark.setAttribute('d','M '+(markNode.offsetLeft+5)+' '+y+' h '+(markNode.offsetWidth-12));
   replayMark.style.setProperty('stroke','#b87514');
   replayMark.setAttribute('stroke-width','3');replayMark.setAttribute('stroke-dasharray','10 6');
  }
  replayMark.classList.toggle('fm-moving',Boolean(markNode)&&!paused);
  for(const id in entries){const enabled=ids.includes(id)&&(kind==='history'?(!paused&&!last):kind==='live'&&['jpg','pet'].includes(id));entries[id].style.display=enabled?'':'none';entries[id].classList.toggle('fm-moving',enabled)}
  for(const id of ['flow-detail','flow-focus','fg-tabs','fg-scope']){const section=document.getElementById(id);if(section)section.hidden=simulated;}
  for(const p of paths)p.classList.toggle('fm-moving',simulated?(!paused&&p.dataset.edge===last):ids.some(id=>runningEdges[id]===p.dataset.edge));
  pause.hidden=back.hidden=!simulated;pause.textContent=paused?'Tiếp tục':'Tạm dừng';pause.disabled=pos>=events.length;
  mode.textContent=kind==='live'?'Trực tiếp':kind==='history'?'Phát lại · lịch sử hôm nay':'Mô phỏng · dữ liệu giả';
  if(!simulated)summary.textContent=live?(live.day+' · '+(fresh?(ids.length?'Đang xử lý: '+ids.map(name).join(', '):'Chưa ghi nhận bước đang chạy'):'Mất cập nhật · đang hiển thị số gần nhất')):'Chưa đọc được dữ liệu';
  else summary.textContent=(live?.day||'Hôm nay')+' · '+pos+'/'+events.length+' · '+(pos>=events.length?'Đã phát xong':paused?'Đang tạm dừng':active.map(name).join(' · '));
 }
 function stop(){clearInterval(playing);playing=null}
 function tick(){if(paused)return;if(pos>=events.length){active=[];last='';stop();paint();return}
  const [from,to]=events[pos++];counts[to]=(counts[to]||0)+1;active=[to];last=from?from+':'+to:'';paint();}
 function start(k,seq){stop();kind=k;events=seq;pos=0;counts=Object.fromEntries(nodes.map(n=>[n[0],0]));active=[];last='';paused=false;paint();tick();playing=setInterval(tick,k==='history'?700:650)}
 replay.onclick=()=>{if(live)start('history',[...live.events].sort((a,b)=>a[0]-b[0]).map(([,to])=>{
  const incoming=edges.filter(([,target])=>target===to);
  // History records the receiving step. Show its entry arrow if the upstream branch is unknown.
  return [incoming.length===1?incoming[0][0]:null,to];
 }))};
 demo.onclick=()=>{const routes=[['source','redraw','redraw_delivery'],['source','agent','erp'],['source','agent','no_action'],['source','agent','vision','match','pet','preview'],['source','agent','vision','pet_restore','pet','preview'],['source','agent','vision','match','psd','preview'],['source','agent','approve','send'],...['single_face','separate_faces','joined_faces','solid_meter','pattern_meter','ready_layout','unknown'].map(k=>['source','jpg',k,...(k==='unknown'?[]:['preview'])])];
  start('demo',routes.flatMap(r=>r.map((id,i)=>[i?r[i-1]:null,id])))};
 pause.onclick=()=>{paused=!paused;paint()};back.onclick=()=>{stop();kind='live';paint();poll()};
 const visible=()=>!box.hidden&&!document.hidden&&graph.getClientRects().length>0;
 async function poll(){if(!visible()||busy||kind!=='live')return;busy=true;try{const r=await fetch('/api/flow-today',{cache:'no-store'});if(!r.ok)throw Error();live=await r.json()}catch(e){}finally{busy=false;replay.disabled=!live;paint()}}
 new MutationObserver(()=>{if(visible())poll();else if(kind!=='live'){paused=true;paint()}}).observe(box,{attributes:true,attributeFilter:['hidden']});
 document.addEventListener('visibilitychange',poll);document.getElementById('fg-refresh').addEventListener('click',poll);setInterval(poll,12000);poll();paint();
};
