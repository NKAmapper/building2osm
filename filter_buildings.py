import argparse
import json
import sys

import shared


def load_osm_refs(osm_raw):
    elements = json.loads(osm_raw)['elements']

    osm_refs = set()
    for element in elements:
        raw_ref = element['tags']['ref:bygningsnr']
        osm_refs |= shared.parse_ref(raw_ref)

    return osm_refs


def filter_buildings(cadastral_buildings, osm_refs):
    def in_osm(building):
        raw_ref = building['properties']['ref:bygningsnr']
        building_refs = shared.parse_ref(raw_ref)
        return bool(building_refs & osm_refs)

    return [b for b in cadastral_buildings if not in_osm(b)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--municipality', required=True)
    args = parser.parse_args()

    with open(args.input, 'r', encoding='utf-8') as file:
        cadastral = shared.parse_cadastral_data(file.read())
    print(f'Loaded {len(cadastral)} buildings')

    osm_raw = shared.load_building_tags(args.municipality)
    osm_refs = load_osm_refs(osm_raw)
    print(f'Loaded {len(osm_refs)} unique references from OSM')

    output = filter_buildings(cadastral, osm_refs)
    print(f'Writing {len(output)} buildings missing from OSM')

    with open(args.output, 'w', encoding='utf-8') as file:
        file.write(shared.format_geojson(output))

    return 0


if __name__ == '__main__':
    sys.exit(main())
