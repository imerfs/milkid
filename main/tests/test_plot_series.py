"""Plot-number series (the «بیست هکتاری» and the ones to come): their plots are loaded with the village map, found by name or by the chosen series, never mixed up
with the village's own plot numbers, and survive a reload of the village drawing."""
import json
import re
import tempfile
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from main.gis import data as gis_data, inquiry, series
from main.models import MapParcel, ParcelArchive, VillageMap
from main.tests.helpers import client_for, make_user

SLUG = 'dastgerd'
KEY = 'hectare20'


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.map = VillageMap.objects.get(slug=SLUG)
        self.plots = MapParcel.objects.filter(village_map=self.map, series=KEY)


class Loaded(Base):
    def test_the_series_plots_are_loaded_apart_from_the_village_numbering(self):
        self.assertGreater(self.plots.count(), 500)
        self.assertEqual(self.plots.exclude(zone='', block_no='', renewal_code='').count(), 0)
        self.assertGreater(MapParcel.objects.filter(village_map=self.map, series='').count(), 4000)
        self.assertEqual(self.plots.values('uid').distinct().count(), self.plots.count())

    def test_numbers_start_from_one_and_a_repeated_number_keeps_both_plots(self):
        numbers = sorted(int(n) for n in self.plots.values_list('number', flat=True))
        self.assertEqual(numbers[0], 1)
        repeated = [n for n in set(numbers) if numbers.count(n) > 1]
        self.assertTrue(repeated)
        self.assertEqual(self.plots.filter(number=str(repeated[0])).count(), numbers.count(repeated[0]))

    def test_reloading_the_village_drawing_leaves_the_series_alone(self):
        before = sorted(self.plots.values_list('uid', 'pk'))
        from main.gis.loader import load_village_map
        from main import models
        load_village_map(SLUG, models)
        self.assertEqual(sorted(MapParcel.objects.filter(village_map=self.map, series=KEY).values_list('uid', 'pk')), before)

    def test_a_plot_dropped_from_the_file_goes_unless_it_has_an_archive(self):
        keep, drop, gone = self.plots.order_by('pk')[:3]
        ParcelArchive.objects.create(parcel=keep)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'one.geojson'
            path.write_text(json.dumps({'features': [{'properties': {'number': '1', 'area': 50.0}, 'geometry': {'type': 'Polygon', 'coordinates': [[[59, 32], [59.1, 32], [59.1, 32.1], [59, 32]]]}}]}),
                            encoding='utf-8')
            spec = dict(series.SERIES[SLUG][KEY], file=path)
            from main import models
            with mock.patch.dict(series.SERIES[SLUG], {KEY: spec}):
                series.load(self.map, models)
        left = set(self.plots.values_list('pk', flat=True))
        self.assertIn(keep.pk, left)
        self.assertNotIn(drop.pk, left)
        self.assertNotIn(gone.pk, left)


class Names(Base):
    def test_a_series_name_is_taken_out_of_the_search_text(self):
        for text in ('بیست هکتاری ۱۲', '20 هکتاری 12', '12 بیست هکتاری', 'بیست‌ هکتاری-12'.replace('‌', ' '), '۲۰ هکتاری-12'):
            self.assertEqual(series.split_query(SLUG, text), (KEY, '12'), text)

    def test_a_text_without_a_series_name_is_left_alone(self):
        self.assertEqual(series.split_query(SLUG, '۱۲-۶۹'), (None, '12-69'))
        self.assertEqual(series.split_query('nowhere', 'بیست هکتاری 12'), (None, 'بیست هکتاری 12'))

    def test_the_table_lists_the_series_with_their_names(self):
        self.assertEqual(series.table(SLUG), [{'key': KEY, 'name': 'بیست هکتاری'}])
        self.assertEqual(series.table('nowhere'), [])


class Search(Base):
    def setUp(self):
        super().setUp()
        self.number = self.plots.exclude(number='').order_by('pk').first().number

    def test_naming_the_series_finds_only_its_plot(self):
        found = inquiry.search(self.map, f'بیست هکتاری {self.number}')
        self.assertTrue(found)
        self.assertTrue(all(r['series'] == KEY and r['series_name'] == 'بیست هکتاری' and r['number'] == self.number for r in found))

    def test_a_bare_number_finds_the_series_and_the_village_plot_and_the_choice_narrows_it(self):
        both = MapParcel.objects.filter(village_map=self.map, series='', number=self.number).first()
        everything = inquiry.search(self.map, self.number)
        self.assertEqual({r['series'] for r in everything}, {KEY} | ({''} if both else set()))
        self.assertEqual({r['series'] for r in inquiry.search(self.map, self.number, series=KEY)}, {KEY})
        self.assertNotIn(KEY, {r['series'] for r in inquiry.search(self.map, self.number, series='main')})

    def test_the_village_cards_have_no_series(self):
        card = next(r for r in inquiry.search(self.map, self.number, series='main') or [{'series': ''}])
        self.assertEqual(card['series'], '')
        self.assertEqual(card['series_name'], '')

    def test_a_series_plot_has_no_renewal_code_and_the_name_alone_finds_nothing(self):
        card = inquiry.search(self.map, f'{self.number}', series=KEY)[0]
        self.assertEqual(card['code'], '')
        self.assertEqual(inquiry.search(self.map, 'بیست هکتاری'), [])

    def test_the_endpoint_takes_the_series(self):
        who = client_for(make_user('citizen'))
        data = who.get(reverse('main:inquiry_search', args=[SLUG]), {'q': self.number, 'series': KEY}).json()['results']
        self.assertTrue(data)
        self.assertEqual({r['series'] for r in data}, {KEY})


class OnTheMaps(Base):
    def test_the_inquiry_map_data_marks_each_plot_with_its_series_and_lists_them(self):
        data = client_for(make_user('citizen')).get(reverse('main:inquiry_data', args=[SLUG])).json()
        self.assertEqual(data['series'], [{'key': KEY, 'name': 'بیست هکتاری'}])
        marked = [f for f in data['features'] if f['properties']['r'] == KEY]
        self.assertEqual(len(marked), self.plots.count())

    def test_the_staff_map_data_marks_the_series_too(self):
        rows = gis_data.static_parcels(self.map)
        self.assertEqual(sum(1 for r in rows if r['properties']['sr'] == KEY), self.plots.count())


class StaffPanel(Base):
    def test_the_staff_card_of_a_series_plot_names_the_series(self):
        plot = self.plots.exclude(number='').first()
        who = client_for(make_user('admin'))
        card = who.get(reverse('main:gis_parcel', args=[SLUG, plot.pk])).json()['parcel']
        self.assertEqual((card['series'], card['series_name'], card['number']), (KEY, 'بیست هکتاری', plot.number))
        self.assertEqual(card['code'], '')

    def test_the_staff_map_page_hands_the_series_and_their_words_to_the_script(self):
        page = client_for(make_user('admin')).get(reverse('main:gis_map', args=[SLUG])).content.decode()
        config = json.loads(re.search(r'<script id="vm-config" type="application/json">(.*?)</script>', page, re.S).group(1))
        self.assertEqual(config['series'][0]['key'], KEY)
        self.assertIn('20 هکتاری', config['series'][0]['aliases'])
