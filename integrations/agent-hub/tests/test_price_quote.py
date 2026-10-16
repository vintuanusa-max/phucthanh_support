import pytest
from hub.price_quote import lookup,quote

def args(rule='pet_meter',q=20):
 return {'rule':rule,'width_cm':20,'height_cm':30,'quantity':q,'quantity_unit':'meter'}

def test_workbook_source_and_rates():
 x=quote(args());assert x['unit_price_vnd']==65000 and x['total_vnd']=='1300000'
 assert x['range']=='C5' and len(x['sha256'])==64
 assert lookup('in PET')['rows']

@pytest.mark.parametrize('quantity',[5,7,100,500])
def test_undefined_pet_tiers_need_staff(quantity):
 assert quote(args(q=quantity))['state']=='human_review'

def test_canavi_never_uses_generic_rate():
 assert quote(args(),'CANAVI')['state']=='human_review'

def test_missing_dimensions_are_not_inferred():
 a=args();del a['width_cm'];x=quote(a)
 assert x['state']=='missing_fields' and x['missing_fields']==['width_cm']

def test_conflicting_laser_and_pet_area_are_not_guessed():
 for rule in ['laser_perimeter']:
  a=args(rule);a['quantity_unit']='piece'
  assert quote(a)['state']=='human_review'

def test_exact_small_pet_reference():
 a=args('pet_area',50);a.update(width_cm=7,height_cm=7,quantity_unit='piece')
 assert quote(a)['total_vnd']=='50000'

@pytest.mark.parametrize('bad',[0,-1,float('nan'),float('inf')])
def test_invalid_inputs(bad):
 a=args();a['quantity']=bad
 with pytest.raises(ValueError):quote(a)


def test_owner_pet_formula_and_boundary():
 a=args('pet_area',5);a.update(width_cm=10,height_cm=10,quantity_unit='piece')
 assert quote(a)['unit_price_vnd']==2041
 a.update(width_cm=29,height_cm=40)
 assert quote(a)['state']=='quoted'
 a['width_cm']=30
 assert quote(a)['state']=='human_review'

def test_owner_corrected_laser_rectangle():
 a=args('laser_perimeter',10);a.update(width_cm=10,height_cm=15,quantity_unit='piece',shape='rectangle')
 result=quote(a)
 assert result['unit_price_vnd']==100 and result['total_vnd']=='1000'
 assert 'owner_override' in result
