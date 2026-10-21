"""Bound image context at a new image after a quantity-bearing text message.

These are candidate groups, not inferred image/quantity assignments. The model
must still resolve colour, unit, corrections and design intent within each group.
"""
import re


def image_groups(messages):
    groups, current = [], []
    has_image = has_quantity = False
    for index, message in enumerate(messages, 1):
        quote = message.get('quoted_image') or {}
        repeats_current = quote.get('resolved') and any(m.get('message_id') == quote.get('message_id') for _, m in current)
        image = bool(message.get('images')) and not repeats_current
        if image and has_image and has_quantity:
            groups.append(current)
            current = []
            has_image = has_quantity = False
        current.append((index, message))
        has_image |= image
        if has_image and re.search(r'\d', message.get('text', '')):
            has_quantity = True
    if current:
        groups.append(current)
    return groups


def validate_group_quantity(orders, messages):
    from decimal import Decimal
    text = '\n'.join(m.get('text', '') for m in messages)
    text = re.sub(r'(?<=[^\d\s])\.(?=\d)', ' ', text)
    numbers = {Decimal(v.replace('.', '') if re.fullmatch(r'\d{1,3}(?:\.\d{3})+', v)
                       else v.replace(',', '.'))
               for v in re.findall(r'(?<![\w.])\d{1,3}(?:\.\d{3})+|(?<![\w.])\d+(?:,\d+)?', text)}
    for order in orders:
        if order.so_luong not in numbers:
            raise ValueError('Quantity is not explicit in this image group; needs review')
