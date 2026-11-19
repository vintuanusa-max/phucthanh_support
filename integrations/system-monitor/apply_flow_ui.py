from pathlib import Path
p=Path('dispatch.html');s=p.read_text(encoding='utf8')
css="""<style>.flow-live-tools{display:flex;align-items:center;flex-wrap:wrap;gap:12px;padding:14px 16px;background:#eff8f5;border:1px solid #b5d6ca;border-radius:12px;margin-top:12px;color:#173e37}.flow-live-tools small{flex-basis:100%;color:#51666a}.fm-controls{display:flex;gap:5px;margin-left:auto}.flow-live-tools.fm-sim{background:#fff5df;border-color:#e0bb79}.flow-node{padding-right:34px!important}.fm-badge{position:absolute;right:5px;top:6px;padding:2px 5px;border-radius:6px;background:#edf1f5;color:#344b60;font:bold 12px system-ui;min-width:15px}.flow-node.fm-working{border-color:#11805c!important;box-shadow:0 0 0 3px #12856130}.fm-working .fm-badge{background:#126b4e;color:white}.fm-sim .fm-working{border-color:#bb7918!important}.fm-moving{stroke:#07805d!important;stroke-width:3!important;stroke-dasharray:10 6;animation:flowDash .75s linear infinite}.fm-sim .fm-moving{stroke:#b87514!important}@keyframes flowDash{to{stroke-dashoffset:-32}}@media(prefers-reduced-motion:reduce){.fm-moving{animation:none}}</style><script src="/flow-motion.js"></script>"""
assert 'attachFlowMotion' not in s
a=s.index('<script');s=s[:a]+css+s[a:]
a=s.index("const graph=document.getElementById('execgraph')")
s=s[:a]+"""const pos={source:[20,305],agent:[245,305],vision:[470,260],match:[695,265],redraw:[695,15],redraw_delivery:[920,15],erp:[695,135],no_action:[470,430],pet_restore:[695,500],pet:[920,510],psd:[920,605],jpg:[920,270],approve:[470,710],send:[695,710],preview:[1390,410]};
['single_face','separate_faces','joined_faces','solid_meter','pattern_meter','ready_layout','unknown'].forEach((k,i)=>pos[k]=[1150,95+i*100]);
for(const n of nodes){[n[3],n[4]]=pos[n[0]]}
"""+s[a:]
s=s.replace("graph.style.width='1500px'","graph.style.width='1590px';graph.style.height='805px'").replace("svg.setAttribute('width','1500')","svg.setAttribute('width','1590')").replace("svg.setAttribute('height','690')","svg.setAttribute('height','805')").replace("clientWidth||1500)/1500","clientWidth||1590)/1590").replace("p.setAttribute('fill','none');p.setAttribute('stroke','#8fa4bb')","p.dataset.edge=a+':'+b;p.setAttribute('fill','none');p.setAttribute('stroke','#8fa4bb')")
s=s.replace('L 205 6 L 860 6 L 860','L 205 49 L 680 49 L 680').replace('L 205 390 L 850 390 L 850','L 205 115 L 900 115 L 900').replace("directLabel.setAttribute('x','430')","directLabel.setAttribute('x','300')").replace("directLabel.setAttribute('y','412')","directLabel.setAttribute('y','106')")
s=s.replace('Chỉ cập nhật khi mở tab hoặc bấm Làm mới; không tự tải lại khi đang xem.','Bộ đếm toàn hệ thống tự cập nhật khi đang xem.')
a="const tabs={chat:'Chatwoot Hub'";assert s.count(a)==1
s=s.replace(a,"window.attachFlowMotion({box,graph,svg,nodes,edges,fit});\n"+a);p.write_text(s,encoding='utf8')
