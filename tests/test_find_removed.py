import unittest

import find_removed


expected_output_point = {
        'type': 'Feature',
        'geometry': {
            'type': 'Point',
            'coordinates': [
                11.0,
                59.0,
                ]
            },
        'properties': {
            'ref:bygningsnr': '1',
            'building': 'yes',
            }
        }


def cadastral(ref):
    return {'properties': {'ref:bygningsnr': str(ref)}}


def osm_node(ref):
    return {
            'type': 'node',
            'lat': 59.0,
            'lon': 11.0,
            'tags': {
                'building': 'yes',
                'ref:bygningsnr': str(ref),
                }
            }


def osm_way(ref):
    return {
            'type': 'way',
            'center': {
                'lat': 59.0,
                'lon': 11.0,
                },
            'tags': {
                'building': 'yes',
                'ref:bygningsnr': str(ref),
                }
            }


class TestFindRemoved(unittest.TestCase):
    def _find_removed(self, cadastral_buildings, osm_buildings):
        return find_removed.find_removed(cadastral_buildings,
                                         osm_buildings)

    def test_ignore_building_still_in_cadastral_data(self):
        removed = self._find_removed([cadastral(1)], [osm_node(1)])
        self.assertEqual([], removed)

    def test_ignore_building_missing_from_osm(self):
        removed = self._find_removed([cadastral(1)], [])
        self.assertEqual([], removed)

    def test_output_removed_building_node(self):
        removed = self._find_removed([], [osm_node(1)])
        self.assertEqual([expected_output_point], removed)

    def test_output_removed_building_way(self):
        removed = self._find_removed([], [osm_way(1)])
        self.assertEqual([expected_output_point], removed)
