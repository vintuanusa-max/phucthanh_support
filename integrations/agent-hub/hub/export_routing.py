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


JPG_GROUPS = {'g5402324928935037742', 'g3427098896227768665'}
CANAVI_GROUPS = {'g1790239230897256718', 'g2671966061008128194'}

def routing_policy(brief):
    thread = brief.get('thread_id')
    if thread in JPG_GROUPS:
        return 'jpg_group'
    if thread in CANAVI_GROUPS:
        return 'slip_process'
    return 'default_pet'

def apply_routing(value, brief):
    policy = routing_policy(brief)
    value = dict(value)
    value['routing_policy'] = policy
    if policy == 'slip_process':
        return value
    if policy == 'jpg_group':
        value.update(print_process='sublimation', process_sources=['owner:group_jpg'])
        return value
    basis = value.get('process_basis')
    has_cap_reason = basis not in ('cap_logo', 'cap_pattern') or bool(value.get('process_reason'))
    if basis in ('cap_logo','cap_pattern','explicit') and value.get('process_sources') and has_cap_reason and value.get('print_process') in ('pet','sublimation'):
        if value['process_basis']=='cap_logo':value['print_process']='pet'
        elif value['process_basis']=='cap_pattern':value['print_process']='sublimation'
        value['routing_policy']='source_process_evidence'
        return value
    # Only the customer text of this source-bound brief can override default PET.
    sources = {s['message_id']:s for s in brief.get('sources', [])}
    mid = value.get('sublimation_message_id', '')
    quote = value.get('sublimation_quote', '').strip()
    src = sources.get(mid, {})
    explicit = (src.get('role') == 'customer' and quote and quote in src.get('text', '')
                and value.get('customer_requests_sublimation') is True)
    if explicit:
        value.update(print_process='sublimation', process_sources=['message:'+mid])
    else:
        value.update(print_process='pet', process_sources=['owner:default_pet'])
    return value
