"""Owner policy: JPG approval filenames, group identity not display name."""
from hub.output_names import NEO_THREADS, short_output_stem


def approved_jpg_name(source_name, thread_id, panel_name='', multiple=False):
    stem = short_output_stem(source_name, max_len=32)
    if multiple:
        panel_short = short_output_stem(panel_name + '.jpg', max_len=16)
        stem = short_output_stem(f'{stem}_{panel_short}', max_len=40)
    return ('NEO_' if thread_id in NEO_THREADS else 'MNT_') + stem + '.jpg'
