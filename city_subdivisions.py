import requests
from io import BytesIO
from zipfile import ZipFile
import json
import argparse
import itertools
from collections import defaultdict
from typing import Tuple, List, Iterable, Iterator, Collection, Sequence, TypedDict, Dict, NamedTuple, Literal, Union
import utm
try:
	from lxml import etree
except ImportError:
	import xml.etree.ElementTree as etree


class RelationMember(TypedDict):
	type: Literal['node', 'way', 'relation']
	ref: int
	role: str


class Relation(TypedDict):
	type: Literal['relation']
	id: int
	members: List[RelationMember]
	tags: Dict[str, str]


class Way(TypedDict):
	type: Literal['way']
	id: int
	nodes: List[int]
	tags: Dict[str, str]


class Node(TypedDict):
	type: Literal['node']
	id: int
	lat: float
	lon: float
	tags: Dict[str, str]


OsmElement = Union[Node, Way, Relation]


class OverpassResponse(TypedDict):
	version: float
	generator: str
	osm3s: Dict[str, str]
	elements: List[OsmElement]


PointCoord = Tuple[float, float]
LinearRingCoord = List[PointCoord]
PolygonCoord = List[LinearRingCoord]
MultipolygonCoord = List[PolygonCoord]


class PointGeometry(TypedDict):
	type: Literal['Point']
	coordinates: PointCoord


class PolygonGeometry(TypedDict):
	type: Literal['Polygon']
	coordinates: PolygonCoord


class MultipolygonGeometry(TypedDict):
	type: Literal['Multipolygon']
	coordinates: MultipolygonCoord


class Feature(TypedDict):
	type: Literal['Feature']
	geometry: Union[
		PointGeometry,
		PolygonGeometry,
		MultipolygonGeometry
	]
	properties: Dict[str, str]


class FeatureCollection(TypedDict):
	type: Literal['FeatureCollection']
	features: List[Feature]


class Bbox(NamedTuple):
	minlat: float
	minlon: float
	maxlat: float
	maxlon: float


city_with_bydel_id = {"0301", "1103", "3005", "4601", "5001"}
osm_api = "https://overpass.kumi.systems/api/interpreter"
query_template = """
[out:json][timeout:40];
(area[ref={}][admin_level=7][place=municipality];)->.a;
(relation["admin_level"="9"](area.a););
out body;
>;
out skel qt;
"""


def pairwise(iterable: Iterable):
	a, b = itertools.tee(iterable)
	next(b)
	return zip(a, b)


def chunk(collection: Collection, n):
	iterator = iter(collection)
	for _ in range(len(collection) // n):
		yield tuple(itertools.islice(iterator, n))


# Area necessary to calculate mass center of a polygon with holes.
def centroid_area_linear_ring(linear_ring: LinearRingCoord) -> Tuple[PointCoord, float]:

	if linear_ring[0] != linear_ring[-1]:
		raise RuntimeError('linear ring not closed')

	delta_x, delta_y = linear_ring[0]
	reset = ((x - delta_x, y - delta_y) for x, y in linear_ring)

	cx = 0.
	cy = 0.
	det = 0.

	for (xi, yi), (xj, yj) in pairwise(reset):
		det += (d := xi * yj - xj * yi)
		cx += (xi + xj) * d
		cy += (yi + yj) * d

	area = det / 2
	area_factor = 6 * area
	center_point = (
		cx / area_factor + delta_x,
		cy / area_factor + delta_y
	)
	return center_point, abs(area)


# Calculate mass centre of polygon
def centroid_polygon(polygon: PolygonCoord) -> PointCoord:
	center_point, outer_area = centroid_area_linear_ring(polygon[0])
	if inner_rings := polygon[1:]:
		cx = center_point[0] * outer_area
		cy = center_point[1] * outer_area
		area_sum = outer_area
		for inner_ring in inner_rings:
			inner_cp, inner_area = centroid_area_linear_ring(inner_ring)
			cx -= center_point[0] * inner_area
			cy -= center_point[1] * inner_area
			area_sum -= inner_area
		center_point = (cx / area_sum, cy / area_sum)
	return center_point


def point_inside_bbox(point: PointCoord, bbox: Bbox):
	p_lon, p_lat = point
	return bbox.minlat <= p_lat <= bbox.maxlat and bbox.minlon <= p_lon <= bbox.maxlon


def bbox_for_polygon(polygon: PolygonCoord) -> Bbox:
	outer_ring = polygon[0]
	return Bbox(
		min(p[1] for p in outer_ring),
		min(p[0] for p in outer_ring),
		max(p[1] for p in outer_ring),
		max(p[0] for p in outer_ring)
	)


def bboxes_for_multipolygon(multipolygon: MultipolygonCoord) -> List[Bbox]:
	return [bbox_for_polygon(polygon) for polygon in multipolygon]


# Ray tracing method
def inside_linear_ring(point: PointCoord, linear_ring: LinearRingCoord):

	if linear_ring[0] != linear_ring[-1]:
		raise RuntimeError('linear ring not closed')

	px, py = point
	inside = False

	for (xi, yi), (xj, yj) in pairwise(linear_ring):
		if (
				((yi > py) != (yj > py)) and
				(px < (xj - xi) * (py - yi) / (yj - yi) + xi)
		):
			inside = not inside

	return inside


def inside_polygon(point: PointCoord, polygon: PolygonCoord, bbox: Bbox = None):
	bbox = bbox if bbox else bbox_for_polygon(polygon)
	if not point_inside_bbox(point, bbox):
		return False

	inside = inside_linear_ring(point, polygon[0])
	if inside:
		for inner_ring in polygon[1:]:
			if inside_linear_ring(point, inner_ring):
				inside = False
	return inside


def inside_multipolygon(point: PointCoord, multipolygon: MultipolygonCoord, bboxes: List[Bbox] = None):
	bboxes = bboxes if bboxes else bboxes_for_multipolygon(multipolygon)
	if not any(point_inside_bbox(point, bbox) for bbox in bboxes):
		return False

	inside = any(inside_polygon(point, polygon, bbox) for polygon, bbox in zip(multipolygon, bboxes))
	return inside


def city_subdivisions_request(session: requests.Session, city_id: str):
	params = {"data": query_template.format(city_id)}
	response = session.get(osm_api, params=params)
	return response.json()


def osm_type_sorter(elements: Iterable[OsmElement]):
	relations: Dict[int, Relation] = {}
	ways: Dict[int, Way] = {}
	nodes: Dict[int, Node] = {}
	# Python 3.10 pattern matching ?
	switch = {
		"relation": relations,
		"way": ways,
		"node": nodes
	}

	for element in elements:
		osmtype = element["type"]
		osmid = element["id"]
		switch[osmtype][osmid] = element

	return nodes, ways, relations


def connections(relation_ways: Iterable[Way]):
	end_nodes = defaultdict(set)

	for way in relation_ways:
		way_id = way['id']
		for i in (0, -1):
			end_node_id = way['nodes'][i]
			end_nodes[end_node_id].add(way_id)

	return end_nodes


def linear_rings_assembler(relation_ways: Sequence[Way]) -> List[List[int]]:
	current_way = relation_ways[0]

	end_nodes = connections(relation_ways)
	unused = {w['id']: w for w in relation_ways}
	current_ring = [current_way['nodes'][0]]
	rings = [current_ring]

	for _ in range(len(relation_ways)):
		current_ring.extend(current_way['nodes'][1:])
		last_node = current_ring[-1]

		del unused[current_way['id']]

		if current_ring[0] != last_node:
			connected_way_ids = end_nodes[last_node] - {current_way['id']}
			connected_way = next(unused[w_id] for w_id in connected_way_ids)
			if connected_way['nodes'][0] == last_node:
				current_way = connected_way
			elif connected_way['nodes'][-1] == last_node:
				connected_way['nodes'] = list(reversed(connected_way['nodes']))
				current_way = connected_way

		elif unused:
			current_way = next(iter(unused.values()))
			current_ring = [current_way['nodes'][0]]
			rings.append(current_ring)

	if current_ring[0] != current_ring[-1]:
		raise RuntimeError('Invalid polygon - ring not closed')

	return rings


def polygon_assembler(
		members: Iterable[RelationMember],
		ways: Dict[int, Way],
		nodes: Dict[int, Node]
) -> Tuple[Union[PolygonCoord, MultipolygonCoord], Literal['Polygon', 'Multipolygon']]:

	outer_way = []
	inner_way = []
	# Python 3.10 pattern matching !
	switch = defaultdict(list, {
		"": outer_way,
		"outer": outer_way,
		"inner": inner_way,
	})

	for member in filter(lambda m: m['type'] == 'way', members):
		way = ways[member['ref']]
		switch[member['role']].append(way)

	rings = [
		[((node := nodes[node_id])['lon'], node['lat']) for node_id in ring]
		for ring in linear_rings_assembler(outer_way)
	]
	if len(rings) > 1:
		geometry_type = "Multipolygon"
		rings = [[ring] for ring in rings]
		if inner_way:
			raise NotImplementedError("Simple feature multipolygons with inner ways not implemented yet")
	else:
		geometry_type = "Polygon"
		if inner_way:
			rings.extend(
				[((node := nodes[node_id])['lon'], node['lat']) for node_id in ring]
				for ring in linear_rings_assembler(inner_way)
			)

	return rings, geometry_type


def overpass2features(elements: Iterable[OsmElement]) -> Iterator[Feature]:
	nodes, ways, relations = osm_type_sorter(elements)
	for relation in relations.values():
		coordinates, geometry_type = polygon_assembler(relation['members'], ways, nodes)
		geometry = {'type': geometry_type, 'coordinates': coordinates}
		properties = relation['tags']
		yield {'type': 'Feature', 'geometry': geometry, 'properties': properties}


def features2geojson(features: Iterable[Feature]) -> FeatureCollection:
	return {"type": "FeatureCollection", "features": list(features)}


def building_center(building: Feature) -> PointCoord:
	geometry = building['geometry']
	geometry_type = geometry['type']
	if geometry_type == "Polygon":
		center = centroid_polygon(geometry['coordinates'])
	elif geometry_type == "Point":
		center = geometry['coordinates']
	else:
		raise RuntimeError(f'A building should not have geometry type {geometry_type}')

	return center


def buildings_inside_subdivision(
		buildings: Iterable[Feature],
		subdivision: Feature
) -> Iterator[Feature]:

	geometry = subdivision['geometry']
	geometry_type = geometry['type']
	coordinates = geometry['coordinates']

	if geometry_type == "Polygon":
		inside_func = inside_polygon
		bbox = bbox_for_polygon(coordinates)
	elif geometry_type == "Multipolygon":
		inside_func = inside_multipolygon
		bbox = bboxes_for_multipolygon(coordinates)
	else:
		raise RuntimeError(f'A subdivision should not have geometry type {geometry_type}')

	building_centers = {b['properties']['ref:bygningsnr']: building_center(b) for b in buildings}

	return filter(
		lambda b: inside_func(building_centers[b['properties']['ref:bygningsnr']], coordinates, bbox),
		buildings
	)


def ftp_name(name: str) -> str:
	replacements = [(" ", "_"), ("Æ", "E"), ("Ø", "O"), ("Å", "A"), ("æ", "e"), ("ø", "o"), ("å", "a")]
	for old, new in replacements:
		name = name.replace(old, new)
	return name


def post_codes_request(
		session: requests.Session, municipality_id: str, municipality_name: str
) -> etree.Element:

	url = (
		'https://nedlasting.geonorge.no/geonorge/Basisdata/Postnummeromrader/GML/'
		f'Basisdata_{municipality_id}_{ftp_name(municipality_name)}_25833_Postnummeromrader_GML.zip'
	)
	response = session.get(url)
	zip_file = ZipFile(BytesIO(response.content))
	filename = zip_file.namelist()[0]
	with zip_file.open(filename) as gml_file:
		tree = etree.parse(gml_file)
	return tree.getroot()


def utm_to_lon_lat(
		points: Iterable[PointCoord], utm_zone: int, hemisphere: Literal['N', 'S'] = 'N'
) -> Iterator[PointCoord]:

	for point in points:
		x, y = point
		lat, lon = utm.UtmToLatLon(x, y, utm_zone, hemisphere)
		yield lon, lat


def gml_pos_list(pos_list: etree.Element) -> Iterator[PointCoord]:
	split_text = pos_list.text.split()
	for point in chunk(split_text, 2):
		yield map(float, point)


def gml_patch_assembler(gml_patch: etree.Element, namespace, utm_zone: int) -> PolygonCoord:
	gml_outer = gml_patch.find("./gml:exterior", namespace)
	pos_list = gml_outer.find(".//gml:posList", namespace)
	outer_ring = list(utm_to_lon_lat(gml_pos_list(pos_list), utm_zone))
	rings = [outer_ring]
	if gml_inners := gml_patch.findall("./gml:interior", namespace):
		for gml_inner in gml_inners:
			pos_list = gml_inner.find(".//gml:posList", namespace)
			inner_ring = list(utm_to_lon_lat(gml_pos_list(pos_list), utm_zone))
			rings.append(inner_ring)
	return rings


def gml_polygon_assembler(
		gml_surface: etree.Element, namespace
) -> Union[PolygonGeometry, MultipolygonGeometry]:

	utm_zone = int(gml_surface.get("srsName")[-2:])
	patches = gml_surface.findall("./gml:patches/gml:PolygonPatch", namespace)
	if len(patches) == 1:
		geometry_type = 'Polygon'
		patch = patches[0]
		coordinates = gml_patch_assembler(patch, namespace, utm_zone)
	else:
		geometry_type = 'Multipolygon'
		coordinates = [gml_patch_assembler(patch, namespace, utm_zone) for patch in patches]

	return {'type': geometry_type, 'coordinates': coordinates}


def postcodes2features(gml_feature_collection: etree.Element) -> Iterator[Feature]:
	namespace = {
		"gml": "http://www.opengis.net/gml/3.2",
		"app": "http://skjema.geonorge.no/SOSI/produktspesifikasjon/Postnummeromrader/20180215"
	}
	gml_features = gml_feature_collection.iterfind("./gml:featureMember", namespace)
	postcode_filter = filter(lambda f: f.find('./app:Postnummerområde', namespace) is not None,  gml_features)

	for gml_feature in postcode_filter:
		surface = gml_feature.find('.//gml:Surface', namespace)
		geometry = gml_polygon_assembler(surface, namespace)
		postcode = gml_feature.find('.//app:postnummer', namespace).text
		postal_place = gml_feature.find('.//app:poststed', namespace).text
		postal_place = postal_place[0] + postal_place[1:].lower()
		properties = {'name': f"{postcode} {postal_place}", 'postcode': postcode, 'postal place': postal_place}
		yield {'type': 'Feature', 'geometry': geometry, 'properties': properties}


def load_municipalities(session: requests.Session) -> Dict[str, str]:
	url = "https://ws.geonorge.no/kommuneinfo/v1/fylkerkommuner"
	params = {"filtrer": ','.join(("fylkesnummer", "fylkesnavn", "kommuner.kommunenummer", "kommuner.kommunenavnNorsk"))}
	response = session.get(url, params=params)
	data = response.json()

	municipalities = {}

	for county in data:
		for municipality in county['kommuner']:
			municipalities[municipality['kommunenummer']] = municipality['kommunenavnNorsk']

	return municipalities


def get_municipality(parameter: str, municipalities: Dict[str, str]):
	if ".geojson" in parameter:
		municipality_id = parameter[10:14]  # e.g. bygninger_0301_Oslo.geojson
		municipality_name = municipalities[municipality_id]
		filename = parameter

	else:
		if parameter.isdigit():
			municipality_id = parameter

		else:
			duplicate = False
			found_id = None
			for mun_id, mun_name in municipalities.items():
				if parameter.lower() == mun_name.lower():
					found_id = mun_id
					duplicate = False
					break
				elif parameter.lower() in mun_name.lower():
					if found_id:
						duplicate = True
					else:
						found_id = mun_id

			if found_id and not duplicate:
				municipality_id = found_id
			else:
				raise RuntimeError(f'Municipality {parameter} not found, or ambiguous')

		municipality_name = municipalities[municipality_id]
		filename = f'bygninger_{municipality_id:4}_{municipality_name}.geojson'

	return municipality_id, municipality_name, filename


def get_arguments() -> argparse.Namespace:
	parser = argparse.ArgumentParser()
	parser.add_argument('input', help="municipality name, kode or filename from building2osm")
	parser.add_argument('-s', '--subdivision', choices=['bydel', 'postnummer'])
	parser.add_argument('-a', '--area', dest='save_area', action='store_true', help="saves areas as geojson",)
	return parser.parse_args()


def main():
	arguments = get_arguments()

	session = requests.Session()
	municipalities = load_municipalities(session)
	municipality_id, municipality_name, filename = get_municipality(arguments.input, municipalities)

	with open(filename, 'r', encoding='utf-8') as file:
		input_geojson: FeatureCollection = json.load(file)

	buildings = input_geojson['features']

	print(f'Loaded {len(buildings)} buildings from "{filename}"\n')

	if not arguments.subdivision:
		arguments.subdivision = 'bydel' if municipality_id in city_with_bydel_id else 'postnummer'

	if arguments.subdivision == 'bydel':
		if municipality_id not in city_with_bydel_id:
			raise RuntimeError(f'Only the municipalities with these ids have "bydeler" {city_with_bydel_id}')
		subdivision_plural = 'bydeler'
		overpass_json = city_subdivisions_request(session, municipality_id)
		print(f"Loaded {subdivision_plural} from overpass api")
		subdivisions = overpass2features(overpass_json['elements'])

	elif arguments.subdivision == 'postnummer':
		subdivision_plural = 'postnummere'
		xml_root = post_codes_request(session, municipality_id, municipality_name)
		subdivisions = postcodes2features(xml_root)
		print("Loaded postal codes")

	else:
		raise RuntimeError(f'subdivision {arguments.subdivision} not known')

	if arguments.save_area:
		subdivisions = list(subdivisions)
		geojson = features2geojson(subdivisions)
		filename = f'{subdivision_plural}_{municipality_id}_{municipality_name}.geojson'
		with open(filename, 'w', encoding='utf-8') as file:
			json.dump(geojson, file, indent=2)
		print(f'\tSaved area to "{filename}"')

	print("")

	for subdivision in subdivisions:
		relevant_buildings = buildings_inside_subdivision(buildings, subdivision)
		geojson = features2geojson(relevant_buildings)
		subdivision_name = subdivision['properties']['name']

		print(f"{arguments.subdivision.title()} {subdivision_name}:")
		print(f"\t{len(geojson['features']):6d} buildings with centroid inside area.")

		filename = (
			f'bygninger_{municipality_id}_{municipality_name.replace(" ", "_")}_'
			f'{arguments.subdivision}_{subdivision_name.replace(" ", "_")}.geojson'
		)
		with open(filename, 'w', encoding='utf-8') as file:
			json.dump(geojson, file, indent=2)

		print(f'\tSaved to "{filename}"')


if __name__ == "__main__":
	main()
