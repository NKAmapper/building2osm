#!/usr/bin/env python3
# -*- coding: utf8

# progress_update
# Generates wiki progress page content, to be copied to wiki


import json
import sys
import time
import urllib.request
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup


version = "0.1.0"

request_header = {"User-Agent": "osmno/buildings2osm"}

sleep_time = 1000  # Number of buildings per 1 second sleep time before Overpass requests



# Output message to console

def message (text):

	sys.stderr.write(text)
	sys.stderr.flush()



# Open file/api, try up to 5 times, each time with double sleep time

def try_urlopen (url, header):

	request = urllib.request.Request(url, headers=header)

	delay = 60  # seconds
	tries = 0
	while tries < 5:
		try:
			return urllib.request.urlopen(request)
		except urllib.error.HTTPError as e:
			if e.code in [429, 503, 504]:  # Too many requests, Service unavailable or Gateway timed out
				if tries  == 0:
					message ("\n") 
				message ("\rRetry %i in %ss... " % (tries + 1, delay * (2**tries)))
				time.sleep(delay * (2**tries))
				tries += 1
			elif e.code in [401, 403]:
				message ("\nHTTP error %i: %s\n" % (e.code, e.reason))  # Unauthorized or Blocked
				sys.exit()
			elif e.code in [400, 409, 412]:
				message ("\nHTTP error %i: %s\n" % (e.code, e.reason))  # Bad request, Conflict or Failed precondition
				message ("%s\n" % str(e.read()))
				sys.exit()
			else:
				raise

		except urllib.error.URLError as e:  # Mostly "Connection timed out"
			if tries  == 0:
				message ("\n") 
			message ("\r\tRetry %i in %ss... " % (tries + 1, delay * (2**tries)))
			time.sleep(delay * (2**tries))
			tries += 1
	
	message ("\nError: %s\n" % e.reason)
	sys.exit()



# Load table from progress page

def load_progress_page():

	message ("\nLoading wiki progress page ...\n")

	url = "https://wiki.openstreetmap.org/wiki/Import/Catalogue/Norway_Building_Import/Progress"

	request = urllib.request.Request(url, headers=request_header)
	page = urllib.request.urlopen(request)
	storesoup = BeautifulSoup(page, features="html.parser")
	page.close()

	content = storesoup.find(class_="mw-parser-output")
	table = content.find("table").find("tbody").find_all("tr")

	for row in table[2:]:
		cols = row.find_all('td')
		cols = [ele.text.strip() for ele in cols]

		if not cols[3]:
			cols[3] = "0"
		if not cols[4]:
			cols[4] = "0"
		if not cols[5]:
			cols[5] = "0"

		if cols and cols[0] != "9999":
			municipalities[ cols[0] ] = {
				'name': cols[1],
				'county': cols[2],
				'import_buildings': int(float(cols[3].replace(" ", ""))),
				'osm_buildings': int(float(cols[4].replace(" ", ""))),
				'ref_progress': int(float(cols[5].strip("%").replace(" ", ""))),
				'user': cols[6],
				'status': cols[7] 
			}

	message ("\t%i municipalities\n" % len(municipalities))



# Get buildings from cadastral registry.

def count_import_buildings():

	message ("\nLoading buildings from cadastral registry ...\n")

	# Namespace

	ns_gml = 'http://www.opengis.net/gml/3.2'
	ns_app = 'http://skjema.geonorge.no/SOSI/produktspesifikasjon/Matrikkelen-Bygningspunkt'

	ns = {
			'gml': ns_gml,
			'app': ns_app
	}

	total_count = 0

	for municipality_id, municipality in municipalities.items():

		message ("\t%-20s " % municipality['name'])

		# Load file from GeoNorge

		url = "https://nedlasting.geonorge.no/geonorge/Basisdata/MatrikkelenBygning/GML/Basisdata_%s_%s_25833_MatrikkelenBygning_GML.zip" \
				% (municipality_id, municipality['name'])
		url = url.replace("Æ","E").replace("Ø","O").replace("Å","A").replace("æ","e").replace("ø","o").replace("å","a").replace(" ", "_")

		in_file = urllib.request.urlopen(url)
		zip_file = zipfile.ZipFile(BytesIO(in_file.read()))

		if len(zip_file.namelist()) == 0:
			message ("*** No data\n")
			continue

		filename = zip_file.namelist()[0]
		file = zip_file.open(filename)

		tree = ET.parse(file)
		file.close()
		root = tree.getroot()
		count = 0

		# Count number of import buildings and compare with last update

		for feature in root.iter('{%s}featureMember' % ns_gml):
			count += 1

		message ("{:,}".format(count).replace(',', ' '))
		if count != municipality['import_buildings']:
			message ("  --> %i" % (count - municipality['import_buildings']))
		message ("\n")

		municipality['import_buildings'] = count
		total_count += count

	message ("\tTotal %i cadastral buildings in Norway\n" % total_count)



# Load count of existing buildings from OSM Overpass

def count_osm_buildings():

	message ("\nLoading existing buildings from OSM ...\n")

	total_count = 0

	for municipality_id, municipality in municipalities.items():

		message ("\t%-20s " % municipality['name'])

		# Get number of buildings

		query = '[out:json][timeout:60];(area[ref=%s][admin_level=7][place=municipality];)->.a;(nwr["building"](area.a););out count;' \
			 	% municipality_id

		url = "https://overpass-api.de/api/interpreter?data=" + urllib.parse.quote(query)
		file = try_urlopen(url, request_header)
		data = json.load(file)
		file.close()

		count = data['elements'][0]['tags']
		count_buildings = int(count['ways']) + int(count['relations'])
		municipality['osm_buildings'] = count_buildings
		total_count += count_buildings

		message ("%-6s " % count_buildings)

		time.sleep(20 + count_buildings / sleep_time)

		# Get number of ref:byningsnr tags

		query = '[out:json][timeout:60];(area[ref=%s][admin_level=7][place=municipality];)->.a;(nwr["ref:bygningsnr"](area.a););out count;' \
			 	% municipality_id

		url = "https://overpass-api.de/api/interpreter?data=" + urllib.parse.quote(query)
		file = try_urlopen(url, request_header)
		data = json.load(file)
		file.close()

		count_tags = int(data['elements'][0]['tags']['total'])
		message ("%6i %3i%%" % (count_tags, 100.0 * count_tags / municipality['import_buildings']))

		municipality['ref_progress'] = 100.0 * count_tags / municipality['import_buildings']

		# Compare with last update

		if count_buildings != municipality['osm_buildings']:
			message ("  --> %i" % (count_buildings - municipality['osm_buildings']))
		message ("\n")

		time.sleep(20 + count_buildings / sleep_time)

	message ("\tTotal %i OSM buildings in Norway\n" % total_count)



# Output summary in format suitable for updating wiki page

def output_file():

	message ("\nSummary\n")

	osm_count = 0
	import_count = 0

	filename = "import_progress.txt"
	file = open(filename, "w")

	for municipality_id, municipality in municipalities.items():

		message("\t%s %-15s %-20s %6i %6i %3i%% %-10s %-10s\n" % (municipality_id, municipality['name'], municipality['county'], \
			municipality['import_buildings'], municipality['osm_buildings'], municipality['ref_progress'], \
			municipality['user'], municipality['status']))

		file.write("|-\n")
		file.write("|%s\n" % municipality_id)
		file.write("|%s\n" % municipality['name'])
		file.write("|%s\n" % municipality['county'])		
		file.write("|%s\n" % "{:,}".format(municipality['import_buildings']).replace(',', ' '))
		file.write("|%s\n" % "{:,}".format(municipality['osm_buildings']).replace(',', ' '))
		file.write("|%i%%\n" % municipality['ref_progress'])
		file.write("|%s\n" % municipality['user'])
		file.write("|%s\n" % municipality['status'])	

		import_count += municipality['import_buildings']
		osm_count += municipality['osm_buildings']

	message ("\t%-41s %6i %6i\n\n" % ("Total in Norway", import_count, osm_count))
	message ("\nFile saved to '%s'\n\n" % filename)

	file.close()



# Main program

if __name__ == '__main__':

	municipalities = {}

	load_progress_page()

	count_import_buildings()
	count_osm_buildings()

	output_file()
