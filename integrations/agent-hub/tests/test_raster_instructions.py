import pytest
from hub import raster_instructions as ins


def test_image_evidence_accepts_source_image_message_id_and_image_id():
    ctx = {
        'batch': [
            {'message_id': '8538596524780', 'sender_id': 'c', 'role': 'customer', 'text': '[Ảnh]'},
            {'message_id': '8538598556166', 'sender_id': 'c', 'role': 'customer', 'text': 'Tuấn cho in giúp q 43cai logo này nhé'},
        ]
    }
    images = {'2e38453fa934': ({}, {'message_id': '8538596524780'})}
    spec = {
        'mode': 'preserve',
        'request_message_id': '8538598556166',
        'request_quote': 'Tuấn cho in giúp q 43cai logo này nhé',
        'evidence': [
            {'kind': 'image', 'source_id': '8538596524780', 'quote': 'CAO 3 CM'},
            {'kind': 'text', 'source_id': '8538598556166', 'quote': 'Tuấn cho in giúp q 43cai logo này nhé'},
        ],
        'changes': [],
        'expected_lines': ['LOTTE', 'CHOCOLAT'],
        'preserve': ['LOTTE CHOCOLAT logo design'],
        'reason': 'Khách yêu cầu in logo theo mẫu.',
    }
    assert ins.validate(spec, ctx, images) is True
    by_image_id = dict(spec, evidence=[{'kind': 'image', 'source_id': '2e38453fa934', 'quote': 'CAO 3 CM'}])
    assert ins.validate(by_image_id, ctx, images) is True


def test_image_evidence_rejects_text_only_or_unknown_source_id():
    ctx = {
        'batch': [
            {'message_id': '8538596524780', 'sender_id': 'c', 'role': 'customer', 'text': '[Ảnh]'},
            {'message_id': '8538598556166', 'sender_id': 'c', 'role': 'customer', 'text': 'Tuấn cho in giúp q 43cai logo này nhé'},
        ]
    }
    images = {'2e38453fa934': ({}, {'message_id': '8538596524780'})}
    base = {
        'mode': 'preserve',
        'request_message_id': '8538598556166',
        'request_quote': 'Tuấn cho in giúp q 43cai logo này nhé',
        'changes': [],
        'expected_lines': ['LOTTE', 'CHOCOLAT'],
        'preserve': ['LOTTE CHOCOLAT logo design'],
        'reason': 'Khách yêu cầu in logo theo mẫu.',
    }
    for bad_sid in ('8538598556166', 'other-id'):
        bad = dict(base, evidence=[{'kind': 'image', 'source_id': bad_sid, 'quote': 'CAO 3 CM'}])
        with pytest.raises(ValueError, match='Ghi chú không thuộc ảnh nguồn'):
            ins.validate(bad, ctx, images)
