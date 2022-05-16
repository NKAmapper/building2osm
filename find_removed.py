import argparse
import json

import shared


def collect_refs(buildings):
    refs = set()

    for building in buildings:
        try:
            tags = building['tags']
        except KeyError:
            tags = building['properties']

        raw_ref = tags['ref:bygningsnr']
        for ref in shared.parse_ref(raw_ref):
            refs.add(ref)

    return refs


def to_output(building):
    if building['type'] == 'node':
        lon = building['lon']
        lat = building['lat']
    else:
        lon = building['center']['lon']
        lat = building['center']['lat']

    return {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [
                    lon,
                    lat,
                    ]
                },
            'properties': building['tags'],
            }


def find_removed(cadastral_buildings, osm_buildings):
    cadastral_refs = collect_refs(cadastral_buildings)
    osm_refs = collect_refs(osm_buildings)

    removed_buildings = []
    for ref in osm_refs - cadastral_refs:
        for osm_building in osm_buildings:
            if ref in collect_refs([osm_building]):
                try:
                    removed_buildings.append(to_output(osm_building))
                except Exception:
                    print(osm_building)
                    raise

    return removed_buildings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--municipality', required=True)
    args = parser.parse_args()

    with open(args.input, 'r', encoding='utf-8') as file:
        cadastral = shared.parse_cadastral_data(file.read())
    print(f'Loaded {len(cadastral)} buildings')

    osm_raw = shared.load_building_tags(args.municipality,
                                        with_position=True)
    osm_buildings = json.loads(osm_raw)['elements']
    print(f'Loaded {len(osm_buildings)} buildings from OSM')

    output = find_removed(cadastral, osm_buildings)
    print(f'Writing {len(output)} buildings that have been removed')

    with open(args.output, 'w', encoding='utf-8') as file:
        file.write(shared.format_geojson(output))


if __name__ == '__main__':
    main()
