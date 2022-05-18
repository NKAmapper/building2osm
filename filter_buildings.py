import argparse
import json
import sys

import requests


def parse_ref(raw_ref):
    return {int(ref) for ref in raw_ref.split(';') if ref}


def run_overpass_query(query):
    overpass_url = "https://overpass-api.de/api/interpreter"
    params = {'data': query}
    version = '0.8.0'
    headers = {'User-Agent': 'building2osm/' + version}
    request = requests.get(overpass_url,
                           params=params,
                           headers=headers)
    return request.json()['elements']


def load_osm_refs(municipality_id):
    query_fmt = '''[out:json][timeout:60];
                   (area[ref={}][admin_level=7][place=municipality];)->.county;
                   nwr["ref:bygningsnr"](area.county);
                   out tags noids;
                '''
    query = query_fmt.format(municipality_id)
    elements = run_overpass_query(query)

    osm_refs = set()
    for element in elements:
        raw_ref = element['tags']['ref:bygningsnr']
        osm_refs |= parse_ref(raw_ref)

    return osm_refs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--municipality', required=True)
    args = parser.parse_args()

    with open(args.input, 'r', encoding='utf-8') as file:
        data = json.load(file)
        import_buildings = data['features']
    print('Loaded {} buildings'.format(len(import_buildings)))

    osm_refs = load_osm_refs(args.municipality)
    print('Loaded {} unique references from OSM'.format(len(osm_refs)))

    def in_osm(building):
        raw_ref = building['properties']['ref:bygningsnr']
        building_refs = parse_ref(raw_ref)
        return bool(building_refs & osm_refs)

    missing_in_osm = [b for b in import_buildings if not in_osm(b)]
    print('Writing {} buildings missing from OSM'.format(len(missing_in_osm)))

    with open(args.output, 'w', encoding='utf-8') as file:
        geojson = {
                'type': 'FeatureCollection',
                'generator': 'filter_buildings.py',
                'features': missing_in_osm,
                }
        json.dump(geojson, file)

    return 0


if __name__ == '__main__':
    sys.exit(main())
