import json
import re
import sys

import requests


class NoResults(Exception):
    pass


class MultipleResults(Exception):
    def __init__(self, *results):
        self.results = list(results)


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


def load_municipalities():
    url = ('https://ws.geonorge.no/kommuneinfo/v1/fylkerkommuner'
           + '?filtrer=fylkesnummer%2Cfylkesnavn%2Ckommuner.kommunenummer'
           + '%2Ckommuner.kommunenavnNorsk')
    request = requests.get(url)

    municipalities = {}
    for county in request.json():
        for municipality in county['kommuner']:
            muni_number = municipality['kommunenummer']
            muni_name = municipality['kommunenavnNorsk']
            municipalities[muni_number] = muni_name

    return municipalities


def resolve_municipality_id(municipalities, lookup_name):
    result = None
    for muni_id in municipalities:
        muni_name = municipalities[muni_id]
        if lookup_name.casefold() in muni_name.casefold():
            current = {
                    'id': muni_id,
                    'name': muni_name,
                    }

            if result is not None:
                raise MultipleResults(result, current)
            else:
                result = current

    if result is None:
        raise NoResults

    return result['id']


def handle_municipality_argument(municipality):
    if re.match('[0-9]{4}', municipality):
        return municipality

    municipalities = load_municipalities()
    try:
        return resolve_municipality_id(
                municipalities, municipality)
    except NoResults:
        sys.exit(f'Municipality {municipality} not found')
    except MultipleResults as e:
        sys.exit('Found multiple matching municipalities: {}'.format(
            ', '.join(
                [f'{item["id"]}/{item["name"]}' for item in e.results]
                )))
