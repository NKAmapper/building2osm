#!/usr/bin/env python3
# -*- coding: utf8

# progress_update
# Generates wiki progress page content, to be copied to wiki
# Usage: progress_update.py [<sleep time>]


import json
import sys
import time
from datetime import date
import urllib.request
import zipfile
import os.path
from io import BytesIO
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup


version = "0.4.1"

request_header = {"User-Agent": "osmno/buildings2osm"}

sleep_time = 1  # Fixed sleep time after each Overpass request
buildings_per_second = 10000  # Number of buildings per 1 second sleep time before Overpass requests

# Faster alternative to https://overpass-api.de/api/interpreter
overpass_instance = "https://overpass.kumi.systems/api/interpreter"
#overpass_instance = "https://overpass-api.de/api/interpreter"

import_folder = "~/Jottacloud/osm/bygninger/"  # Folder containing import building files 

norway_id = "0000"



# Output message to console

def message(text):

	sys.stderr.write(text)
	sys.stderr.flush()



# Open file/api, try up to 5 times, each time with double sleep time

def try_urlopen(url, header):

	request = urllib.request.Request(url, headers=header)

	delay = 10  # seconds
	tries = 0
	while tries < 5:
		try:
			return urllib.request.urlopen(request)
		except urllib.error.HTTPError as e:
			if e.code in [429, 503, 504, 500]:  # Too many requests, Service unavailable or Gateway timed out + Internal server error
				if tries == 0:
					message("\n")
				message(f"\rRetry {tries + 1:d} in {delay * (2 ** tries):d}s... ")
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
			message(f"\r\tRetry {tries + 1:d} in {delay * (2 ** tries):d}s... ")
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
	table = content.find("caption", text="Import progress table - Municipalities\n").find_parent("table")
	table_rows = table.find("tbody").find_all("tr", recursive=False)[1:]  # [2:]

	for row in table_rows:
		cols = [
			ele.text.strip() if not (link := ele.next).name == 'a'
			else f'[[{link.attrs["title"]}|{link.text}]]'  # Link to userpage
			for ele in row.find_all('td')
		]

		for i in [3, 4]:
			if not cols[i]:
				cols[i] = "0"

		if cols[5].strip() == "":
			progress = 0
		elif "%" in cols[5]:
			progress = int(float(cols[5].strip("%").replace(" ", "")))
		else:
			progress = int(cols[5].split("|")[1].strip("}"))

		municipalities[cols[0]] = {
			'name': cols[1],
			'county': cols[2],
			'import_buildings': int(float(cols[3].replace(" ", ""))),
			'osm_buildings': int(float(cols[4].replace(" ", ""))),
			'ref_progress': progress,
			'ref_polygon_progress': 0,
			'user': cols[6].strip(),
			'status': cols[7]
		}

	message(f"\t{(len(municipalities)-1):d} municipalities\n")

	municipality_ids = {municipality["name"]: municipality_id for municipality_id, municipality in municipalities.items()}

	table = content.find("caption", text="Import progress table - Bydeler\n").find_parent("table")
	table_rows = table.find("tbody").find_all("tr", recursive=False)[1:]

	for row in table_rows:
		cols = [
			ele.text.strip() if not (link := ele.next).name == 'a'
			else f'[[{link.attrs["title"]}|{link.text}]]'  # Link to userpage
			for ele in row.find_all('td')
		]

		for i in [2, 3]:
			if not cols[i]:
				cols[i] = "0"

		if cols[4].strip() == "":
			progress = 0
		elif "%" in cols[4]:
			progress = int(float(cols[4].strip("%").replace(" ", "")))
		else:
			progress = int(cols[4].split("|")[1].strip("}"))

		subdivision = {
			'name': cols[1],
			'import_buildings': int(cols[2].replace(" ", "")),
			'osm_buildings': int(cols[3].replace(" ", "")),
			'ref_progress': progress,
			'ref_polygon_progress': 0,
			'user': cols[5].strip(),
			'status': cols[6]
		}

		city_id = municipality_ids[cols[0]]

		if "subdivision" in municipalities[city_id]:
			municipalities[city_id]["subdivision"].append(subdivision)
		else:
			municipalities[city_id]["subdivision"] = [subdivision]



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

		if municipality_id == norway_id:
			continue

		message(f"\t{municipality['name']:<20} ")

		# Load file from GeoNorge

		url = (
			"https://nedlasting.geonorge.no/geonorge/Basisdata/MatrikkelenBygning/GML/Basisdata_"
			f"{municipality_id}_{municipality['name']}_25833_MatrikkelenBygning_GML.zip"
		)
		url = url.replace("Æ", " E").replace("Ø", "O").replace(
			"Å", "A").replace("æ", "e").replace("ø", "o").replace("å", "a").replace(" ", "_")

		in_file = urllib.request.urlopen(url)
		zip_file = zipfile.ZipFile(BytesIO(in_file.read()))

		if len(zip_file.namelist()) == 0:
			message("*** No data\n")
			total_count += municipality['import_buildings']
			continue

		filename = zip_file.namelist()[0]
		file = zip_file.open(filename)

		tree = ET.parse(file)
		file.close()
		root = tree.getroot()
		count = 0

		# Count number of import buildings and compare with last update

		for _ in root.iter('{%s}featureMember' % ns_gml):
			count += 1

		message(f"{count:,}".replace(',', ' '))
		if count != municipality['import_buildings']:
			message(f"  -> {count - municipality['import_buildings']:d}")
		message("\n")

		municipality['import_buildings'] = count
		total_count += count

	message(f"\tTotal {total_count:d} cadastral buildings in Norway\n")

	municipalities[ norway_id ]['import_buildings'] = total_count  # Norway



# Get building polygons from stored files

def count_import_polygons():

	message("\nLoading buildings from OSM import files ...\n")	

	path = os.path.expanduser(import_folder)
	total_buildings = 0
	total_polygons = 0

	for municipality_id, municipality in municipalities.items():

		if municipality_id == norway_id:
			continue

		message(f"\t{municipality['name']:<20} ")

		# Load import file for municipality and count polygons

		filename = path + "bygninger_%s_%s.geojson" % (municipality_id, municipality['name'].replace(" ", "_"))

		if os.path.isfile(filename):
			file = open(filename)
			data = json.load(file)
			file.close()

			count = 0
			for building in data['features']:
				if building['geometry']['type'] != "Point":
					count += 1

			message(f"{count:6}\n")
			municipality['import_polygons'] = count
			total_polygons += count
			total_buildings += len(data['features'])

			# Load import files for boroughs and count polygons

			for subdivision in municipality.get("subdivision", []):

				message(f'\t\tBydel {subdivision["name"]:<20}')
				filename = path + "bygninger_%s_%s_bydel_%s.geojson" % (municipality_id, municipality['name'].replace(" ", "_"),
																subdivision['name'].replace(" ", "_"))
				if os.path.isfile(filename):
					file = open(filename)
					data = json.load(file)
					file.close()

					count = 0
					for building in data['features']:
						if building['geometry']['type'] != "Point":
							count += 1

					message(f"{count:6}\n")
					subdivision['import_polygons'] = count

				else:
					message ("*** Not found\n")
					subdivision['import_polygons'] = 0
		else:
			message ("*** Not found\n")
			municipality['import_polygons'] = 0

	ratio = round(100* total_polygons / total_buildings)
	message(f"\tTotal {total_polygons:d} import polygons of {total_buildings:d} import buildings in Norway ({ratio:d}%)\n")

	municipalities[ norway_id ]['import_polygons'] = total_polygons  # Norway



# Load count of existing buildings from OSM Overpass

def count_osm_buildings():

	message("\nLoading existing buildings from OSM ...\n")

	total_count = 0
	total_tags = 0

	for municipality_id, municipality in municipalities.items():

		if municipality_id == norway_id:
			continue

		message(f"\t{municipality['name']:<20} ")

		# Get number of buildings

		query = (
			'[out:json][timeout:60];'
			f'(area[ref={municipality_id}][admin_level=7][place=municipality];)->.a;'
			'(nwr["building"](area.a););out count;'
		)

		url = f'{overpass_instance}?data={urllib.parse.quote(query)}'
		with try_urlopen(url, request_header) as file:
			data = json.load(file)

		count = data['elements'][0]['tags']
		count_buildings = int(count['ways']) + int(count['relations'])
		total_count += count_buildings

		message(f"{count_buildings:7} ")

		if count == 0:
			message ("\n%s\n" % json.dumps(data, indent=2, ensure_ascii=False))

		time.sleep(sleep_time + count_buildings / buildings_per_second)

		# Get number of ref:byningsnr tags

		query = (
			'[out:json][timeout:60];'
			f'(area[ref={municipality_id}][admin_level=7][place=municipality];)->.a;'
			'(nwr["ref:bygningsnr"](area.a););out count;'
		)

		url = f'{overpass_instance}?data={urllib.parse.quote(query)}'
		with try_urlopen(url, request_header) as file:
			data = json.load(file)

		count_tags = int(data['elements'][0]['tags']['total'])
		total_tags += count_tags
		try:
			municipality['ref_progress'] = round(100 * count_tags / municipality['import_buildings'])
		except ZeroDivisionError:
			municipality['ref_progress'] = 0

		message(f"{count_tags:6d} {municipality['ref_progress']:3d}%")

		try:
			municipality['ref_polygon_progress'] = round(100 * count_tags / municipality['import_polygons'])
		except ZeroDivisionError:
			municipality['ref_polygon_progress'] = 0

		message(f"{municipality['ref_polygon_progress']:4d}%")

		# Compare with last update

		if count_buildings != municipality['osm_buildings']:
			message(f"  -> {count_buildings - municipality['osm_buildings']:d}")
		message("\n")

		municipality['osm_buildings'] = count_buildings

		time.sleep(sleep_time + count_buildings / buildings_per_second)

		for subdivision in municipality.get("subdivision", []):

			message(f'\t\tBydel {subdivision["name"]:<20}')
			query = (
				'[out:json][timeout:60];'
				f'(area[name="{subdivision["name"]}"][admin_level=9];)->.a;'
				'(nwr["building"](area.a););out count;'
				)

			url = f'{overpass_instance}?data={urllib.parse.quote(query)}'
			with try_urlopen(url, request_header) as file:
				data = json.load(file)

			count = data['elements'][0]['tags']
			count_buildings = int(count['ways']) + int(count['relations'])

			message(f"{count_buildings:7}")

			time.sleep(sleep_time + count_buildings / buildings_per_second)

			query = (
				'[out:json][timeout:60];'
				f'(area[name="{subdivision["name"]}"][admin_level=9];)->.a;'
				'(nwr["ref:bygningsnr"](area.a););out count;'
			)

			url = f'{overpass_instance}?data={urllib.parse.quote(query)}'
			with try_urlopen(url, request_header) as file:
				data = json.load(file)

			count_tags = int(data['elements'][0]['tags']['total'])
			try:
				subdivision['ref_progress'] = round(100 * count_tags / subdivision['import_buildings'])
			except ZeroDivisionError:
				subdivision['ref_progress'] = 0

			message(f"{count_tags:6d} {subdivision['ref_progress']:3d}%")

			try:
				subdivision['ref_polygon_progress'] = round(100 * count_tags / subdivision['import_polygons'])
			except ZeroDivisionError:
				subdivision['ref_polygon_progress'] = 0

			message(f"{subdivision['ref_polygon_progress']:4d}%")

			if count_buildings != subdivision['osm_buildings']:
				message(f"  -> {count_buildings - subdivision['osm_buildings']:d}")
			message("\n")

			subdivision['osm_buildings'] = count_buildings

			time.sleep(sleep_time + count_buildings / buildings_per_second)

	message(f"\tTotal {total_count:d} OSM buildings in Norway\n")

	municipalities[ norway_id ]['osm_buildings'] = total_count  # Norway
	municipalities[ norway_id ]['ref_progress'] = round(100 * total_tags / municipalities[ norway_id ]['import_buildings'])
	municipalities[ norway_id ]['ref_polygon_progress'] = round(100 * total_tags / municipalities[ norway_id ]['import_polygons'])



# Output summary in format suitable for updating wiki page

def output_file():

	message("\nSummary\n")

	osm_count = 0
	import_count = 0
	ref_count = 0
	ref_polygon_count = 0

	filename = "building_import_progress.txt"
	with open(filename, "w", encoding='utf-8') as file:

		file.write('Please read instructions in the [[Import/Catalogue/Norway Building Import|import plan]] (workflow section). '
			'Tagged import files per municipality and "bydel" are in [https://www.jottacloud.com/s/059f4e21889c60d4e4aaa64cc857322b134 this folder].\n\n')

		file.write("How to use the table below:\n\n")
		file.write('* "Status" (last column) may be used to indicate if import of a municipality is "started" or "completed", to avoid conflicting imports.\n')
		file.write('* "Matrikkel buildings" is the number of buildings in the Cadastral registry ("Matrikkelen"), available for import.\n')
		file.write('* "Total progress" is the number of buildings with the "ref:bygningsnr" tag in OSM in percentage of "Matrikkel buildings".\n')
		file.write('* "Polygon progress" is the same, but only for building polygons/ways, excluding nodes.\n\n')

		file.write('Some larger municipalities (Oslo, Bergen, Trondheim, Stavanger, Drammen) have been divided into smaller "bydel" parts in this table. Please see second table of this page.\n\n')

		today = date.today()
		file.write('Table numbers updated %s. Updates once a week.\n\n' % today.strftime("%Y-%m-%d"))

		# Produce municipality table

		file.write('{| class="wikitable sortable" style="text-align: right;"\n')
		file.write("|+Import progress table - Municipalities\n")
		file.write("|-\n")
		file.write("!Id\n")
		file.write("!Municipality\n")
		file.write("!County\n")
		file.write('! data-sort-type="number" |Matrikkel buildings\n')
		file.write('! data-sort-type="number" |OSM buildings\n')
		file.write('! data-sort-type="number" |Building progress\n')
		file.write('! data-sort-type="number" |Polygon progress\n')
		file.write("!Responsible user(s)\n")
		file.write("!Status\n")

		for municipality_id, municipality in municipalities.items():

			message(
				f"\t{municipality_id} {municipality['name']:<15} {municipality['county']:<20} "
				f"{municipality['import_buildings']:7d} {municipality['osm_buildings']:7d} "
				f"{municipality['ref_progress']:3d}% {municipality['ref_polygon_progress']:3d}% "
				f"{municipality['user']:<10} {municipality['status']:<10}\n"
			)

			file.write("|-\n")
			file.write(f"|{municipality_id}\n")
			file.write(f"|{municipality['name']}\n")
			file.write(f"|{municipality['county']}\n")
			file.write(f"|{municipality['import_buildings']:,}\n".replace(',', ' '))
			file.write(f"|{municipality['osm_buildings']:,}\n".replace(',', ' '))
			if municipality['ref_progress'] > 0 or municipality['user']:
				file.write(f"|{{{{Progress|{municipality['ref_progress']:d}}}}}\n")
			else:
				file.write("|0%\n")
			if municipality['ref_polygon_progress'] > 0 or municipality['user']:
				file.write(f"|{{{{Progress|{municipality['ref_polygon_progress']:d}}}}}\n")
			else:
				file.write("|0%\n")
			file.write(f"|{municipality['user']}\n")
			file.write(f"|{municipality['status']}\n")

			if municipality_id != norway_id:
				import_count += municipality['import_buildings']
				osm_count += municipality['osm_buildings']
				ref_count += municipality['ref_progress'] * municipality['import_buildings'] / 100.0
				ref_polygon_count += municipality['ref_polygon_progress'] * municipality['import_buildings'] / 100.0

		file.write("|}\n\n")

		ref_count = round(100.0 * ref_count / import_count)
		ref_polygon_count = round(100.0 * ref_polygon_count / import_count)
		message(f"\t{'Total in Norway':<41} {import_count:7d} {osm_count:7d} {ref_count:3d}% {ref_polygon_count:3d}%\n\n")

		# Produce borough table

		file.write("==Bydeler==\n")
		file.write("Note: Most of Oslo inside of Ring 3 is already imported except East side, however needs conflation with ''ref:bygningsnr'' and ''building:levels''.\n")
		file.write('{| class="wikitable sortable" style="text-align: right;"\n')
		file.write("|+Import progress table - Bydeler\n")
		file.write("|-\n")
		file.write("!Municipality\n")
		file.write("!Bydel\n")
		file.write('! data-sort-type="number" |Matrikkel buildings\n')
		file.write('! data-sort-type="number" |OSM buildings\n')
		file.write('! data-sort-type="number" |Building progress\n')
		file.write('! data-sort-type="number" |Polygon progress\n')
		file.write("!Responsible user(s)\n")
		file.write("!Status\n")

		for city in filter(lambda m: "subdivision" in m, municipalities.values()):
			for subdivision in city["subdivision"]:
				file.write("|-\n")
				file.write(f"|{city['name']}\n")
				file.write(f"|{subdivision['name']}\n")
				file.write(f"|{subdivision['import_buildings']:,}\n".replace(',', ' '))
				file.write(f"|{subdivision['osm_buildings']:,}\n".replace(',', ' '))
				if subdivision['ref_progress'] > 0 or subdivision['user']:
					file.write(f"|{{{{Progress|{subdivision['ref_progress']:d}}}}}\n")
				else:
					file.write("|0%\n")
				if subdivision['ref_polygon_progress'] > 0 or subdivision['user']:
					file.write(f"|{{{{Progress|{subdivision['ref_polygon_progress']:d}}}}}\n")
				else:
					file.write("|0%\n")
				file.write(f"|{subdivision['user']}\n")
				file.write(f"|{subdivision['status']}\n")

		file.write("|}\n")

	message(f"File saved to '{filename}'\n")



# Main program

if __name__ == '__main__':

	if len(sys.argv) > 1 and sys.argv[1].isdigit():
		sleep_time = float(sys.argv[1])
		if sleep_time != 0:
			buildings_per_second = 10000.0 / sleep_time
		else:
			buildings_per_second = 1000000.0

	municipalities = {}

	load_progress_page()

	if "-osm" not in sys.argv:
		count_import_buildings()
		count_import_polygons()

	if "-matrikkel" not in sys.argv:
		count_osm_buildings()

	output_file()

	message ("Done\n\n")
