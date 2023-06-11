import unittest

import find_lifecycle_updates


def cadastral(ref, status):
    if status == 'MB':
        status = '#MB Midlertidig brukstillatelse'
    elif status == 'IG':
        status = '#IG Igangsettingstillatelse'
    else:
        raise RuntimeError

    return {
        'properties': {
            'ref:bygningsnr': str(ref),
            'STATUS': status,
            },
        }


def osm(ref, planned=False, construction=False):
    tags = {
            'ref:bygningsnr': str(ref),
            }

    if planned:
        tags['planned:building'] = 'yes'
    elif construction:
        tags['building'] = 'construction'

    return {'tags': tags}


class TestFindLifecycleUpdate(unittest.TestCase):
    def _run_filter(self, cadastral_buildings, osm_buildings):
        osm_by_ref = find_lifecycle_updates.osm_buildings_by_ref(
                osm_buildings)
        return find_lifecycle_updates.find_lifecycle_updates(
                cadastral_buildings,
                osm_by_ref)

    def test_provisional_use_permit_is_update_from_planned(self):
        cadastral_buildings = [cadastral(1, status='MB')]
        osm_buildings = [osm(1, planned=True)]
        output = self._run_filter(cadastral_buildings, osm_buildings)
        self.assertEqual(cadastral_buildings, output)

    def test_provisional_use_permit_is_update_from_construction(self):
        cadastral_buildings = [cadastral(1, status='MB')]
        osm_buildings = [osm(1, construction=True)]
        output = self._run_filter(cadastral_buildings, osm_buildings)
        self.assertEqual(cadastral_buildings, output)

    def test_dont_include_construction_permit_when_osm_has_planned(self):
        # IG doesn't imply that construction has actually started, so planned
        # might still be the correct OSM tagging
        cadastral_buildings = [cadastral(1, status='IG')]
        osm_buildings = [osm(1, planned=True)]
        output = self._run_filter(cadastral_buildings, osm_buildings)
        self.assertEqual([], output)

    def test_ignore_building_missing_from_osm(self):
        cadastral_buildings = [cadastral(1, status='MB')]
        output = self._run_filter(cadastral_buildings, [])
        self.assertEqual([], output)
