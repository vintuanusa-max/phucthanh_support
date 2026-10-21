from hub.bag_design import BagFact,bag_plan

def facts(**values):
    return [BagFact(field=k,value=str(v),source_message_ids=['m'],basis='text',evidence='source') for k,v in values.items()]

def test_single_face_uses_full_explicit_fabric_and_adds_mouth_once():
    p=bag_plan(facts(fabric_height_cm=47.5,fabric_width_cm=46,fabric_scope='single_face',print_faces=1,top_offset_finished_cm=4,mouth_allowance_cm=5,top_offset_reference='finished_mouth'))
    assert p['proposed_geometry']['artboard_candidate_cm']['height']==47.5
    assert p['proposed_geometry']['top_offset_raw_cm']==9
    assert not p['ready_for_execution']

def test_print_one_face_does_not_prove_split_and_edge_offset_not_added():
    p=bag_plan(facts(fabric_height_cm=90,fabric_width_cm=46,fabric_scope='two_faces',print_faces=1,top_offset_finished_cm=9,mouth_allowance_cm=5,top_offset_reference='raw_fabric_edge'))
    assert 'artboard_candidate_cm' not in p['proposed_geometry']
    assert p['proposed_geometry']['top_offset_raw_cm']==9

def test_split_requires_explicit_axis_and_handles_require_code():
    p=bag_plan(facts(fabric_height_cm=90,fabric_width_cm=46,fabric_scope='two_faces',split_confirmed='true',split_axis='height',handle_print='true'))
    assert p['proposed_geometry']['artboard_candidate_cm']['height']==45
    assert p['proposed_geometry']['handle_artboard_width_cm']==160
    assert any('Mã mẫu quai' in x for x in p['missing_or_review'])

def test_conflicting_values_do_not_generate_geometry():
    f=facts(fabric_height_cm=90,fabric_width_cm=46,fabric_scope='single_face')+facts(fabric_height_cm=80)
    assert not bag_plan(f)['proposed_geometry']

def test_each_object_keeps_its_own_anchor_and_only_known_top_converts():
    from hub.bag_design import BagPanel,BagPlacement
    def place(**kwargs):return BagPlacement(source_message_ids=['m'],evidence='maket',basis='image',**kwargs)
    panel=BagPanel(part='front',print_required=True,source_message_ids=['m'],placements=[
        place(object_label='logo',edge='top',reference='finished_mouth',offset_cm=4,mouth_allowance_cm=5),
        place(object_label='logo',edge='right',reference='finished_edge',offset_cm=2.3),
        place(object_label='text',edge='left',reference='finished_edge',offset_cm=2)])
    p=bag_plan([], [panel]);placements=p['panels'][0]['placements']
    assert [x['proposed_raw_offset_cm'] for x in placements]==[9,None,None]
    assert all(not x['verified'] for x in placements)
