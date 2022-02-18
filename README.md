# building2osm
Generates import files for OpenStreetMap with buliding footprints from Kartverket.

### building2osm

Generates geojson import file with building footprints.

_Note: The WFS service used is currently not delivering building polygons._

Usage:
<code>python3 building2osm.py \<municipality\> [-split] [-original] [-verify] [-debug]</code>

Parameters:
* _municipality_ - Name of the municipality to generate. Output for several municipalities is generated if county name or "Norway" is given. 
* <code>-split</code> - Also split output file into smaller subdivisions ("bydel", electoral or post districts).
* <code>-original</code> - Produce file without any modifications.
* <code>-verify</code> - Include extra tags for verification of topology modificatons.
* <code>-debug</code> - Include extra tags for debugging.

### building_merge

Conflates the geojson import file with existing buildings in OSM and produces an OSM file for manual verification and uploading.

Usage:
<code>python3 building_merge.py \<municipality\> [\<max distance\>] [\<filename.geojson\>] [-debug]</code>

Parameters:
* _municipality_ - Name of the municipality to conflate.
* _max distance_ - Optional maximum Hausdorff distance between matched buildings. Default value is 10 metres (5 metres is the building is tagged).
* _filename.geojson_ - Optional input file in geojson format. If not specified, the import file for the municipality will be loaded (it must be present in the default folder or in a predefined folder).
* <code>-debug</code> - Include extra tags for debugging.

### municipality_split

Splits the geojson import file into smaller subdivisions such as electoral districts or "bydel".

Usage:
<code>python3 municipality_split.py \<municipality\> [ --subdivision [ bydel | valgkrets | postnummer ]</code>
 
Parameter:
* _municipality_ - Name of the municipality to split.
* <code>--subdivision bydel</code> - Split municipality according to boroughs.
* <code>--subdivision postnummer</code> - Split municipality according to post districts.
* <code>--subdivision valgkrets</code> - Split municipality according to electoral districts (fewer than post districts in large towns; default).
* <code>--area</code> - Save district boundaries only (no split). Default is to save boundary file when splitting.

### filter_buildings

Filters the geojson import file, removing buildings that have already been
imported.

Usage:
<code>python3 filter_buildings.py --municipality \<id\> --input \<geojson\> --output \<geojson\></code>

Parameters:
* <code>--municipality id</code> - Municipality code to use for downloading
* <code>--input geojson</code> - Path to the input geojson file
* <code>--output geojson</code> - Path to the output geojson file

### Notes
* Source data is from the Cadastral registry of Kartverket
  * "INSPIRE Buildings Core2d" - Contains polygons of the building footprints.
  * "Matrikkelen Building point" - Contains information about the building type/usage.
  * "Matrikkelen Address apartment level" - Contains information about levels of the building. 
* The building=* tag is given a value corresponding to the _building_type_ translation table in this respository. Please provide feedback if you observe that the tagging should be modified. 
* Certain modifications of the footprint polygons are made to avoid clutter in OSM:
  * Polygons which are almost square are rectified (orthogonalized) to get exact 90 degrees corners. Groups of connected buildings are rectified as a group. Multipolygons are supported. A polygon is not rectified if it would relocate one of its nodes by more than 20 centimeters.
  * Redundant nodes are removed if they are located on an (almost) straight line.
  * Curved walls are only simplified lightly.
* Output is stored in a geosjon file which may be loaded into JOSM when the OpenData plugin has been installed. Please read the [import plan](https://wiki.openstreetmap.org/wiki/Import/Catalogue/Norway_Building_Import) for guiding on how to do the import.
* The _building_merge.py_ program conflates the import buildings with existing buildings in OSM.
  * New buildings are loaded from the geojson import file. You may split the import file into smaller parts using _municipality_split.py_ or manually.
  * Existing buildings are loaded from OSM.
  * New and existing buildings which are each other's best match within the given maximum Hausdorff distance (default 10 metres) are automatically conflated. They also need to have similar size (default 50% difference).
  * The _OSM_BUILDING_ tag will show which building tag was used by the existing building, unless they are in similar residential/commercial/farm categories.
  * Use the To-do plugin in JOSM to:
    1) Resolve _Overlapping buildings_. 
    2) Resolve _Building within buildings_.
    3) Check _OSM_BUILDING_ for manual retagging of building types.
    4) Check untouched existing OSM buildings.
    5) Check if entrances or other tagged nodes needs to be reconnected to the new buildings (search for <code>type:node ways:0 -untagged</code>).
  * Use the boundary polygons from _municipality_split.py_ and the JOSM functions _Selection->All inside_ and _Edit->Purge_ to work on a subset of a large municipality.
  * The _building_merge.py_ program may be run several times for the same municipality. Only buildings with new _ref:bygningsnr_ will be added each time.

### References

* [Kartverket product specificaton](https://register.geonorge.no/data/documents/Produktspesifikasjoner_Matrikkelen%20-%20Bygningspunkt_v1_produktspesifikasjon-matrikkelen-bygningspunkt-versjon20180501_.pdf)
* [OSM Norway building import plan](https://wiki.openstreetmap.org/wiki/Import/Catalogue/Norway_Building_Import)
* [Building import progress](https://wiki.openstreetmap.org/wiki/Import/Catalogue/Norway_Building_Import/Progress)
