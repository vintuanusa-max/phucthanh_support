import base64
import io
import unittest

from PIL import Image, ImageDraw

from hub.native_selection import opaque_native_source
from hub.pet_customer_dimensions import apply_adjustment_math, collect_customer_messages


def _png_b64(im):
    buf = io.BytesIO()
    im.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


class PetCustomerDimensionsTests(unittest.TestCase):
    def test_collect_customer_messages_ignores_staff_and_markers(self):
        brief = {
            'sources': [
                {'message_id': '100', 'origin': 'staff', 'direction': 'incoming', 'text': 'mạc ngang 9 cm'},
                {'message_id': '101', 'origin': 'customer', 'direction': 'incoming', 'text': '[File Zalo: MK.pdf]'},
                {'message_id': '102', 'origin': 'customer', 'direction': 'incoming', 'text': 'mạc ngang 7 cm'},
                {'message_id': '103', 'origin': 'customer', 'direction': 'incoming', 'text': 'đuôi ngang 7 cm'},
                {'message_id': '104', 'origin': 'customer', 'direction': 'outgoing', 'text': 'bỏ qua'},
            ]
        }
        msgs = collect_customer_messages(brief)
        self.assertEqual(
            msgs,
            [
                {'ref': 'message:102', 'message_id': '102', 'text': 'mạc ngang 7 cm'},
                {'ref': 'message:103', 'message_id': '103', 'text': 'đuôi ngang 7 cm'},
            ],
        )

    def test_kim_oanh_width_override_preserves_aspect_ratio(self):
        faces = [
            {'side': 'front', 'basis': 'source_layout', 'width_cm': 7.9226, 'height_cm': 9.0761, 'dimension_refs': ['file_page:1']},
            {'side': 'back', 'basis': 'source_layout', 'width_cm': 4.2932, 'height_cm': 1.4393, 'dimension_refs': ['file_page:1']},
        ]
        ai_result = {
            'adjustments': [
                {
                    'side': 'front',
                    'action': 'resize',
                    'axis': 'width',
                    'width_cm': 7.0,
                    'height_cm': 0,
                    'dimension_refs': ['message:8535607813389'],
                    'reason': 'Khách ghi mạc ngang 7 cm',
                },
                {
                    'side': 'back',
                    'action': 'resize',
                    'axis': 'width',
                    'width_cm': 7.0,
                    'height_cm': 0,
                    'dimension_refs': ['message:8535608714278'],
                    'reason': 'Khách ghi đuôi ngang 7 cm',
                },
            ],
            'unmatched_requests': [],
        }
        updated, notes, warnings = apply_adjustment_math(faces, ai_result, ['message:8535607813389', 'message:8535608714278'])
        self.assertEqual(warnings, [])
        self.assertEqual(len(notes), 2)
        self.assertEqual(updated[0]['basis'], 'explicit')
        self.assertAlmostEqual(updated[0]['width_cm'], 7.0, places=3)
        self.assertAlmostEqual(updated[0]['height_cm'], 7.0 * 9.0761 / 7.9226, places=3)
        self.assertEqual(updated[1]['basis'], 'explicit')
        self.assertAlmostEqual(updated[1]['width_cm'], 7.0, places=3)
        self.assertAlmostEqual(updated[1]['height_cm'], 7.0 * 1.4393 / 4.2932, places=3)

    def test_height_axis_and_keep_source(self):
        faces = [
            {'side': 'front', 'basis': 'source_layout', 'width_cm': 10.0, 'height_cm': 5.0},
            {'side': 'left', 'basis': 'source_layout', 'width_cm': 4.0, 'height_cm': 2.0},
        ]
        ai_result = {
            'adjustments': [
                {'side': 'front', 'action': 'resize', 'axis': 'height', 'width_cm': 0, 'height_cm': 6.5, 'dimension_refs': ['message:1'], 'reason': 'cao 6.5cm'},
                {'side': 'left', 'action': 'keep_source', 'axis': 'none', 'width_cm': 0, 'height_cm': 0, 'dimension_refs': [], 'reason': ''},
            ],
            'unmatched_requests': [],
        }
        updated, notes, warnings = apply_adjustment_math(faces, ai_result, ['message:1'])
        self.assertEqual(warnings, [])
        self.assertEqual(updated[0]['basis'], 'explicit')
        self.assertAlmostEqual(updated[0]['width_cm'], 13.0, places=3)
        self.assertAlmostEqual(updated[0]['height_cm'], 6.5, places=3)
        self.assertEqual(updated[1]['basis'], 'source_layout')
        self.assertAlmostEqual(updated[1]['width_cm'], 4.0, places=3)

    def test_rejects_ungrounded_ref_or_distorted_both_axes(self):
        faces = [
            {'side': 'front', 'basis': 'source_layout', 'width_cm': 10.0, 'height_cm': 5.0},
            {'side': 'back', 'basis': 'source_layout', 'width_cm': 10.0, 'height_cm': 5.0},
        ]
        ai_result = {
            'adjustments': [
                {'side': 'front', 'action': 'resize', 'axis': 'width', 'width_cm': 7.0, 'height_cm': 0, 'dimension_refs': ['message:fake'], 'reason': 'bad ref'},
                {'side': 'back', 'action': 'resize', 'axis': 'both', 'width_cm': 7.0, 'height_cm': 7.0, 'dimension_refs': ['message:1'], 'reason': 'distorted'},
            ],
            'unmatched_requests': ['hông phải 4cm'],
        }
        updated, notes, warnings = apply_adjustment_math(faces, ai_result, ['message:1'])
        self.assertEqual(notes, [])
        self.assertEqual(len(warnings), 3)
        self.assertEqual(updated[0]['basis'], 'source_layout')
        self.assertEqual(updated[1]['basis'], 'source_layout')

    def test_opaque_native_source_accepts_multi_candidate_solid_rectangle(self):
        bg = Image.new('RGBA', (100, 40), (77, 34, 99, 255))
        # Simulate 1px anti-aliased outer border on preview while interior is 100% opaque.
        for x in range(100):
            bg.putpixel((x, 0), (77, 34, 99, 128))
        fg = Image.new('RGBA', (80, 24), (0, 0, 0, 0))
        ImageDraw.Draw(fg).rectangle((10, 5, 70, 18), fill=(255, 255, 255, 255))
        payload = {
            'auto_selected': True,
            'candidates': [
                {'id': '0.0.1', 'bounds': [1012.0, 408.0, 1103.0, 377.0], 'preview': _png_b64(fg)},
                {'id': '0.0.2.1', 'bounds': [997.0, 413.0, 1119.0, 372.0], 'preview': _png_b64(bg)},
            ],
        }
        self.assertTrue(opaque_native_source(payload))

    def test_opaque_native_source_rejects_transparent_artwork(self):
        logo = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(logo).ellipse((20, 20, 80, 80), fill=(200, 50, 50, 255))
        payload = {
            'auto_selected': True,
            'candidates': [
                {'id': '0.0.6', 'bounds': [100.0, 200.0, 200.0, 100.0], 'preview': _png_b64(logo)},
            ],
        }
        self.assertFalse(opaque_native_source(payload))


if __name__ == '__main__':
    unittest.main()
