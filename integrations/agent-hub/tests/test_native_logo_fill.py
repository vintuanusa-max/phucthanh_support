from hub.native_auto import is_excluded_candidate,region_candidates,LOGO_FILL_POLICY
parent={'id':'0.25','kind':'GroupItem','bounds':[0,150,150,0],'width_cm':15,'height_cm':15}
child={'id':'0.25.0','kind':'GroupItem','bounds':[20,130,130,20],'width_cm':11,'height_cm':11}
bg={'id':'0.25.1','kind':'PathItem','bounds':[0,150,150,0],'width_cm':15,'height_cm':15}
dim={'id':'0.30','kind':'GroupItem','name':'Manual Dimension','bounds':[0,150,150,0],'width_cm':15,'height_cm':15}
cs=[parent,child,bg,dim]
assert not is_excluded_candidate(parent,['0.30'],1000,1000,cs)
assert is_excluded_candidate(dim,['0.30'],1000,1000,cs)
scan={'artboards':[{'index':0,'bounds':[0,1000,1000,0]}],'candidates':cs}
ids=[c['id'] for c in region_candidates(scan,[{'artboard_index':0,'box':[.02,.87,.13,.98]}])]
assert '0.25' in ids and '0.25.0' in ids,ids
assert '0.30' not in ids
assert 'NGOÀI artwork' in LOGO_FILL_POLICY
print('logo-fill: complete parent retained; child alternative retained; dimension excluded')
