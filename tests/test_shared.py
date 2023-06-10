import unittest

import shared


class TestMuncipalityResolution(unittest.TestCase):
    def setUp(self):
        self.municipalities = {
                '0301': 'Oslo',
                # '0231': 'Skedsmo',
                '3018': 'Våler',
                '3030': 'Lillestrøm',
                '3419': 'Våler',
                '4215': 'Lillesand',
                '4637': 'Hyllestad',
                }

    def _resolve(self, muni_name):
        return shared.resolve_municipality_id(
                self.municipalities,
                muni_name)

    def _assert_resolves_to(self, muni_name, muni_id):
        self.assertEqual(muni_id, self._resolve(muni_name))

    def test_resolve_municipality(self):
        self._assert_resolves_to('Lillestrøm', '3030')

    def test_resolve_zero_prefix(self):
        self._assert_resolves_to('Oslo', '0301')

    def test_resolve_duplicate_name(self):
        with self.assertRaises(shared.MultipleResults) as cm:
            self._resolve('Våler')

        self.assertEqual(cm.exception.results, [
            {'id': '3018', 'name': 'Våler'},
            {'id': '3419', 'name': 'Våler'},
            ])

    def test_resolve_missing(self):
        with self.assertRaises(shared.NoResults):
            self._resolve('Skedsmo')

    def test_resolve_with_different_case(self):
        self._assert_resolves_to('lILLESTRØM', '3030')

    def test_resolve_using_prefix(self):
        self._assert_resolves_to('Lillest', '3030')

    def test_prefix_resolution_to_multiple_results(self):
        with self.assertRaises(shared.MultipleResults) as cm:
            self._resolve('Lilles')

        self.assertEqual(cm.exception.results, [
            {'id': '3030', 'name': 'Lillestrøm'},
            {'id': '4215', 'name': 'Lillesand'},
            ])

    def test_resolve_with_infix_match(self):
        self._assert_resolves_to('llestr', '3030')
