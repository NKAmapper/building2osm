#!/usr/bin/env python3
# -*- coding: utf8

# buildings2osm
# Converts buildings from the Norwegian cadastral registry to geosjon file for import to OSM.
# Usage: buildings2osm.py <municipality name> [-original] [-verify] [-debug]
# Creates geojson file with name "bygninger_4222_Bykle.osm" etc.


import sys
import time
import copy
import math
import statistics
import csv
import json
import urllib.request
import zipfile
from io import TextIOWrapper
from io import BytesIO
from xml.etree import ElementTree as ET
import utm  # From building2osm on GitHub


version = "0.2.1"

verbose = False				# Provides extra messages about polygon loading

debug = False				# Add debugging / testing information
verify = False				# Add tags for users to verify
original = False			# Output polygons as in original data (no rectification/simplification)

coordinate_decimals = 7

angle_margin = 8.0			# Max margin around angle limits, for example around 90 degrees corners (degrees)
short_margin = 0.20			# Min length of short wall which will be removed if on "straight" line (meters)
corner_margin = 1.0			# Max length of short wall which will be rectified even if corner is outside of 90 +/- angle_margin (meters)
rectify_margin = 0.2		# Max relocation distance for nodes during rectification before producing information tag (meters)

simplify_margin = 8.0		# Max angle for simplification, i.e. remove node (degrees)

curve_margin_max = 40		# Max angle for a curve (degrees)
curve_margin_min = 0.3		# Min agnle for a curve (degrees)
curve_margin_nodes = 3		# At least three nodes in a curve (number of nodes)

max_download = 10000		# Max features permitted for downloading by WFS per query


status_codes = {
	'RA': 'Rammetillatelse',
	'IG': 'Igangsettingstillatelse',
	'MB': 'Midlertidig brukstillatelse',
	'FA': 'Ferdigattest',
	'TB': 'Bygning er tatt i bruk',
	'MT': 'Meldingsak registrert',
	'MF': 'Meldingsak fullført',
	'GR': 'Bygning godkjent, revet eller brent',
	'IP': 'Ikke pliktig registrert',
	'FS': 'Fritatt for søknadsplikt'
}


# Output message to console

def message (text):

	sys.stderr.write(text)
	sys.stderr.flush()



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



# Calculate center of polygon, or of list of nodes

def polygon_center (polygon):

	length = len(polygon)
	if polygon[0] == polygon[-1]:
		length -= 1

	x = 0
	y = 0
	for node in polygon[:length]:
		x += node[0]
		y += node[1]
	return (x / length, y / length)



# Return bearing in degrees of line between two points (longitude, latitude)

def bearing (point1, point2):

	lon1, lat1, lon2, lat2 = map(math.radians, [point1[0], point1[1], point2[0], point2[1]])
	dLon = lon2 - lon1
	y = math.sin(dLon) * math.cos(lat2)
	x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dLon)
	angle = (math.degrees(math.atan2(y, x)) + 360) % 360
	return angle



# Return the difference between two bearings.
# Negative degrees to the left, positive to the right.

def bearing_difference (bearing1, bearing2):

	delta = (bearing2 - bearing1 + 360) % 360

	if delta > 180:
		delta = delta - 360

	return delta



# Return the shift in bearing at a junction.
# Negative degrees to the left, positive to the right. 

def bearing_turn (point1, point2, point3):

	bearing1 = bearing(point1, point2)
	bearing2 = bearing(point2, point3)

	return bearing_difference(bearing1, bearing2)



# Rotate point with specified angle around axis point.
# https://gis.stackexchange.com/questions/246258/transforming-data-from-a-rotated-pole-lat-lon-grid-into-regular-lat-lon-coordina

def rotate_node (axis, r_angle, point):

	r_radians = math.radians(r_angle)  # *(math.pi/180)

	tr_y = point[1] - axis[1]
	tr_x = (point[0] - axis[0]) * math.cos(math.radians(axis[1]))

	xrot = tr_x * math.cos(r_radians) - tr_y * math.sin(r_radians)  
	yrot = tr_x * math.sin(r_radians) + tr_y * math.cos(r_radians)

	xnew = xrot / math.cos(math.radians(axis[1])) + axis[0]
	ynew = yrot + axis[1]

	return (xnew, ynew)



# Parse WKT coordinates and return polygon list of (longitude, latitude).
# Omit equal coordinates in sequence.

def parse_polygon(coord_text):

	split_coord = coord_text.split(" ")
	coordinates = []
	last_node1 = (None, None)
	last_node2 = (None, None)
	for i in range(0, len(split_coord) - 1, 2):
		lon = float(split_coord[i])
		lat = float(split_coord[i+1])
		node = (lon, lat)
		if node != last_node1:
			if node == last_node2:
				coordinates.pop()
				last_node1 = last_node2
			else:
				coordinates.append(node)
		last_node2 = last_node1
		last_node1 = node

	return coordinates



# Load conversion CSV table for tagging building types.
# Format in CSV: "key=value + key=value + ..."

def load_building_types():

	url = "https://raw.githubusercontent.com/NKAmapper/building2osm/main/building_types.csv"
	file = urllib.request.urlopen(url)
	building_csv = csv.DictReader(TextIOWrapper(file, "utf-8"), fieldnames=["id", "name", "osm_tag"], delimiter=";")
	next(building_csv)

	for row in building_csv:
		osm_tag = { 'building': 'yes' }

		if row['osm_tag']:
			tag_list = row['osm_tag'].replace(" ","").split("+")
			for tag_part in tag_list:
				tag_split = tag_part.split("=")
				osm_tag[ tag_split[0] ] = tag_split[1]

		building_types[ row['id'] ] = {
			'name': row['name'],
			'tags': osm_tag
		}

	file.close()



# Identify municipality name, unless more than one hit
# Returns municipality number, or input paramter if not found

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



# Load building polygons from WFS within given BBOX.
# Note: Max 10.000 buildings will be returned from WFS. No paging provided.
# Data parsed as text lines for performance reasons (very simple data structure)

def load_building_coordinates(municipality_id, min_bbox, max_bbox, level):

	bbox_list = [str(min_bbox[1]), str(min_bbox[0]), str(max_bbox[1]), str(max_bbox[0])]

	url = "https://wfs.geonorge.no/skwms1/wfs.inspire-bu-core2d?" + \
			"service=WFS&version=2.0.0&request=GetFeature&&srsName=EPSG:4326&typename=Building&bbox=" + ",".join(bbox_list)
#	message ("\n\tQuery: %s\n\t" % url)
	file_in = urllib.request.urlopen(url)
	file = TextIOWrapper(file_in, "utf-8")

	count_feature = 0
	count_hits = 0
	hit = False

	for line in file:

		ref_index = line.find("<bu-base:reference>")
		if ref_index > 0:
			ref_end = line.find("<", ref_index + 19 )
			ref = line[ ref_index + 19 : ref_end ]

			coordinates = []
			count_feature += 1

			if ref in buildings:
				hit = True
				count_hits += 1
			else:
				hit = False

		ref_index = line.find("<gml:posList>")
		if ref_index > 0:
			ref_end = line.find("<", ref_index + 13 )
			geo = line[ ref_index + 13 : ref_end ]
			coordinates.append( parse_polygon(geo) )

		if "</wfs:member>" in line:
			if ref in buildings and coordinates:
				buildings[ref]['geometry']['type'] = "Polygon"
				buildings[ref]['geometry']['coordinates'] = coordinates

	file_in.close()

	if verbose:
		message ("Found %i, loaded %i buildings\n" % (count_hits, count_feature))

	# If returned number of buildings is close to max WFS limit, then reload using smaller BBOX

	count_load = 1
	if count_feature > max_download - 10:
		if verbose:
			message ("%s*** Too many buildings in box, force split box and reloading" % ("\t" * level))
		count_load += load_area(municipality_id, min_bbox, max_bbox, level, force_divide=True)
	elif not verbose:
		countdown = len(buildings) - sum((building['geometry']['type'] == "Polygon") for building in buildings.values())
		message ("\r\tLoading ... %6i " % countdown)
		
	return count_load



# Recursivly split municipality BBOX into smaller quadrants if needed to fit within WFS limit.

def load_area(municipality_id, min_bbox, max_bbox, level, force_divide):

	# How many buildings from municipality within bbox?
	count_load = 0
	inside_box = 0
	for building in buildings.values():
		if min_bbox[0] <= building['centroid'][0] <  max_bbox[0] and \
			min_bbox[1] <= building['centroid'][1] <  max_bbox[1]:
			inside_box += 1

	# How many buildings from neighbour municipalities within bbox?
	neighbour_inside_box = 0
	for building_node in neighbour_buildings:
		if min_bbox[0] <= building_node[0] <  max_bbox[0] and \
			min_bbox[1] <= building_node[1] <  max_bbox[1]:
			neighbour_inside_box += 1

	if verbose and not force_divide:
		message("%sExpecting %i buildings + %i neighbours ... " % ("\t" * level, inside_box, neighbour_inside_box))

	if inside_box == 0:
		if verbose:
			message ("\n")
		return count_load

	# Do actual loading of data
	elif inside_box + neighbour_inside_box < 0.95 * max_download and not force_divide:
		count_load += load_building_coordinates(municipality_id, min_bbox, max_bbox, level)

	else:
		# Split bbox to get fewer than 10.000 buildings within bbox
		if verbose:
			message ("\n%sSplit box\n" % ("\t" * level))

		if distance((min_bbox[0], max_bbox[1]), max_bbox) > distance(min_bbox, (min_bbox[0], max_bbox[1])):  # x longer than y
			# Split x axis
			half_x = 0.5 * (max_bbox[0] + min_bbox[0])
			count_load += load_area(municipality_id, min_bbox, (half_x, max_bbox[1]), level + 1, force_divide=False)
			count_load += load_area(municipality_id, (half_x, min_bbox[1]), max_bbox, level + 1, force_divide=False)
		else:
			# Split y axis
			half_y = 0.5 * (max_bbox[1] + min_bbox[1])
			count_load += load_area(municipality_id, min_bbox, (max_bbox[0], half_y), level + 1, force_divide=False)
			count_load += load_area(municipality_id, (min_bbox[0], half_y), max_bbox, level + 1, force_divide=False)

	return count_load



# Get municipality BBOX and kick off recursive splitting into smaller BBOX quadrants

def load_coordinates_municipality(municipality_id):

	message ("Load building polygons ...\n")
	message ("\tLoading ... %6i " % len(buildings))

	file = urllib.request.urlopen("https://ws.geonorge.no/kommuneinfo/v1/kommuner/" + municipality_id)
	data = json.load(file)
	file.close()
	bbox = data['avgrensningsboks']['coordinates'][0]

	count_load = load_area(municipality_id, bbox[0], bbox[2], 1, force_divide=False)  # Start with full bbox

	count_polygons = sum((building['geometry']['type'] == "Polygon") for building in buildings.values())
	message ("\r\tLoaded %i building polygons with %i load queries\n" % (count_polygons, count_load))



# Get info about buildings from cadastral registry.
# To aid data fetching of building polygons from WFS + to be merged with polygons later.
# Function can also load building info from neighbour municipalities, to aid bbox splitting when loading building polygons.

def load_building_info(municipality_id, municipality_name, neighbour):

	global max_download

	# Namespace

	ns_gml = 'http://www.opengis.net/gml/3.2'
	ns_app = 'http://skjema.geonorge.no/SOSI/produktspesifikasjon/Matrikkelen-Bygningspunkt'

	ns = {
			'gml': ns_gml,
			'app': ns_app
	}

	# Load file from GeoNorge

	url = "https://nedlasting.geonorge.no/geonorge/Basisdata/MatrikkelenBygning/GML/Basisdata_%s_%s_25833_MatrikkelenBygning_GML.zip" \
			% (municipality_id, municipality_name)
	url = url.replace("Æ","E").replace("Ø","O").replace("Å","A").replace("æ","e").replace("ø","o").replace("å","a").replace(" ", "_")

	if not neighbour:
		message ("Loading building information from cadastral registry ...\n")
#		message ("\tFile: %s\n" % url)

	in_file = urllib.request.urlopen(url)
	zip_file = zipfile.ZipFile(BytesIO(in_file.read()))

	# If building file is being updated at server, it will not be available
	if len(zip_file.namelist()) == 0:
		if neighbour:
			max_download = 0.5 * max_download  # Aim for less aggressive target since neighbour info will be incomplete
			return 0
		else:
			sys.exit("\n\n*** Building information for %s not available, please try later\n\n" % municipality_name)

	filename = zip_file.namelist()[0]
	file = zip_file.open(filename)

	tree = ET.parse(file)
	file.close()
	root = tree.getroot()
	count = 0

	not_found = []

	for feature in root.iter('{%s}featureMember' % ns_gml):

		count += 1
		building = feature.find('app:Bygning', ns)
		ref = building.find('app:bygningsnummer', ns).text

		position = building.find("app:representasjonspunkt/gml:Point/gml:pos", ns).text
		position_split = position.split()
		x, y = float(position_split[0]), float(position_split[1])
		[lat, lon] = utm.UtmToLatLon (x, y, 33, "N")  # Reproject from UTM to WGS84
		centroid = ( round(lon, coordinate_decimals), round(lat, coordinate_decimals) )

		if neighbour:
			neighbour_buildings.append(centroid)  # We only need center coordinates for neighbour municipalities
			continue

		building_type = building.find("app:bygningstype", ns).text
		building_status = building.find("app:bygningsstatus", ns).text
		source_date = building.find("app:oppdateringsdato", ns).text
		heritage = building.find("app:harKulturminne", ns).text

#		registration = building.find("app:opprinnelse", ns)  # Not useful
#		if registration is not None:
#			registration = registration.text

		sefrak = building.find("app:sefrakIdent/app:SefrakIdent", ns)
		if sefrak is not None:
			sefrak = "%s-%s-%s" % (sefrak.find("app:sefrakKommune", ns).text,
									sefrak.find("app:registreringskretsnummer", ns).text,
									sefrak.find("app:huslopenummer", ns).text)

		feature = {
			"type": "Feature",
			"geometry": {
				"type": "Point",
					"coordinates": centroid
			},
			"properties": {
				'ref:bygningsnr': ref,
				'TYPE': "#" + building_type,
				'STATUS': "#%s %s" % (building_status, status_codes[ building_status ]),
				'DATE': source_date[:10]
			},
			'centroid': centroid
		}

		if building_type in building_types:
			feature['properties']['TYPE'] = "#%s %s" % (building_type, building_types[ building_type ]['name'])
			feature['properties'].update(building_types[ building_type ]['tags'])

		elif building_type not in not_found:
			not_found.append(building_type)

		if heritage == "true":
			feature['properties']['heritage'] = "yes"

		if sefrak:
			feature['properties']['SEFRAK'] = sefrak

		if debug:
			feature['properties']['DEBUG_CENTROID'] = str(centroid[1]) + " " + str(centroid[0])

		buildings[ ref ] = feature

	if not neighbour:
		message("\tLoaded %i buildings\n" % count)
		if not_found:
			message ("\t*** Building type(s) not found: %s\n" % (", ".join(sorted(not_found))))

	return count


# Load center coordinate for all buildings in neighbour municipalities, to make bbox splitting more accurate when loading building polygons.

def load_neighbour_buildings(municipality_id):

	message ("Load building points for neighbour municipalities ...\n")

	# Load neighbour municipalities
	file = urllib.request.urlopen("https://ws.geonorge.no/kommuneinfo/v1/kommuner/" + municipality_id + "/nabokommuner")
	data = json.load(file)
	file.close()

	for municipality in data:
		message ("\tLoading %s ... " % municipality['kommunenavnNorsk'])
		count = load_building_info(municipality['kommunenummer'], municipality['kommunenavnNorsk'], neighbour=True)
		message ("loaded %i bulidings\n" % count)

	message ("\tLoaded %i neighbour building points for reference\n" % len(neighbour_buildings))



# Simplify polygon
# Remove non-essential nodes, i.e. nodes on (almost) staight lines

def simplify_polygons():

	message ("Simplify polygons ...\n")
	message ("\tSimplification factor: %i degrees\n" % simplify_margin)

	# Make dict of all nodes with count of usage

	count = 0
	nodes = {}
	for ref, building in iter(buildings.items()):
		if building['geometry']['type'] == "Polygon":
			for polygon in building['geometry']['coordinates']:
				for node in polygon[:-1]:
					if node not in nodes:
						nodes[ node ] = 1
					else:
						nodes[ node ] += 1
						count += 1

	message ("\t%i nodes used by more than one building\n" % count)

	# Identify non-essential nodes, i.e. nodes on a straight line

	count = 0
	for ref, building in iter(buildings.items()):
		if building['geometry']['type'] == "Polygon" and ("rectified" not in building or building['rectified'] == "no"):

			for polygon in building['geometry']['coordinates']:

				# First discover curved walls

				curves = set()
				curve = set()
				last_bearing = 0

				for i in range(1, len(polygon) - 1):
					new_bearing = bearing_turn(polygon[i-1], polygon[i], polygon[i+1])

					if math.copysign(1, last_bearing) == math.copysign(1, new_bearing) and curve_margin_min < abs(new_bearing) < curve_margin_max:
						curve.add(i - 1)
						curve.add(i)
						curve.add(i + 1)
					else:
						if len(curve) > curve_margin_nodes + 1:
							curves = curves.union(curve)
						curve = set()
					last_bearing = new_bearing

				if len(curve) > curve_margin_nodes + 1:
					curves = curves.union(curve)

				if curves:
					building['properties']['VERIFY_CURVE'] = str(len(curves))
					count += 1

				# Then identify non-essential nodes which are not part of curved walls.
				# Short segments may be removed with larger margins.

				last_node = polygon[-2]
				for i in range(len(polygon) - 1):
					angle = bearing_turn(last_node, polygon[i], polygon[i+1])
					length = distance(polygon[i], polygon[i+1])

					if i not in curves and \
							(abs(angle) < simplify_margin or \
							length < short_margin and \
								(abs(angle) < 40 or \
								abs(angle + bearing_turn(polygon[i], polygon[i+1], polygon[(i+2) % (len(polygon)-1)])) < simplify_margin) or \
							length < corner_margin and abs(angle) < 2 * simplify_margin):

						nodes[ polygon[i] ] -= 1
						if angle > simplify_margin - 2:
							building['properties']['VERIFY_SIMPLIFY'] = "%.1f" % abs(angle)
					else:
						last_node = polygon[i]

	message ("\tIdentified %i buildings with curved walls\n" % count)

	# Create set of nodes which may be deleted without conflicts

	already_removed = len(remove_nodes)
	for node in nodes:
		if nodes[ node ] == 0:
			remove_nodes.add(node)

	# Remove nodes from polygons

	count_building = 0
	count_remove = 0
	for ref, building in iter(buildings.items()):
		if building['geometry']['type'] == "Polygon":
			removed = False
			for polygon in building['geometry']['coordinates']:
				for node in polygon[:-1]:
					if node in remove_nodes:
						i = polygon.index(node)
						polygon.pop(i)
						count_remove += 1
						removed = True
						if i == 0:
							polygon[-1] = polygon[0]
			if removed:
				count_building += 1

	message ("\tRemoved %i redundant nodes in %i buildings\n" % (count_remove, count_building))



# Upddate corner dict

def update_corner(corners, wall, node, used):

	if node not in corners:
		corners[node] = {
			'used': 0,
			'walls': []
		}

	if wall:
		wall['nodes'].append(node)
		corners[node]['used'] += used
		corners[node]['walls'].append(wall)



# Make square corners if possible.
# Based on method used by JOSM:
#   https://josm.openstreetmap.de/browser/trunk/src/org/openstreetmap/josm/actions/OrthogonalizeAction.java
# The only input data required is the building dict, where each member is a standard geojson feature member.
# Supports single polygons, multipolygons (outer/inner) and group of connected buildings.

def rectify_polygons():

	message ("Rectify building polygons ...\n")
	message ("\tTreshold for square corners: 90 +/- %i degrees\n" % angle_margin)
	message ("\tMinimum length of wall: %.2f meters\n" % short_margin)

	# First identify nodes used by more than one way (usage > 1)

	count = 0
	nodes = {}
	for ref, building in iter(buildings.items()):
		if building['geometry']['type'] == "Polygon":
			for polygon in building['geometry']['coordinates']:
				for node in polygon[:-1]:
					if node not in nodes:
						nodes[ node ] = {
							'use': 1,
							'parents': [building]
						}
					else:
						nodes[ node ]['use'] += 1
						if building not in nodes[ node ]['parents']:
							nodes[ node ]['parents'].append( building )
						count += 1
			building['neighbours'] = [ building ]

	# Add list of neighbours to each building (other buildings which share one or more node)

	for node in nodes.values():
		if node['use'] > 1:
			for parent in node['parents']:
				for neighbour in node['parents']:
					if neighbour not in parent['neighbours']:
						parent['neighbours'].append(neighbour)  # Including self

	message ("\t%i nodes used by more than one building\n" % count)

	# Then loop buildings and rectify where possible.

	count_rectify = 0
	count_not_rectify = 0
	count_remove = 0
	count = 0

	for ref, building_test in iter(buildings.items()):

		count += 1
		message ("\r%i " % count)

		if building_test['geometry']['type'] != "Polygon" or "rectified" in building_test:
			continue

		# 1. First identify buildings which are connected and must be rectifed as a group

		building_group = []
		check_neighbours = building_test['neighbours']  # includes self
		while check_neighbours:
			for neighbour in check_neighbours[0]['neighbours']:
				if neighbour not in building_group and neighbour not in check_neighbours:
					check_neighbours.append(neighbour)
			building_group.append(check_neighbours[0])
			check_neighbours.pop(0)

		if len(building_group) > 1:
			building_test['properties']['VERIFY_GROUP'] = str(len(building_group)) 

		# 2. Then build data strucutre for rectification process.
		# "walls" will contain all (almost) straight segments of the polygons in the group.
		# "corners" will contain all the intersection points between walls.

		corners = {}
		walls = []
		conform = True  # Will be set to False if rectification is not possible

		for building in building_group:

			building['ways'] = []
			angles = []

			# Loop each patch (outer/inner polygon) of building separately
			for patch, polygon in enumerate(building['geometry']['coordinates']):

				if len(polygon) < 5 or polygon[0] != polygon[-1]:
					conform = False
					building['properties']['DEBUG_NORECTIFY'] = "No, only %i walls" % len(polygon)
					break

				# Build list of polygon with only square corners

				patch_walls = []
				wall = { 'nodes': [] }
				count_corners = 0
				last_corner = polygon[-2]  # Wrap polygon for first test

				for i in range(len(polygon) - 1):

					last_count = count_corners

					test_corner = bearing_turn(last_corner, polygon[i], polygon[i+1])
					angles.append("%i" % test_corner)
					short_length = min(distance(last_corner, polygon[i]), distance(polygon[i], polygon[i+1])) # Test short walls

					# Remove short wall if on (almost) straight line
					if distance(polygon[i], polygon[i+1]) < short_margin and \
							abs(test_corner + bearing_turn(polygon[i], polygon[i+1], polygon[(i+2) % (len(polygon)-1)])) < angle_margin and \
							nodes[ polygon[i] ]['use'] == 1:

						update_corner(corners, None, polygon[i], 0)
						building['properties']['VERIFY_SHORT_REMOVE'] = "%.2f" % distance(polygon[i], polygon[i+1])

					# Identify (almost) 90 degree corner and start new wall
					elif 90 - angle_margin < abs(test_corner) < 90 + angle_margin or \
							 short_length < corner_margin and 60 < abs(test_corner) < 120 and nodes[ polygon[i] ]['use'] == 1:
#							 45 - angle_margin < abs(test_corner) < 45 + angle_margin or \

						update_corner(corners, wall, polygon[i], 1)
						patch_walls.append(wall)  # End of previous wall, store it

						if short_length < 1 and not (90 - angle_margin < abs(test_corner) < 90 + angle_margin):
							building['properties']['VERIFY_SHORT_CORNER'] = "%.1f" % abs(test_corner)

						wall = { 'nodes': [] }  # Start new wall
						update_corner(corners, wall, polygon[i], 1)
						last_corner = polygon[i]
						count_corners += 1

					# Not possible to recitfy if wall is other than (almost) straight line
					elif abs(test_corner) > angle_margin:
						conform = False
						building['properties']['DEBUG_NORECTIFY'] = "No, %i degree angle" % test_corner
						last_corner = polygon[i]

					# Keep node if used by another building or patch
					elif nodes[ polygon[i] ]['use'] > 1: 
						update_corner(corners, wall, polygon[i], 0)
						last_corner = polygon[i]

					# Else throw away node (redundant node on (almost) straight line)
					else:
						update_corner(corners, None, polygon[i], 0)  # Node on "straight" line, will not be used

					# For debugging, mark cases where a slightly larger margin would have produced a rectified polygon
					if count_corners != last_count and not conform and 90 - angle_margin + 2 < abs(test_corner) < 90 + angle_margin + 2:
						building['properties']['DEBUG_MISSED_CORNER'] = str(int(abs(test_corner)))

				building['properties']['DEBUG_ANGLES'] = " ".join(angles)

				if count_corners % 2 == 1:  # Must be even number of corners
					conform = False
					building['properties']['DEBUG_NORECTIFY'] = "No, odd number %i" % count_corners

				elif conform:

					# Wrap from end to start
					patch_walls[0]['nodes'] = wall['nodes'] + patch_walls[0]['nodes']
					for node in wall['nodes']:
						wall_index = len(corners[node]['walls']) - corners[node]['walls'][::-1].index(wall) - 1  # Find last occurence
						corners[node]['walls'].pop(wall_index)  # remove(wall)
						if patch_walls[0] not in corners[node]['walls']:
							corners[node]['walls'].append(patch_walls[0])

					walls.append(patch_walls)

			if not conform and "DEBUG_NORECTIFY" not in building['properties']:
				building['properties']['DEBUG_NORECTIFY'] = "No"

		if not conform:
			for building in building_group:
				count_not_rectify += 1
				building['rectified'] = "no"  # Do not test again
			continue

		# 3. Remove unused nodes

		for node in list(corners.keys()):
			if corners[node]['used'] == 0:
				for patch in walls:
					for wall in patch:
						if node in wall['nodes']:
							wall['nodes'].remove(node)
				remove_nodes.add(node)
				del corners[node]
				count_remove += 1

		# 4. Get average bearing of all ways

		bearings = []
		group_bearing = 90.0  # For first patch in group, corresponding to axis 1
		group_axis = 1
#		diff_info = []

		for patch in walls:
			start_axis = None

			for i, wall in enumerate(patch):

				wall_bearing = bearing(wall['nodes'][0], wall['nodes'][-1])

				# Get axis for first wall, synced with group
				if start_axis is None:
					diff = (wall_bearing - group_bearing + 180) % 180
					if diff > 90:
						diff = diff - 180

					if abs(diff) < 45 and group_axis == 0:
						start_axis = group_axis  # Axis 1 (y axis)
					else:
						start_axis = 1 - group_axis  # Axis 0 (x axis)

#					diff_info.append("%i %i %i %i %i" % (group_bearing, wall_bearing, diff, group_axis, start_axis))

					if not bearings:
						group_axis = start_axis

				wall['axis'] = (i + start_axis) % 2

				if wall['axis'] == 0:					
					wall_bearing = wall_bearing % 180  # X axis
				else:
					wall_bearing = (wall_bearing + 90) % 180  # Turn Y axis 90 degrees 

				wall['bearing'] = wall_bearing
				bearings.append(wall_bearing)

			group_bearing = statistics.median_low(bearings)

		# Compute center for rotation, average of all corner nodes in cluster of buildings
		axis = polygon_center(list(corners.keys()))

		# Compute median bearing, by which buildings will be rotatatet

		if max(bearings) - min(bearings) > 90:
			for i, wall in enumerate(bearings):
				if 0 <= wall < 90:
					bearings[i] = wall + 180  # Fix wrap-around problem at 180

		avg_bearing = statistics.median_low(bearings)  # Use median to get dominant bearings

		building['properties']['DEBUG_BEARINGS'] = str([int(degree) for degree in bearings])
		building['properties']['DEBUG_AXIS'] = str([wall['axis'] for patch in walls for wall in patch ])
		building['properties']['DEBUG_BEARING'] = "%.1f" % avg_bearing

		# 5. Combine connected walls with same axis
		# After this section, the wall list in corners is no longer accurate

		copy_walls = copy.deepcopy(walls)
		walls = [wall for patch in walls for wall in patch]  # Flatten walls

		combine_walls = []  # List will contain all combinations of walls in group which can be combined

		for wall in walls:
			if any(wall in w for w in combine_walls):  # Avoid walls which are already combined
				continue

			# Identify connected walls with same axis
			connected_walls = []
			check_neighbours = [ wall ]  # includes self
			while check_neighbours:
				if check_neighbours[0]['axis'] == wall['axis']:
					for node in check_neighbours[0]['nodes']:
						for check_wall in corners[ node ]['walls']:
							if check_wall['axis'] == wall['axis'] and check_wall not in check_neighbours and check_wall not in connected_walls:
								check_neighbours.append(check_wall)
					connected_walls.append(check_neighbours[0])
					check_neighbours.pop(0)

			if len(connected_walls) > 1:
				combine_walls.append(connected_walls)

		if combine_walls:
			building_test['properties']['DEBUG_COMBINE'] = str([len(l) for l in combine_walls])

		# Combine nodes of connected walls into one remaining wall
		for combination in combine_walls:
			main_wall = combination[0]
			for wall in combination[1:]:
				main_wall['nodes'].extend(list(set(wall['nodes']) - set(main_wall['nodes'])))

		# 6. Rotate by average bearing

		for node, corner in iter(corners.items()):
			corner['new_node'] = rotate_node(axis, avg_bearing, node)

		# 7. Rectify nodes

		for wall in walls:

#			# Skip 45 degree walls
#			if 45 - 2 * angle_margin < (wall['bearing'] - avg_bearing) % 90 <  45 + 2 * angle_margin:  # 45 degree wall
#				building_test['properties']['TEST_45'] = "%.1f" % (wall['bearing'] - avg_bearing)
#				continue

			# Calculate x and y means of all nodes in wall
			x = statistics.mean([ corners[node]['new_node'][0] for node in wall['nodes'] ])
			y = statistics.mean([ corners[node]['new_node'][1] for node in wall['nodes'] ])

			# Align y and x coordinate for y and x axis, respectively
			for node in wall['nodes']:  
				if wall['axis'] == 1:
					corners[ node ]['new_node'] = ( corners[ node ]['new_node'][0], y)
				else:
					corners[ node ]['new_node'] = ( x, corners[ node ]['new_node'][1])

		# 8. Rotate back

		for node, corner in iter(corners.items()):
			corner['new_node'] = rotate_node(axis, - avg_bearing, corner['new_node'])
			corner['new_node'] = ( round(corner['new_node'][0], coordinate_decimals), round(corner['new_node'][1], coordinate_decimals) )

		# 9. Construct new polygons

		# Check if relocated nodes are off
		relocated = 0
		for building in building_group:
			for i, polygon in enumerate(building['geometry']['coordinates']):
				for node in polygon:
					if node in corners:
						relocated = max(relocated, distance(node, corners[node]['new_node']))

		if relocated  < rectify_margin:

			# Construct new polygons

			for building in building_group:
				relocated = 0
				for i, polygon in enumerate(building['geometry']['coordinates']):
					new_polygon = []
					for node in polygon:
						if node in corners:
							new_polygon.append(corners[node]['new_node'])
							relocated = max(relocated, distance(node, corners[node]['new_node']))
 
					if new_polygon[0] != new_polygon[-1]:  # First + last node were removed
						polygon.append(polygon[0])

					building['geometry']['coordinates'][i] = new_polygon

				building['rectified'] = "done"  # Do not test again
				building['properties']['DEBUG_RECTIFY'] = "%.2f" % relocated
				count_rectify += 1

				if relocated  > 0.5 * rectify_margin:
					building['properties']['VERIFY_RECTIFY'] = "%.1f" % relocated

		else:
			building_test['properties']['DEBUG_NORECTIFY'] = "Node relocated %.1f m" % relocated
			for building in building_group:
				building['rectified'] = "no"  # Do not test again

	message ("\r      \r")
	message ("\tRemoved %i redundant nodes in buildings\n" % count_remove)
	message ("\t%i buildings rectified\n" % count_rectify)
	message ("\t%i buildings could not be rectified\n" % count_not_rectify)



# Ouput geojson file

def save_file():

	filename = "bygninger_" + municipality_id + "_" + municipalities[municipality_id].replace(" ", "_") + ".geojson"
	if debug:
		filename = filename.replace(".geojson", "_debug.geojson")
	elif verify:
		filename = filename.replace(".geojson", "_verify.geojson")
	elif original:
		filename = filename.replace(".geojson", "_original.geojson")

	message ("Saving buildings ...\n")
	message ("\tFilename: '%s'\n" % filename)

	features = {
		"type": "FeatureCollection",
		"features": []
	}

	# Prepare buildings to fit geosjon data structure

	count = 0
	for ref, building in iter(buildings.items()):
		if building['geometry']['coordinates']:
			count += 1

			# Delete temporary data
			for key in list(building.keys()):
				if key not in ['type', 'geometry', 'properties']:
					del building[key]

			# Delete upper case debug tags		
			if not debug:
				for key in list(building['properties'].keys()):
					if key == key.upper() and key not in ['TYPE', 'STATUS', 'DATE'] and \
							not(verify and "VERIFY" in key)  and not(original and key == "SEFRAK"):
						del building['properties'][key]
			features['features'].append(building)

	# Add removed nodes, for debugging

	if debug or verify:
		for node in remove_nodes:
			feature = {
				'type': 'Feature',
				'geometry': {
					'type': 'Point',
					'coordinates': node
				},
				'properties': {
					'REMOVE': 'yes'
				}
			}
			features['features'].append(feature)

	file_out = open(filename, "w")
	json.dump(features, file_out, indent = 2)
	file_out.close

	message ("\tSaved %i buildings\n" % count)


# Main program

if __name__ == '__main__':

	start_time = time.time()
	message ("\n*** buildings2osm v%s\n\n" % version)

	municipalities = {}
	building_types = {}
	buildings = {}
	neighbour_buildings = []
	remove_nodes = set()


	# Parse parameters

	if len(sys.argv) < 2:
		message ("Please provide municipality number or name\n")
		message ("Options: -original, -verify, -debug\n\n")
		sys.exit()

	if "-debug" in sys.argv:
		debug = True
		verbose = True

	if "-verify" in sys.argv:
		verify = True

	if "-original" in sys.argv:
		original = True

	# Get selected municipality

	load_municipalities()
	municipality_query = sys.argv[1]
	municipality_id = get_municipality(municipality_query)
	if municipality_id is None or municipality_id not in municipalities:
		sys.exit("Municipality '%s' not found\n" % municipality_query)
	
	message ("Municipality: %s %s\n\n" % (municipality_id, municipalities[ municipality_id ]))

	# Process

	load_building_types()
	load_building_info(municipality_id, municipalities[municipality_id], neighbour=False)
	load_neighbour_buildings(municipality_id)
	load_coordinates_municipality(municipality_id)

	if not original:
		rectify_polygons()
		simplify_polygons()

	save_file()

	message("Done in %i seconds\n\n" % (time.time() - start_time))
