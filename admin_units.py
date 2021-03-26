import requests  # Bruker requests - midlertidig. Fordi det er det biblioteket jeg kjenner best
import json
from collections import defaultdict
from typing import List, TypedDict, Dict, Literal


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


osm_api = "https://overpass.kumi.systems/api/interpreter"
query_template = """
[out:json][timeout:40];
(area[ref={}][admin_level=7][place=municipality];)->.a;
(relation["admin_level"="9"](area.a););
out body;
>;
out skel qt;
"""


def list_of_dict_iter(iterable, key):
	for i in iterable:
		yield i[key]


def bydel_requests(session: requests.Session, city: str):
	params = {"data": query_template.format(city)}
	repons = session.get(osm_api, params=params)
	return repons.json()


def osm_type_sorter(elements):
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


def connections(relation_ways: List[Way]):
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
		all_ways: Dict[int, Way],
		all_nodes: Dict[int, Node]
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
		way = all_ways[member['ref']]
		switch[member['role']].append(way)

	rings = [
		[((node := all_nodes[node_id])['lon'], node['lat']) for node_id in ring]
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
				[((node := all_nodes[node_id])['lon'], node['lat']) for node_id in ring]
				for ring in linear_rings_assembler(inner_way))

	return rings, geometry_type


def relation_iterator(
		relations: Dict[int, Relation],
		ways: Dict[int, Way],
		nodes: Dict[int, Node]
):
	for relation in relations.values():
		coordinates, geometry_type = polygon_assembler(relation['members'], ways, nodes)
		geometry = {'type': geometry_type, 'coordinates': coordinates}
		properties = relation['tags']
		yield {'type': 'Feature', 'geometry': geometry, 'properties': properties}


def overpass2geojson(overpass_json):
	nodes, ways, relations = osm_type_sorter(overpass_json['elements'])
	features = list(relation_iterator(relations, ways, nodes))
	return {"type": "FeatureCollection", "features": features}


if __name__ == "__main__":
	geojson = overpass2geojson(
		bydel_requests(requests.Session(), '0301')
	)
	with open('Oslo.geojson', 'w', encoding='utf-8') as file:
		file.write(json.dumps(geojson, indent=2))
