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
# Faster alternative to https://overpass-api.de/api/interpreter
overpass_instance = "https://overpass.kumi.systems/api/interpreter"


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
				if tries == 0:
					message("\n")
				message(f"\rRetry {tries + 1:d} in {delay * (2 ** tries)}s... ")
				time.sleep(delay * (2**tries))
				tries += 1
			elif e.code in [401, 403]:
				message(f"\nHTTP error {e.code:d}: {e.reason}\n")  # Unauthorized or Blocked
				sys.exit()
			elif e.code in [400, 409, 412]:
				message(f"\nHTTP error {e.code:d}: {e.reason}\n")  # Bad request, Conflict or Failed precondition
				message(f"{str(e.read())}\n")
				sys.exit()
			else:
				raise

		except urllib.error.URLError as e:  # Mostly "Connection timed out"
			if tries == 0:
				message("\n")
			message(f"\r\tRetry {tries + 1:d} in {delay * (2 ** tries)}s... ")
			time.sleep(delay * (2**tries))
			tries += 1

	message(f"\nError: {e.reason}\n")
	sys.exit()



# Load table from progress page

def load_progress_page():

	message("\nLoading wiki progress page ...\n")

	url = "https://wiki.openstreetmap.org/wiki/Import/Catalogue/Norway_Building_Import/Progress"

	request = urllib.request.Request(url, headers=request_header)
	page = urllib.request.urlopen(request)
	storesoup = BeautifulSoup(page, features="html.parser")
	page.close()

	content = storesoup.find(class_="mw-parser-output")
	table = content.find("table").find("tbody").find_all("tr", recursive=False)

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

	message(f"\t{len(municipalities):d} municipalities\n")

	for city_id, has_id in [("0301", True), ("4601", False)]:
		city_name = municipalities[city_id]["name"]
		municipalities[city_id]["subdiv"] = []
		table = content.select_one(f'h2:-soup-contains("{city_name}") + table').find("tbody").find_all("tr", recursive=False)

		for row in table[1:]:
			cols = row.find_all('td')
			cols = [ele.text.strip() for ele in cols]

			if not cols[1 + has_id]:
				cols[1 + has_id] = "0"

			subdiv = {
				'name': cols[0 + has_id],
				'osm_buildings': int(cols[1 + has_id].replace(" ", "")),
				'user': cols[2 + has_id],
				'status': cols[3 + has_id]
			}
			if has_id:
				subdiv['id'] = cols[0]

			municipalities[city_id]["subdiv"].append(subdiv)


# Get buildings from cadastral registry.

def count_import_buildings():

	message("\nLoading buildings from cadastral registry ...\n")

	# Namespace

	ns_gml = 'http://www.opengis.net/gml/3.2'
	ns_app = 'http://skjema.geonorge.no/SOSI/produktspesifikasjon/Matrikkelen-Bygningspunkt'

	ns = {
			'gml': ns_gml,
			'app': ns_app
	}

	total_count = 0

	for municipality_id, municipality in municipalities.items():

		message(f"\t{municipality['name']:<20} ")

		# Load file from GeoNorge

		url = f"https://nedlasting.geonorge.no/geonorge/Basisdata/MatrikkelenBygning/GML/Basisdata_{municipality_id}_{municipality['name']}_25833_MatrikkelenBygning_GML.zip"
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

		message(f"{count:,}".replace(',', ' '))
		if count != municipality['import_buildings']:
			message(f"  ⟶ {count - municipality['import_buildings']:d}")
		message("\n")

		municipality['import_buildings'] = count
		total_count += count

	message(f"\tTotal {total_count:d} cadastral buildings in Norway\n")



# Load count of existing buildings from OSM Overpass

def count_osm_buildings():

	message("\nLoading existing buildings from OSM ...\n")

	total_count = 0

	for municipality_id, municipality in municipalities.items():

		message(f"\t{municipality['name']:<20} ")

		# Get number of buildings

		query = f'[out:json][timeout:60];(area[ref={municipality_id}][admin_level=7][place=municipality];)->.a;(nwr["building"](area.a););out count;'

		url = f'{overpass_instance}?data={urllib.parse.quote(query)}'
		with try_urlopen(url, request_header) as file:
			data = json.load(file)

		count = data['elements'][0]['tags']
		count_buildings = int(count['ways']) + int(count['relations'])
		total_count += count_buildings

		message(f"{count_buildings:<6} ")

		time.sleep(20 + count_buildings / sleep_time)

		# Get number of ref:byningsnr tags

		query = '[out:json][timeout:60];(area[ref=%s][admin_level=7][place=municipality];)->.a;(nwr["ref:bygningsnr"](area.a););out count;' \
			 	% municipality_id

		url = f'{overpass_instance}?data={urllib.parse.quote(query)}'
		with try_urlopen(url, request_header) as file:
			data = json.load(file)

		count_tags = int(data['elements'][0]['tags']['total'])
		municipality['ref_progress'] = 100 * count_tags / municipality['import_buildings']

		message(f"{count_tags:6d} {int(municipality['ref_progress']):3d}%")

		# Compare with last update

		if count_buildings != municipality['osm_buildings']:
			message(f"  ⤍ {count_buildings - municipality['osm_buildings']:d}")
		message("\n")

		municipality['osm_buildings'] = count_buildings

		if "subdiv" in municipality:
			for subdiv in municipality["subdiv"]:
				time.sleep(5 + count_buildings / sleep_time)

				message(f'\t\tBydel {subdiv["name"]:<20}')
				query = f'[out:json][timeout:60];(area[name="{subdiv["name"]}"][admin_level=9];)->.a;(nwr["building"](area.a););out count;'
				url = f'{overpass_instance}?data={urllib.parse.quote(query)}'
				with try_urlopen(url, request_header) as file:
					data = json.load(file)

				count = data['elements'][0]['tags']
				count_buildings = int(count['ways']) + int(count['relations'])

				message(f"{count_buildings:>7}")

				if count_buildings != subdiv['osm_buildings']:
					message(f"  --> {count_buildings - subdiv['osm_buildings']:d}")
				message("\n")

				subdiv['osm_buildings'] = count_buildings

	time.sleep(20 + count_buildings / sleep_time)

	message("\tTotal %i OSM buildings in Norway\n" % total_count)



# Output summary in format suitable for updating wiki page

def output_file():

	message ("\nSummary\n")

	osm_count = 0
	import_count = 0

	filename = "import_progress.txt"
	with open(filename, "w", encoding='utf-8') as file:

		for municipality_id, municipality in municipalities.items():

			message(f"\t{municipality_id} {municipality['name']:<15} {municipality['county']:<20} {municipality['import_buildings']:6d} {municipality['osm_buildings']:6d} {municipality['ref_progress']:3d}% {municipality['user']:<10} {municipality['status']:<10}\n")

			file.write("|-\n")
			file.write(f"|{municipality_id}\n")
			file.write(f"|{municipality['name']}\n")
			file.write(f"|{municipality['county']}\n")
			file.write(f"|{municipality['import_buildings']:,}\n".replace(',', ' '))
			file.write(f"|{municipality['osm_buildings']:,}\n".replace(',', ' '))
			file.write(f"|{municipality['ref_progress']:d}%\n")
			file.write(f"|{municipality['user']}\n")
			file.write(f"|{municipality['status']}\n")

			import_count += municipality['import_buildings']
			osm_count += municipality['osm_buildings']

			message(f"\t{'Total in Norway':<41} {import_count:6d} {osm_count:6d}\n\n")

		message(f"\nFile saved to '{filename}'\n\n")

		for city_id, city in filter(lambda m: "subdiv" in m[1], municipalities.items()):
			filename = f"import_progress_{city['name']}.txt"
			with open(filename, "w", encoding='utf-8') as file:

				for subdiv in city["subdiv"]:
					file.write("|-\n")
					if 'id' in subdiv:
						file.write(f"|{subdiv['id']}\n")
					file.write(f"|{subdiv['name']}\n")
					file.write(f"|{subdiv['osm_buildings']:,}\n".replace(',', ' '))
					file.write(f"|{subdiv['user']}\n")
					file.write(f"|{subdiv['status']}\n")


			message(f"\nFile saved to '{filename}'\n\n")



# Main program

if __name__ == '__main__':

	municipalities = {}

	load_progress_page()

	count_import_buildings()
	count_osm_buildings()

	output_file()
