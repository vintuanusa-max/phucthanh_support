"""Native-only duplication/cropping; original document artwork stays unchanged."""
JSX = r'''
function specialPart(p,layer,x,y,w,h,map){
 var template=layer.groupItems.add(),removeItems=[];
 var specs=p.objects.slice(0);specs.sort(function(a,b){var aa=a.id.split('.'),bb=b.id.split('.');for(var j=0;j<Math.min(aa.length,bb.length);j++){if(Number(aa[j])!==Number(bb[j]))return Number(aa[j])-Number(bb[j]);}return aa.length-bb.length;});
 for(var k=0;k<specs.length;k++){
  var spec=specs[k],dup=find(spec).duplicate(template,ElementPlacement.PLACEATEND);
  for(var e=0;e<p.exclude_ids.length;e++)if(p.exclude_ids[e].indexOf(spec.id+'.')===0){
   var tail=p.exclude_ids[e].substring(spec.id.length+1).split('.'),q=dup;
   for(var a=0;a<tail.length;a++)q=children(q)[Number(tail[a])];
   if(!q)fail('Annotation ID changed');removeItems.push(q);
  }
 }
 // Rotation/crop frame uses the complete selected source union, before notes are hidden.
 if(p.rotation)template.rotate(p.rotation);
 var frame=groupBounds(template),fw=frame[2]-frame[0],fh=frame[1]-frame[3],crop=p.crop_box;
 var tw=fw*(crop[2]-crop[0]),th=fh*(crop[3]-crop[1]);
 if(Math.abs(tw/cm-p.tile_cm[0])>.03||Math.abs(th/cm-p.tile_cm[1])>.03)fail('Artwork crop/native dimensions changed');
 for(var e=0;e<removeItems.length;e++)removeItems[e].hidden=true;
 var tile=layer.groupItems.add();template.move(tile,ElementPlacement.PLACEATEND);
 var mask=tile.pathItems.rectangle(frame[1]-fh*crop[1],frame[0]+fw*crop[0],tw,th);
 mask.stroked=false;mask.filled=false;mask.clipping=true;tile.clipped=true;tile.name='SOURCE_REPEAT_CELL';
 var tileBounds=bounds(tile);tile.translate(x-tileBounds[0],y-tileBounds[1]);
 if(p.special_kind==='pattern_meter'){
  // Copies may exceed 160 cm. The output artboard clips them, without stretching.
  var count=Math.ceil(w*cm/tw);if(count>2000)fail('Repeat cell count exceeds plan');
  for(var ix=1;ix<count;ix++){var next=tile.duplicate(layer,ElementPlacement.PLACEATEND);next.translate(ix*tw,0);}
 }else if(p.special_kind!=='ready_layout')fail('Unknown special JPG type');
}
'''
