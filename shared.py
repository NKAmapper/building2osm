import json

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
    request.raise_for_status()
    return request.text


def load_building_tags(municipality_id, with_position=False):
    center = 'center' if with_position else ''
    query = f'''[out:json][timeout:60];
                (area[ref={municipality_id}]
                     [admin_level=7]
                     [place=municipality];
                ) -> .county;
                nwr["ref:bygningsnr"](area.county);
                out tags noids {center};
             '''
    return run_overpass_query(query)


def parse_cadastral_data(data):
    return json.loads(data)['features']


def format_geojson(features):
    geojson = {
            'type': 'FeatureCollection',
            'generator': 'filter_buildings.py',
            'features': features,
            }
    return json.dumps(geojson)
