import argparse
import json
import sys

import requests


def parse_cadastral_data(data):
    return json.loads(data)['features']


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
    return request.text


def load_osm_data(municipality_id):
    query_fmt = '''[out:json][timeout:60];
                   (area[ref={}][admin_level=7][place=municipality];)->.county;
                   nwr["ref:bygningsnr"](area.county);
                   out tags noids;
                '''
    query = query_fmt.format(municipality_id)
    return run_overpass_query(query)


def load_osm_refs(osm_raw):
    elements = json.loads(osm_raw)['elements']

    osm_refs = set()
    for element in elements:
        raw_ref = element['tags']['ref:bygningsnr']
        osm_refs |= parse_ref(raw_ref)

    return osm_refs


def format_geojson(features):
    geojson = {
            'type': 'FeatureCollection',
            'generator': 'filter_buildings.py',
            'features': features,
            }
    return json.dumps(geojson)


def filter_buildings(cadastral_buildings, osm_refs):
    def in_osm(building):
        raw_ref = building['properties']['ref:bygningsnr']
        building_refs = parse_ref(raw_ref)
        return bool(building_refs & osm_refs)

    return [b for b in cadastral_buildings if not in_osm(b)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--municipality', required=True)
    args = parser.parse_args()

    with open(args.input, 'r', encoding='utf-8') as file:
        cadastral = parse_cadastral_data(file.read())
    print(f'Loaded {len(cadastral)} buildings')

    osm_raw = load_osm_data(args.municipality)
    osm_refs = load_osm_refs(osm_raw)
    print(f'Loaded {len(osm_refs)} unique references from OSM')

    output = filter_buildings(cadastral, osm_refs)
    print(f'Writing {len(output)} buildings missing from OSM')

    with open(args.output, 'w', encoding='utf-8') as file:
        file.write(format_geojson(output))

    return 0


if __name__ == '__main__':
    sys.exit(main())
