"""Owner policy: JPG approval filenames, group identity not display name."""
import re
from hub.original_jpg import filename
NEO_THREADS={'g5402324928935037742','g3427098896227768665'}
def approved_jpg_name(source_name,thread_id,panel_name='',multiple=False):
 stem=filename(source_name)
 stem=re.sub(r'^(?:(?:NEO|MNT)[_ -]+)+','',stem,flags=re.I)
 if not stem:raise ValueError('Missing original filename')
 if multiple:stem+='_'+filename(panel_name+'.jpg')
 return ('NEO_' if thread_id in NEO_THREADS else 'MNT_')+stem+'.jpg'
