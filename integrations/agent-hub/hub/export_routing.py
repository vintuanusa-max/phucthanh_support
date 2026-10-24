"""Format decisions for admitted customer groups; never infer from group name."""
import re

def safe_folder(folder):
    return bool(folder and folder not in ('.','..') and folder == folder.strip(' .')
                and not re.search(r'[<>:"/\\|?*\x00-\x1f]',folder))

def original_jpg_allowed(comparison):
    return (comparison.get('print_process') == 'sublimation'
            and bool(comparison.get('process_sources'))
            and comparison.get('same_design') == 'proposed'
            and comparison.get('file_role') == 'artwork')
