"""The legacy Persian SHX text of the plans is decoded by a table built from the legend (scripts/gis/shx_text.py)."""
from django.test import SimpleTestCase

from scripts.gis import shx_text


class DecodeTheLegend(SimpleTestCase):
    def test_land_use_words_of_the_legend(self):
        for raw, word in (
            ('jÐ—v\x8d', 'تجاری'), ('l¸ـâkŒ', 'مسکونی'), ('nvl\x97k\x8c', 'درمانی'), ('hnhv\x8d', 'اداری'),
            ('nf¸\x9d—¢', 'دبستان'), ('HlâcaŒ', 'آموزشی'), ('o\x97k\x9b f\x9a©ha\x9e', 'خانه بهداشت'),
            ('{\x9a\x97kßÁn\x8d , `\x85dÁhd\x8c', 'جهانگردی و پذیرایی'), ('j—s‹¸—Ÿ , jÐš‹ˆhŸ', 'تاسیسات و تجهیزات'),
        ):
            with self.subTest(word=word):
                self.assertEqual(shx_text.read(raw), word)

    def test_a_character_autocad_could_not_store_is_a_decimal_byte(self):
        self.assertEqual(shx_text.read('k%%151k%%140'), shx_text.read('k\x97k\x8c'))

    def test_digits_are_stored_in_reverse(self):
        self.assertEqual(shx_text.reverse_digit_runs('051 and 05 and 6'), '150 and 50 and 6')

    def test_an_unknown_byte_is_shown_not_guessed(self):
        self.assertIn('<ff>', shx_text.decode('\xff'))
