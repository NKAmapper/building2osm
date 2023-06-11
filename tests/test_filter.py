import json
import unittest

import filter_buildings


def cadastral(ref):
    return {
        'properties': {
            'ref:bygningsnr': str(ref),
            },
        }


def osm(ref):
    return {
        'tags': {
            'ref:bygningsnr': str(ref),
            },
        }


class TestBuildingFilter(unittest.TestCase):
    def _run_filter(self, cadastral_buildings, osm_ref):
        return filter_buildings.filter_buildings(cadastral_buildings,
                                                 osm_ref)

    def test_remove_if_imported(self):
        output = self._run_filter([cadastral(1)], {1})
        self.assertEqual([], output)

    def test_keep_if_not_in_osm(self):
        cadastral_buildings = [cadastral(1)]
        output = self._run_filter(cadastral_buildings, set())
        self.assertEqual(cadastral_buildings, output)


class TestOsmDataParsing(unittest.TestCase):
    def _parse(self, osm_buildings):
        return filter_buildings.load_osm_refs(
                json.dumps({'elements': osm_buildings}))

    def test_parse_empty(self):
        self.assertEqual(set(), self._parse([]))

    def test_parse_single_building(self):
        self.assertEqual({1}, self._parse([osm(1)]))

    def test_parse_duplicate_id(self):
        self.assertEqual({2}, self._parse([osm(2), osm(2)]))
