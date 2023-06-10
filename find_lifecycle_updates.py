import argparse
import json
import re
import sys

import shared


def osm_buildings_by_ref(osm_buildings):
    by_ref = {}
    for osm_building in osm_buildings:
        tags = osm_building['tags']
        raw_ref = tags['ref:bygningsnr']
        for osm_ref in shared.parse_ref(raw_ref):
            try:
                by_ref[osm_ref].append(osm_building)
            except KeyError:
                by_ref[osm_ref] = [osm_building]

    return by_ref


def cadastral_construction_finished(building):
    tags = building['properties']
    if 'STATUS' not in tags:
        raise RuntimeError

    if re.match('#(RA|IG) .*', tags['STATUS']):
        return False

    return True


def osm_construction_finished(building):
    tags = building['tags']
    if 'planned:building' in tags:
        return False
    elif 'building' in tags and tags['building'] == 'construction':
        return False
    else:
        return True


def has_lifecycle_update(cadastral_building, osm_buildings):
    for osm_building in osm_buildings:
        cadastral_done = cadastral_construction_finished(cadastral_building)
        osm_done = osm_construction_finished(osm_building)

        if cadastral_done and not osm_done:
            return True

    return False


def find_lifecycle_updates(cadastral_buildings, osm_by_ref):
    updated = []
    for cadastral_building in cadastral_buildings:
        cadastral_ref = int(cadastral_building['properties']['ref:bygningsnr'])
        try:
            osm_buildings = osm_by_ref[cadastral_ref]
        except KeyError:
            # Building is missing from OSM
            continue

        if has_lifecycle_update(cadastral_building, osm_buildings):
            updated.append(cadastral_building)
            continue

    return updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--municipality', required=True)
    args = parser.parse_args()

    muni_id = shared.handle_municipality_argument(args.municipality)

    with open(args.input, 'r', encoding='utf-8') as file:
        cadastral = shared.parse_cadastral_data(file.read())
    print(f'Loaded {len(cadastral)} buildings')

    osm_raw = shared.load_building_tags(muni_id)
    osm_buildings = json.loads(osm_raw)['elements']
    osm_by_ref = osm_buildings_by_ref(osm_buildings)
    print(f'Loaded {len(osm_buildings)} buildings from OSM')

    output = find_lifecycle_updates(cadastral, osm_by_ref)
    print(f'Writing {len(output)} updated buildings')
    with open(args.output, 'w', encoding='utf-8') as file:
        file.write(shared.format_geojson(output))

    return 0


if __name__ == '__main__':
    sys.exit(main())
