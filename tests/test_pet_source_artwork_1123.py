import ast,math,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def funcs(path,names,env):
 tree=ast.parse((ROOT/path).read_text(encoding='utf-8-sig'))
 exec(compile(ast.Module(body=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in names],type_ignores=[]),str(path),'exec'),env)
 return env
class PetSourceTests(unittest.TestCase):
 def setUp(self):
  self.env=funcs(Path('integrations/system-monitor/artwork-worker/native_local.py'),{'reimport_pdf_pages','selected_source'},{'Path':Path})
 def test_old_candidates_keep_source(self):
  for name in ('source.ai','source.pdf'):
   self.assertEqual(self.env['selected_source'](Path(name),'.',[{'id':'0.1'}]),Path(name))
 def test_mixed_representations_rejected(self):
  with self.assertRaises(ValueError):self.env['selected_source'](Path('source.pdf'),'.',[{}, {'pdf_page_reimport':True}])
 def test_ai_never_reimported(self):
  with self.assertRaises(ValueError):self.env['reimport_pdf_pages'](Path('source.ai'),'.')
 def test_pdf_large_canvas_preserves_page(self):
  import pymupdf as fitz
  with tempfile.TemporaryDirectory() as td:
   src=Path(td)/'source.pdf';d=fitz.open();p=d.new_page(width=120,height=80);p.draw_rect(fitz.Rect(10,10,80,60),color=(1,0,0),fill=(1,1,1));d.xref_set_key(p.xref,'UserUnit','10');d.save(src);d.close()
   out=self.env['reimport_pdf_pages'](src,td)
   with fitz.open(src) as a,fitz.open(out) as b:
    self.assertEqual(a[0].rect,b[0].rect)
    self.assertEqual(a[0].get_pixmap().samples,b[0].get_pixmap().samples)
 def test_numeric_source_stack(self):
  env=funcs(Path('integrations/agent-hub/hub/native_auto.py'),{'validate'},{'math':math,'SIDES':['front'],'merge_exact_artwork':lambda v:v})
  ids=['0.10','0.2','0.3'];c=[{'id':i,'bounds':[0,20,20,0],'live_text_count':0} for i in ids]
  f={'candidate_ids':ids,'side':'front','dimension_refs':[],'basis':'source_layout','width_cm':0,'height_cm':0}
  out=env['validate']({'is_pet':True,'same_design':True,'issues':[],'faces':[f]},{'candidates':c},[])
  self.assertEqual([x['id'] for x in out[0]['candidates']],['0.2','0.3','0.10'])
if __name__=='__main__':unittest.main()
