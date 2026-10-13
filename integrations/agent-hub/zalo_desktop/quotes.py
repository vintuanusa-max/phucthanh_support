"""Resolve quoted photos by source identifiers, never by proximity or quoted URLs."""
import json

from .codec import decode_field


def attach_quote(message, row, db, secret, enabled):
    raw = row['quote'] if 'quote' in row.keys() else None
    if not raw:
        return
    try:
        quote = json.loads(raw)
        if not isinstance(quote, dict):
            raise ValueError('invalid_quote')
        if quote.get('cliMsgType') != 32:
            return
        mid = str(quote.get('globalMsgId') or '')
        message['quoted_image'] = dict(message_id=mid, sender_id=str(quote.get('ownerId') or ''),
            client_message_id=str(quote.get('cliMsgId') or ''), sender='', timestamp=0, resolved=False)
        if not enabled or not mid.isdigit() or db is None:
            raise ValueError('unavailable_quote')
        original = db.execute('SELECT * FROM message WHERE msgId=?', (mid,)).fetchone()
        if original is None or original['msgType'] != 2 or original['ev'] != 0:
            raise ValueError('missing_photo')
        stamp = int(original['serverTime'] or original['sendDttm'] or 0)
        if (str(original['toUid']) != message['thread_id']
            or str(original['fromUid']) != str(quote.get('ownerId'))
            or str(original['cliMsgId']) != str(quote.get('cliMsgId'))
            or stamp != int(quote.get('ts') or 0)
            or stamp <= 0 or stamp > message['timestamp'] * 1000
            or message.get('_asset_requests') or message.get('images')):
            raise ValueError('quote_identity_mismatch_or_multiple_images')
        metadata = decode_field(original['message'], secret, original['ev'])
        url = metadata['oriUrl']
        if not isinstance(url, str) or not url.startswith('https://'):
            raise ValueError('missing_original_url')
        message['quoted_image'].update(sender=str(original['dName'] or ''), timestamp=stamp/1000, resolved=True)
        message['_asset_requests'] = [{'kind':'image', 'url':url, 'name':''}]
    except (ValueError, TypeError, KeyError):
        message['attachments'].append('zalo-desktop:quoted-image-unresolved')
