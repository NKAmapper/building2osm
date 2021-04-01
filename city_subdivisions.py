import requests
import json
import argparse
from collections import defaultdict
from typing import Tuple, List, Iterable, Iterator, TypedDict, Dict, Literal, Union


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
	iterator = iter(iterable)
	ia = next(iterator)

	for ib in iterator:
		yield ia, ib
		ia = ib


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


def inside_polygon(point: PointCoord, polygon: PolygonCoord):
	inside = inside_linear_ring(point, polygon[0])
	if inside:
		for inner_ring in polygon[1:]:
			if inside_linear_ring(point, inner_ring):
				inside = False
	return inside


def inside_multipolygon(point: PointCoord, multipolygon: MultipolygonCoord):
	inside = any(inside_polygon(point, polygon) for polygon in multipolygon)
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


def linear_rings_assembler(relation_ways: List[Way]):
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
		members: List[RelationMember],
		ways: Dict[int, Way],
		nodes: Dict[int, Node]
):
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


def overpass2geojson(overpass_json: OverpassResponse) -> FeatureCollection:
	features = list(overpass2features(overpass_json['elements']))
	return {"type": "FeatureCollection", "features": features}


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

	if geometry_type == "Polygon":
		inside_func = inside_polygon
	elif geometry_type == "Multipolygon":
		inside_func = inside_multipolygon
	else:
		raise RuntimeError(f'A subdivision should not have geometry type {geometry_type}')

	building_centers = {b['properties']['ref:bygningsnr']: building_center(b) for b in buildings}

	return filter(
		lambda b: inside_func(building_centers[b['properties']['ref:bygningsnr']], geometry['coordinates']),
		buildings
	)


def get_arguments():
	parser = argparse.ArgumentParser()
	parser.add_argument('input_filename', type=str)
	parser.add_argument('-s', '--subdivision', choices=['bydel'], default='bydel')
	return parser.parse_args()


def main():
	arguments = get_arguments()

	with open(arguments.input_filename, 'r', encoding='utf-8') as file:
		input_geojson: FeatureCollection = json.load(file)

	buildings = input_geojson['features']

	municipality_id = arguments.input_filename[10:14]  # e.g. bygninger_0301_Oslo.geojson
	municipality_name = arguments.input_filename[15:].replace(".geojson", "")

	if arguments.subdivision == 'bydel':
		if municipality_id not in city_with_bydel_id:
			raise RuntimeError(f'Only the municipalities with these ids have "bydeler" {city_with_bydel_id}')
		with requests.Session() as session:
			overpass_json = city_subdivisions_request(session, municipality_id)
		print("Loaded bydeler from overpass api")
		subdivisions = overpass2features(overpass_json['elements'])

	else:
		raise RuntimeError(f'subdivision {arguments.subdivision} not known')

	for subdivision in subdivisions:
		relevant_buildings = list(buildings_inside_subdivision(buildings, subdivision))
		subdivision_name = subdivision['properties']['name'].replace(" ", "_")
		filename = f'bygninger_{municipality_id}_{municipality_name}_{arguments.subdivision}_{subdivision_name}.geojson'
		with open(filename, 'w', encoding='utf-8') as file:
			json.dump(relevant_buildings, file, indent=2)

		print(f'Saved file {filename}')


if __name__ == "__main__":
	main()
