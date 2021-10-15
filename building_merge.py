#!/usr/bin/env python3
# -*- coding: utf8

# building_merge.py
# Conflates geojson building import file with existing buildings in OSM.
# Usage: building_merge <municipality name> [max Hausdorff distance] [filename.geojson] [-debug].
# geojson file from building2osm must be present in default folder. Other filename is optional parameter.
# Creates OSM file (manual upload to OSM).

import math
import sys
import time
import json
import os.path
import urllib.request, urllib.parse
from xml.etree import ElementTree as ET


version = "0.6.0"

request_header = {"User-Agent": "building2osm/" + version}

overpass_api = "https://overpass-api.de/api/interpreter"  # Overpass endpoint

import_folder = "~/Jottacloud/osm/bygninger/"  # Folder containing import building files (default folder tried first)

margin_hausdorff = 10.0	# Maximum deviation between polygons (meters)
margin_tagged = 5.0		# Maximum deviation between polygons if building is tagged (meters)
margin_area = 0.5       # Max 50% difference of building areas

remove_addr = True 		# Remove addr tags from buildings

# No warnings when replacing these building tags with each other within same category
similar_buildings = {
	'residential': ["house", "detached", "semidetached_house", "terrace", "farm", "apartments", "residential", "cabin", "hut", "bungalow"],
	'commercial':  ["retail", "commercial", "warehouse", "industrial", "office"],
	'farm':        ["barn", "farm_auxiliary", "shed", "cabin"]
}

debug = False 			# Output extra tags for debugging/testing


# Output message to console

def message (text):

	sys.stderr.write(text)
	sys.stderr.flush()



# Format time

def timeformat (sec):

	if sec > 3600:
		return "%i:%02i:%02i hours" % (sec / 3600, (sec % 3600) / 60, sec % 60)
	elif sec > 60:
		return "%i:%02i minutes" % (sec / 60, sec % 60)
	else:
		return "%i seconds" % sec


# Format decimal number

def format_decimal(number):

	if number:
		number = "%.1f" % float(number)
		return number.rstrip("0").rstrip(".")
	else:
		return ""


# Compute approximation of distance between two coordinates, (lat,lon), in meters
# Works for short distances

def distance (point1, point2):

	lon1, lat1, lon2, lat2 = map(math.radians, [point1[0], point1[1], point2[0], point2[1]])
	x = (lon2 - lon1) * math.cos( 0.5*(lat2+lat1) )
	y = lat2 - lat1
	return 6371000.0 * math.sqrt( x*x + y*y )  # Metres



# Compute approximation of distance between two coordinates, (lat,lon), in meters
# Works for short distances

def distance2 (point1, point2):

	lon1, lat1, lon2, lat2 = map(math.radians, [point1[0], point1[1], point2[0], point2[1]])

	dlon = lon2 - lon1
	dlat = lat2 - lat1

	a = math.sin( dlat / 2 ) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin( dlon / 2 ) ** 2
	c = 2 * math.atan2( math.sqrt(a), math.sqrt(1 - a) )

	return 6371000.0 * c  # Metres



# Compute closest distance from point p3 to line segment [s1, s2].
# Works for short distances.

def line_distance(s1, s2, p3):

	x1, y1, x2, y2, x3, y3 = map(math.radians, [s1[0], s1[1], s2[0], s2[1], p3[0], p3[1]])

	# Simplified reprojection of latitude
	x1 = x1 * math.cos( y1 )
	x2 = x2 * math.cos( y2 )
	x3 = x3 * math.cos( y3 )

	A = x3 - x1
	B = y3 - y1
	dx = x2 - x1
	dy = y2 - y1

	dot = (x3 - x1)*dx + (y3 - y1)*dy
	len_sq = dx*dx + dy*dy

	if len_sq != 0:  # in case of zero length line
		param = dot / len_sq
	else:
		param = -1

	if param < 0:
		x4 = x1
		y4 = y1
	elif param > 1:
		x4 = x2
		y4 = y2
	else:
		x4 = x1 + param * dx
		y4 = y1 + param * dy

	# Also compute distance from p to segment

	x = x4 - x3
	y = y4 - y3
	distance = 6371000 * math.sqrt( x*x + y*y )  # In meters
	'''
	# Project back to longitude/latitude

	x4 = x4 / math.cos(y4)

	lon = math.degrees(x4)
	lat = math.degrees(y4)

	return (lon, lat, distance)
	'''
	return distance


# Calculate coordinate area of polygon in square meters
# Simple conversion to planar projection, works for small areas
# < 0: Clockwise
# > 0: Counter-clockwise
# = 0: Polygon not closed

def polygon_area (polygon):

	if polygon and polygon[0] == polygon[-1]:
		lat_dist = math.pi * 6371009.0 / 180.0

		coord = []
		for node in polygon:
			y = node[1] * lat_dist
			x = node[0] * lat_dist * math.cos(math.radians(node[1]))
			coord.append((x,y))

		area = 0.0
		for i in range(len(coord) - 1):
			area += (coord[i+1][0] - coord[i][0]) * (coord[i+1][1] + coord[i][1])  # (x2-x1)(y2+y1)

		return int(area / 2.0)
	else:
		return 0



# Calculate center of polygon nodes (simple average method)
# Note: If nodes are skewed to one side, the center will be skewed to the same side

def polygon_center (polygon):

	if len(polygon) == 0:
		return None
	elif len(polygon) == 1:
		return polygon[0]

	length = len(polygon)
	if polygon[0] == polygon[-1]:
		length -= 1

	x = 0
	y = 0
	for node in polygon[:length]:
		x += node[0]
		y += node[1]

	x = x / length
	y = y / length

	return (x, y)



# Calculate centroid of polygon
# Source: https://en.wikipedia.org/wiki/Centroid#Of_a_polygon

def polygon_centroid (polygon):

	if polygon[0] == polygon[-1]:
		x = 0
		y = 0
		det = 0

		for i in range(len(polygon) - 1):
			d = polygon[i][0] * polygon[i+1][1] - polygon[i+1][0] * polygon[i][1]
			det += d
			x += (polygon[i][0] + polygon[i+1][0]) * d  # (x1 + x2) (x1*y2 - x2*y1)
			y += (polygon[i][1] + polygon[i+1][1]) * d  # (y1 + y2) (x1*y2 - x2*y1)

		x = x / (3.0 * det)
		y = y / (3.0 * det)

		return (x, y)

	else:
		return None



# Calculate new node with given distance offset in meters
# Works over short distances

def coordinate_offset (node, distance):

	m = (1 / ((math.pi / 180.0) * 6378137.0))  # Degrees per meter

	latitude = node[1] + (distance * m)
	longitude = node[0] + (distance * m) / math.cos( math.radians(node[1]) )

	return (longitude, latitude)



# Calculate Hausdorff distance, including reverse.
# Abdel Aziz Taha and Allan Hanbury: "An Efficient Algorithm for Calculating the Exact Hausdorff Distance"
# https://publik.tuwien.ac.at/files/PubDat_247739.pdf

def hausdorff_distance(p1, p2):

	N1 = len(p1) - 1
	N2 = len(p2) - 1

# Shuffling for small lists disabled
#	random.shuffle(p1)
#	random.shuffle(p2)

	cmax = 0
	for i in range(N1):
		no_break = True
		cmin = 999999.9  # Dummy

		for j in range(N2):

			d = line_distance(p2[j], p2[j+1], p1[i])
    
			if d < cmax: 
				no_break = False
				break

			if d < cmin:
				cmin = d

		if cmin < 999999.9 and cmin > cmax and no_break:
			cmax = cmin

#	return cmax

	for i in range(N2):
		no_break = True
		cmin = 999999.9  # Dummy

		for j in range(N1):

			d = line_distance(p1[j], p1[j+1], p2[i])
    
			if d < cmax:
				no_break = False
				break

			if d < cmin:
				cmin = d

		if cmin < 999999.9 and cmin > cmax and no_break:
			cmax = cmin

	return cmax



# Identify municipality name, unless more than one hit
# Returns municipality number, or input parameter if not found

def get_municipality (parameter):

	if parameter.isdigit():
		return parameter

	else:
		parameter = parameter
		found_id = ""
		duplicate = False
		for mun_id, mun_name in iter(municipalities.items()):
			if parameter.lower() == mun_name.lower():
				return mun_id
			elif parameter.lower() in mun_name.lower():
				if found_id:
					duplicate = True
				else:
					found_id = mun_id

		if found_id and not duplicate:
			return found_id
		else:
			return parameter



# Load dict of all municipalities

def load_municipalities():

	url = "https://ws.geonorge.no/kommuneinfo/v1/fylkerkommuner?filtrer=fylkesnummer%2Cfylkesnavn%2Ckommuner.kommunenummer%2Ckommuner.kommunenavnNorsk"
	file = urllib.request.urlopen(url)
	data = json.load(file)
	file.close()
	for county in data:
		for municipality in county['kommuner']:
			municipalities[ municipality['kommunenummer'] ] = municipality['kommunenavnNorsk']



# Load buildings from geojson file

def load_import_buildings(filename):

	global import_buildings

	message ("Loading import buildings ...\n")
	message ("\tFilename '%s'\n" % filename)

	if not os.path.isfile(filename):
		test_filename = os.path.expanduser(import_folder + filename)
		if os.path.isfile(test_filename):
			filename = test_filename
		else:
			sys.exit("\t*** File not found\n\n")

	file = open(filename)
	data = json.load(file)
	file.close()
	import_buildings = data['features']

	# Add polygon center and area

	for building in import_buildings:
		if building['geometry']['type'] == "Polygon" and len(building['geometry']['coordinates']) == 1:

			building['center'] = polygon_center( building['geometry']['coordinates'][0] )
			building['area'] = abs(polygon_area( building['geometry']['coordinates'][0] ))
			if debug:
				building['properties']['AREA'] = str(building['area'])

		if "STATUS" in building['properties']:
			del building['properties']['STATUS']
		if "DATE" in building['properties']:
			del building['properties']['DATE']

		# Temporary fixes

		if "#672 " in building['properties']['TYPE'] or "#673 " in building['properties']['TYPE']:
			building['properties']['building'] = "religious"

		if building['properties']['building'] == "barracks":
			building['properties']['building'] = "container"
		if building['properties']['building'] == "hotel" and "area" in building and building['area'] < 100:
			building['properties']['building'] = "cabin"
		if building['properties']['building'] in ["garage", "barn"] and "area" in building and building['area'] < 15:
			building['properties']['building'] = "shed"
		if building['properties']['building'] == "barn" and "area" in building and building['area'] < 100:
			building['properties']['building'] = "farm_auxiliary"


	message ("\t%i buildings loaded\n" % len(import_buildings))



# Load existing buildings from OSM Overpass

def load_osm_buildings(municipality_id):

	global osm_elements

	message ("Loading existing buildings from OSM ...\n")

	query = '[out:json][timeout:60];(area[ref=%s][admin_level=7][place=municipality];)->.a;(nwr["building"](area.a););(._;>;<;>;);out center meta;'\
			 % (municipality_id)
	request = urllib.request.Request(overpass_api + "?data=" + urllib.parse.quote(query), headers=request_header)
	file = urllib.request.urlopen(request)
	data = json.load(file)
	file.close()
	osm_elements = data['elements']

	# Identify members of relations, to exclude from building matching

	relation_members = set()
	for element in osm_elements:
		if element['type'] == "relation":
			for member in element['members']:
				relation_members.add(member['ref'])  # OSM id of element

	# Create dict of nodes + list of buildings (ways tagged with building=*)

	for element in osm_elements:
		if element['type'] == "node":
			osm_nodes[ element['id'] ] = element
			element['used'] = 0

		elif element['type'] == "way":
			if "tags" in element and \
					"building" in element['tags'] and \
					"building:part" not in element['tags'] and \
					len(element['nodes']) > 2 and element['nodes'][0] == element['nodes'][-1] and \
					not element['id'] in relation_members:
				osm_buildings.append(element)
			else:
				for node_ref in element['nodes']:
					if node_ref in osm_nodes:
						osm_nodes[ node_ref ]['used'] += 1

	# Add polygon center and area

	tag_count = 0
	for building in osm_buildings:
		if "center" in building:
			building['center'] = (building['center']['lon'], building['center']['lat'])

		if building['type'] == "way":
			line = []
			for node_ref in building['nodes']:
				if node_ref in osm_nodes:
					line.append((osm_nodes[ node_ref ]['lon'], osm_nodes[ node_ref ]['lat']))
#				if node_ref in osm_nodes:
					osm_nodes[ node_ref ]['used'] += 1
			building['polygon'] = line
			building['area'] = abs(polygon_area(line))

			for tag in building['tags']:
				if tag not in ["building", "source"] and "addr:" not in tag:
					building['tagged'] = True
			if "tagged" in building:
				tag_count += 1

			if debug:
				building['tags']['AREA'] = str(building['area'])

	message ("\t%i buildings loaded (%i elements)\n" % (len(osm_buildings), len(osm_elements)))
	message ("\t%i buildings with tags other than building=*\n" % tag_count)



# Create new node with given tag
# Used for debugging centers

def add_node(node, tag):

	global osm_id

	osm_id -= 1

	node_element = {
		'type': 'node',
		'id': osm_id,
		'lat': node[1],
		'lon': node[0],
		'tags': tag
	}

	osm_elements.append(node_element)



# Create new way element for OSM

def add_way(coordinates, osm_element):

	global osm_id

	way_element = {
		'type': 'way',
		'nodes': [],
		'tags': {}
	}

	for node in coordinates:

		node_tuple = (node[0], node[1])

		# Either reuse node alreadyimported
		if node_tuple in import_nodes:
			node_id = import_nodes[ node_tuple ]['id']

		# Or create new node
		else:
			osm_id -= 1
			node_id = osm_id
			node_element = {
				'type': 'node',
				'id': node_id,
				'lat': node[1],
				'lon': node[0],
				'tags': {}
			}
			osm_elements.append(node_element)
			import_nodes[ node_tuple ] = node_element
		
		way_element['nodes'].append(node_id)

	if osm_element is None:
		osm_id -= 1
		way_element['id'] = osm_id
		osm_elements.append(way_element)

	else:
		# Delete old nodes if not used anymore, and replace with new nodes

		for node_ref in osm_element['nodes']:
			if node_ref in osm_nodes:
				osm_nodes[ node_ref ]['used'] -= 1
				if osm_nodes[ node_ref ]['used'] == 0 and "tags" not in osm_nodes[ node_ref ]:
					osm_nodes[ node_ref ]['action'] = "delete"

		osm_element['nodes'] = way_element['nodes']
		way_element = osm_element

	return way_element



def add_building(building, osm_element):

	global osm_id

	if building['geometry']['type'] == "Point":
		return

	# Simple polygon

	elif len(building['geometry']['coordinates']) == 1:
		way_element = add_way(building['geometry']['coordinates'][0], osm_element)

		if osm_element is not None and way_element['tags']['building'] != "yes" and \
				way_element['tags']['building'] != building['properties']['building'] and \
			 	not (way_element['tags']['building'] in similar_buildings['residential'] and \
			 		building['properties']['building'] in similar_buildings['residential']) and \
			 	not (way_element['tags']['building'] in similar_buildings['commercial'] and \
			 		building['properties']['building'] in similar_buildings['commercial']) and \
			 	not (way_element['tags']['building'] in similar_buildings['farm'] and \
			 		building['properties']['building'] in similar_buildings['farm']):

			way_element['tags']['OSM_BUILDING'] = way_element['tags']['building']

		for tag in ["building:type", "source", "source:date"] or \
				remove_addr and tag in ["addr:street", "addr:housenumber", "addr:city", "addr:country", "addr:place"]:
			if tag in way_element['tags']:
				del way_element['tags'][ tag ]

		way_element['tags'].update(building['properties'])  # If merge, update old tags
		way_element['center'] = building['center']
		way_element['area'] = building['area']
		
		if osm_element is not None:
			way_element['action'] = "modify"

#		centroid = polygon_centroid(building['geometry']['coordinates'][0])
#		add_node(centroid, {'CENTROID': "yes"})

	# Multipolygon

	else:
		relation_element = {
			'type': 'relation',
			'members': [],
			'tags': building['properties']
		}
		relation_element['tags']['type'] = "multipolygon"

		role = "outer"

		for patch in building['geometry']['coordinates']:
			way_element = add_way(patch, None)
			member = {
				'type': 'way',
				'ref': way_element['id'],
				'role': role
			}
			relation_element['members'].append(member)
			role = "inner"  # Next patch

		osm_id -= 1
		relation_element['id'] = osm_id
		osm_elements.append(relation_element)



# Do reverse match to verify that two buildings are each others' best match

def reverse_match(import_building):

	found_building = None
	best_diff = 9999  # Dummy

	min_bbox = coordinate_offset(import_building['center'], - 2 * margin_hausdorff) #import_building['area'])
	max_bbox = coordinate_offset(import_building['center'], + 2 * margin_hausdorff) #import_building['area'])

	for osm_building in osm_buildings:

		if "area" in osm_building and "ref:bygningsnr" not in osm_building['tags'] and \
					min_bbox[0] < osm_building['center'][0] < max_bbox[0] and \
					min_bbox[1] < osm_building['center'][1] < max_bbox[1]:  # and "action" not in osm_building and \

			diff_haus = hausdorff_distance(import_building['geometry']['coordinates'][0], osm_building['polygon'])
				
			if diff_haus < best_diff:
				found_building = osm_building
				best_diff = diff_haus

	return (found_building, best_diff)



# Merge import with OSM buildings

def merge_buildings():

	message ("Merging buildings ...\n")
	message ("\tMaximum Hausdorff difference: %i m (%i m for tagged buildings)\n" % (margin_hausdorff, margin_tagged))
	message ("\tMaximum area difference: %i %%\n" % (margin_area * 100))

	count = len(osm_buildings)
	count_merge = 0
	count_ref = 0

	# Remove import buildings which have already been imported

	import_refs = {}
	for import_building in import_buildings:
		import_refs[ import_building['properties']['ref:bygningsnr'] ] = import_building

	for osm_building in osm_buildings:
		if "ref:bygningsnr" in osm_building['tags']:
			for ref in osm_building['tags']['ref:bygningsnr'].split(";"):
				if ref in import_refs:
					import_buildings.remove(import_refs[ref])

	# Loop osm buildings and attempt to find matching import buildings

	for osm_building in osm_buildings[:]:
		count -= 1
		message ("\r\t%i " % count)
		found_building = None
		best_diff = 9999  # Dummy

		# Skip test if ref:bygningsnr exists (building has already been imported)

		if "ref:bygningsnr" in osm_building['tags']:
			count_ref += 1
			continue

		# Get bbox for limiting search below

		min_bbox = coordinate_offset(osm_building['center'], - 2 * margin_hausdorff) # osm_building['area'])
		max_bbox = coordinate_offset(osm_building['center'], + 2 * margin_hausdorff) # osm_building['area'])

		for import_building in import_buildings:

			if "area" in import_building and \
					min_bbox[0] < import_building['center'][0] < max_bbox[0] and \
					min_bbox[1] < import_building['center'][1] < max_bbox[1]:

				# Calculate Hausdorff distance to identify building with shortest distance
				diff_haus = hausdorff_distance(osm_building['polygon'], import_building['geometry']['coordinates'][0])
	
				if diff_haus < best_diff:
					found_building = import_building
					best_diff = diff_haus

		if found_building is not None:
			if debug:
				osm_building['tags']['HAUSDORFF'] = " %.2f" % best_diff

			# Also check if Hausdorff distance is within given limit (shorter limit for tagged buildings)
			if best_diff < margin_hausdorff and "tagged" not in osm_building or best_diff < margin_tagged:

				# Also check if both buildings are each others best match
				found_reverse, reverse_haus = reverse_match(found_building)

				if found_reverse == osm_building and reverse_haus < margin_hausdorff:

					# Buildings 
					if margin_area < osm_building['area'] / found_building['area'] < 1.0 / margin_area:

						add_building(found_building, osm_building)
						import_buildings.remove(found_building)
						count_merge += 1
					elif debug:
						osm_building['tags']['SIZE'] = "%.1f" % (osm_building['area'] / found_building['area'])

	# Add remaining import buildings which were not matched

	count_add = 0
	for building in import_buildings:
		if building['geometry']['type'] == "Polygon":
			add_building(building, None)
			count_add += 1

	message ("\r\tMerged %i buildings from OSM (%i%%)\n" % (count_merge, 100.0 * count_merge / len(osm_buildings)))
	if count_ref > 0:
		message ("\tSkipped %i already imported buildings in OSM (%i%%)\n" % (count_ref, 100.0 * count_ref / len(osm_buildings)))
	message ("\tRemaining %i buildings from OSM not merged (%i%%)\n" % \
		(len(osm_buildings) - count_merge - count_ref, 100 - 100.0 * (count_merge + count_ref) / len(osm_buildings)))
	message ("\tAdded %i new buildings from import file\n" % count_add)



# Indent XML output

def indent_tree(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent_tree(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i



# Generate one osm tag for output

def tag_property (osm_element, tag_key, tag_value):

	tag_value = tag_value.strip()
	if tag_value:
		osm_element.append(ET.Element("tag", k=tag_key, v=tag_value))



def set_attributes (element, data):

	if "user" in data:
		element.set('version', str(data['version']))
		element.set('user', data['user'])
		element.set('uid', str(data['uid']))
		element.set('timestamp', data['timestamp'])
		element.set('changeset', str(data['changeset']))
		element.set('visible', 'true')
		if "action" in data:
			element.set('action', data['action'])
	else:
		element.set('action', 'modify')
		element.set('visible', 'true')



# Output result

def save_file(filename):

	message ("Saving file ...\n")
	message ("\tFilename '%s'\n" % filename)

	count = 0
	osm_root = ET.Element("osm", version="0.6", generator="building_merge", upload="false")

	# First output all start/end nodes

	for element in osm_elements:

		if element['type'] == "node":
			osm_node = ET.Element("node", id=str(element['id']), lat=str(element['lat']), lon=str(element['lon']))
			set_attributes(osm_node, element)
			osm_root.append(osm_node)
			count += 1
			if "tags" in element:
				for key, value in iter(element['tags'].items()):
					tag_property (osm_node, key, value)

		elif element['type'] == "way":
			osm_way = ET.Element("way", id=str(element['id']))
			set_attributes(osm_way, element)
			osm_root.append(osm_way)
			count += 1

			if "tags" in element:
				for key, value in iter(element['tags'].items()):
					tag_property (osm_way, key, value)
		
			for node_ref in element['nodes']:
				osm_way.append(ET.Element("nd", ref=str(node_ref)))

		elif element['type'] == "relation":
			osm_relation = ET.Element("relation", id=str(element['id']))
			set_attributes(osm_relation, element)
			osm_root.append(osm_relation)
			count += 1

			if "tags" in element:
				for key, value in iter(element['tags'].items()):
					tag_property (osm_relation, key, value)

			for member in element['members']:
				osm_relation.append(ET.Element("member", type=member['type'], ref=str(member['ref']), role=member['role']))
		
	# Produce OSM/XML file

	osm_tree = ET.ElementTree(osm_root)
	indent_tree(osm_root)
	osm_tree.write(filename, encoding="utf-8", method="xml", xml_declaration=True)

	message ("\t%i elements saved\n" % count)


# Main program

if __name__ == '__main__':

	start_time = time.time()
	message ("\n*** building_merge %s ***\n\n" % version)

	municipalities = {}
	import_buildings = []
	osm_buildings = []
	osm_elements = []
	import_nodes = {}
	osm_nodes = {}
	osm_id = -1000

	# Parse parameters

	if len(sys.argv) < 2:
		message ("Please provide municipality number or name\n\n")
		sys.exit()

	if len(sys.argv) > 2 and sys.argv[2].isdigit():
		margin_hausdorff = int(sys.argv[2])
		margin_tagged = margin_hausdorff * 0.5

	if "-debug" in sys.argv:
		debug = True

	# Get municipality

	load_municipalities()
	municipality_query = sys.argv[1]
	municipality_id = get_municipality(municipality_query)
	if municipality_id is None or municipality_id not in municipalities:
		sys.exit("Municipality '%s' not found\n" % municipality_query)
	
	message ("Municipality: %s %s\n\n" % (municipality_id, municipalities[ municipality_id ]))

	# Get filename

	filename = "bygninger_%s_%s.geojson" % (municipality_id, municipalities[ municipality_id ].replace(" ", "_"))

	for arg in sys.argv[2:]:
		if ".geojson" in arg:
			filename = arg

	# Process

	load_import_buildings(filename)
	load_osm_buildings(municipality_id)

	if len(import_buildings) > 0 and len(osm_buildings) > 0:
		merge_buildings()

	filename = filename.replace(".geojson", "") + "_merged.osm"
	save_file(filename)

	used_time = time.time() - start_time
	message("Done in %s (%i buildings per second)\n\n" % (timeformat(used_time), len(osm_buildings) / used_time))
