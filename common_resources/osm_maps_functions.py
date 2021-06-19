#!/usr/bin/python

# import official python packages
import glob
import json
import os
import os.path
import subprocess
import sys
import time
import platform

# import custom python packages
import requests
from os import sys, path
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
from common_resources import file_directory_functions
from common_resources import constants
from common_resources import constants_functions

class OsmMaps:
    "This is a OSM data class"


    def __init__(self, inputFile, Max_Days_Old, Force_Download,
     Force_Processing, workers, threads, Save_Cruiser):
        self.input_argument1 = inputFile
        self.region = constants_functions.get_region_of_country(inputFile)
        self.max_days_old = Max_Days_Old
        self.force_download = Force_Download
        self.force_processing = Force_Processing
        self.workers = workers
        self.threads = threads
        self.save_cruiser = Save_Cruiser
        self.tiles_from_json = []
        self.border_countries = {}

        self.country_name = os.path.split(inputFile)[1][:-5]


    def read_json_file(self):
        print('\n# Read json file')

        # option 1: have a .json file as input parameter
        if os.path.isfile(self.input_argument1):
            json_file_path = self.input_argument1
        # option 2: input a country as parameter, e.g. germany
        else:
            json_file_path = os.path.join (file_directory_functions.COMMON_DIR,
             'json', self.region, self.input_argument1 + '.json')

        with open(json_file_path) as json_file:
            self.tiles_from_json = json.load(json_file)
            json_file.close()
        if self.tiles_from_json == '' :
            print ('! Json file could not be opened.')
            sys.exit()

        # logging
        print(f'+ Use json file {json_file.name} with {len(self.tiles_from_json)} tiles')
        print('# Read json file: OK')


    def check_and_download_land_poligons_file(self):
        print('\n# check land_polygons.shp file')
        # Check for expired land polygons file and delete it
        now = time.time()
        to_old_timestamp = now - 60 * 60 * 24 * self.max_days_old
        try:
            file_creation_timestamp = os.path.getctime(file_directory_functions.LAND_POLYGONS_PATH)
            if file_creation_timestamp < to_old_timestamp:
                print ('# Deleting old land polygons file')
                os.remove(file_directory_functions.LAND_POLYGONS_PATH)
                self.force_download = 1
                self.force_processing = 1
        except:
            self.force_download = 1
            self.force_processing = 1

        if not os.path.exists(file_directory_functions.LAND_POLYGONS_PATH) or not os.path.isfile(file_directory_functions.LAND_POLYGONS_PATH) or self.force_download == 1:
            print('# Downloading land polygons file')
            url = 'https://osmdata.openstreetmap.de/download/land-polygons-split-4326.zip'
            request_land_polygons = requests.get(url, allow_redirects=True, stream = True)
            if request_land_polygons.status_code != 200:
                print('failed to find or download land polygons file')
                sys.exit()
            download=open(os.path.join (file_directory_functions.COMMON_DIR,
             'land-polygons-split-4326.zip'), 'wb')
            for chunk in request_land_polygons.iter_content(chunk_size=1024*100):
                download.write(chunk)
            download.close()
            # unpack it
            # should work on macOS and Windows
            file_directory_functions.unzip(os.path.join (file_directory_functions.COMMON_DIR,
             'land-polygons-split-4326.zip'), file_directory_functions.COMMON_DIR)
            # Windows-Version
            # cmd = ['7za', 'x', '-y', os.path.join (file_directory_functions.COMMON_DIR, 'land-polygons-split-4326.zip')]
            #print(cmd)
            # result = subprocess.run(cmd)
            os.remove(os.path.join (file_directory_functions.COMMON_DIR,
             'land-polygons-split-4326.zip'))
            # if result.returncode != 0:
            #     print(f'Error unpacking land polygons file')
            #     sys.exit()

        # Check if land polygons file exists
        if not os.path.isfile(file_directory_functions.LAND_POLYGONS_PATH):
            print(f'! failed to find {file_directory_functions.LAND_POLYGONS_PATH}')
            sys.exit()

        # logging
        print('# check land_polygons.shp file: OK')


    def check_and_download_osm_pbf_file(self):
        print('\n# check countries .osm.pbf files')
        # Build list of countries needed
        border_countries = {}
        for tile in self.tiles_from_json:
            for country in tile['countries']:
                if country not in border_countries:
                    border_countries[country] = {'map_file':country}

        # logging
        print(f'+ Border countries of json file: {len(border_countries)}')
        for country in border_countries:
            print(f'+ Border country: {country}')

        # time.sleep(60)

        # Check for expired maps and delete them
        print('+ Checking for old maps and remove them')
        now = time.time()
        to_old_timestamp = now - 60 * 60 * 24 * self.max_days_old
        for country in border_countries:
            # print(f'+ mapfile for {c}')
            map_files = glob.glob(f'{file_directory_functions.MAPS_DIR}/{country}*.osm.pbf')
            if len(map_files) != 1:
                map_files = glob.glob(f'{file_directory_functions.MAPS_DIR}/**/{country}*.osm.pbf')
            if len(map_files) == 1 and os.path.isfile(map_files[0]):
                file_creation_timestamp = os.path.getctime(map_files[0])
                if file_creation_timestamp < to_old_timestamp or self.force_download == 1:
                    print(f'+ mapfile for {country}: deleted')
                    os.remove(map_files[0])
                    self.force_processing = 1
                else:
                    border_countries[country] = {'map_file':map_files[0]}
                    print(f'+ mapfile for {country}: up-to-date')

        # time.sleep(60)

        file_directory_functions.create_empty_directories(self.tiles_from_json)

        for country in border_countries:
            print(f'+ Checking mapfile for {country}')
            # check for already existing .osm.pbf file
            # map_file_name = border_countries[country]['map_file']
            if len(border_countries[country]) != 1 or not os.path.isfile(border_countries[country]['map_file']):
                # if there exists no file or it is no file --> download
                map_files = self.download_map(country)
                border_countries[country] = {'map_file':map_files[0]}

        self.border_countries = border_countries
        # logging
        print('# Check countries .osm.pbf files: OK')


    def filter_tags_from_country_osm_pbf_files(self):

        print('\n# Filter tags from country osm.pbf files')

        # Windows
        if platform.system() == "Windows":
            for key, val in self.border_countries.items():
            # print(key, val)
                out_file = os.path.join(file_directory_functions.OUTPUT_DIR,
                 f'filtered-{key}.osm.pbf')
                out_file_o5m = os.path.join(file_directory_functions.OUTPUT_DIR,
                 f'outFile-{key}.o5m')
                out_file_o5m_filtered = os.path.join(file_directory_functions.OUTPUT_DIR,
                 f'outFileFiltered-{key}.o5m')

                if not os.path.isfile(out_file) or self.force_processing == 1:
                    print(f'\n+ Converting map of {key} to o5m format')
                    cmd = ['osmconvert']
                    cmd.extend(['-v', '--hash-memory=2500', '--complete-ways', '--complete-multipolygons', '--complete-boundaries', '--drop-author', '--drop-version'])
                    cmd.append(val['map_file'])
                    cmd.append('-o='+out_file_o5m)
                    # print(cmd)
                    result = subprocess.run(cmd)
                    if result.returncode != 0:
                        print(f'Error in OSMConvert with country: {key}')
                        sys.exit()

                    print(f'\n# Filtering unwanted map objects out of map of {key}')
                    cmd = ['osmfilter']
                    cmd.append(out_file_o5m)
                    cmd.append('--keep="' + constants.FILTERED_TAGS_WIN + '"')
                    cmd.append('-o=' + out_file_o5m_filtered)
                    # print(cmd)
                    result = subprocess.run(cmd)
                    if result.returncode != 0:
                        print(f'Error in OSMFilter with country: {key}')
                        sys.exit()

                    print(f'\n# Converting map of {key} back to osm.pbf format')
                    cmd = ['osmconvert', '-v', '--hash-memory=2500', out_file_o5m_filtered]
                    cmd.append('-o='+out_file)
                    # print(cmd)
                    result = subprocess.run(cmd)
                    if result.returncode != 0:
                        print(f'Error in OSMConvert with country: {key}')
                        sys.exit()

                    os.remove(out_file_o5m)
                    os.remove(out_file_o5m_filtered)

                self.border_countries[key]['filtered_file'] = out_file

        # Non-Windows
        else:
            for key, val  in self.border_countries.items():
                ## print(key, val)
                out_file = os.path.join(file_directory_functions.OUTPUT_DIR,
                 f'filtered-{key}.osm.pbf')
                ## print(outFile)
                if not os.path.isfile(out_file):
                    print(f'+ Create filtered country file for {key}')

                    cmd = ['osmium', 'tags-filter']
                    cmd.append(val['map_file'])
                    cmd.extend(constants.filtered_tags)
                    cmd.extend(['-o', out_file])
                    # print(cmd)
                    subprocess.run(cmd)
                self.border_countries[key]['filtered_file'] = out_file

        # logging
        print('# Filter tags from country osm.pbf files: OK')


    def generate_land(self):
        print('\n# Generate land')

        tile_count = 1
        for tile in self.tiles_from_json:
            land_file = os.path.join(file_directory_functions.OUTPUT_DIR,
             f'{tile["x"]}', f'{tile["y"]}', 'land.shp')
            out_file = os.path.join(file_directory_functions.OUTPUT_DIR,
             f'{tile["x"]}', f'{tile["y"]}', 'land')

            if not os.path.isfile(land_file) or self.force_processing == 1:
                print(f'+ Generate land {tile_count} of {len(self.tiles_from_json)} for Coordinates: {tile["x"]} {tile["y"]}')
                cmd = ['ogr2ogr', '-overwrite', '-skipfailures']
                cmd.extend(['-spat', f'{tile["left"]-0.1:.6f}',
                            f'{tile["bottom"]-0.1:.6f}',
                            f'{tile["right"]+0.1:.6f}',
                            f'{tile["top"]+0.1:.6f}'])
                cmd.append(land_file)
                cmd.append(file_directory_functions.LAND_POLYGONS_PATH)
                #print(cmd)
                subprocess.run(cmd)

            if not os.path.isfile(out_file+'1.osm') or self.force_processing == 1:
                # Windows
                if platform.system() == "Windows":
                    cmd = ['python', os.path.join(file_directory_functions.COMMON_DIR,
                     'shape2osm.py'), '-l', out_file, land_file]
                # Non-Windows
                else:
                    cmd = ['python3', os.path.join(file_directory_functions.COMMON_DIR,
                     'shape2osm.py'), '-l', out_file, land_file]
                #print(cmd)
                subprocess.run(cmd)
            tile_count += 1

        # logging
        print('# Generate land: OK')


    def generate_sea(self):
        print('\n# Generate sea')

        tile_count = 1
        for tile in self.tiles_from_json:
            out_file = os.path.join(file_directory_functions.OUTPUT_DIR,
             f'{tile["x"]}', f'{tile["y"]}', 'sea.osm')
            if not os.path.isfile(out_file) or self.force_processing == 1:
                print(f'+ Generate sea {tile_count} of {len(self.tiles_from_json)} for Coordinates: {tile["x"]} {tile["y"]}')
                with open(os.path.join(file_directory_functions.COMMON_DIR, 'sea.osm')) as sea_file:
                    sea_data = sea_file.read()

                    sea_data = sea_data.replace('$LEFT', f'{tile["left"]-0.1:.6f}')
                    sea_data = sea_data.replace('$BOTTOM',f'{tile["bottom"]-0.1:.6f}')
                    sea_data = sea_data.replace('$RIGHT',f'{tile["right"]+0.1:.6f}')
                    sea_data = sea_data.replace('$TOP',f'{tile["top"]+0.1:.6f}')

                    with open(out_file, 'w') as output_file:
                        output_file.write(sea_data)
            tile_count += 1

        # logging
        print('# Generate sea: OK')


    def split_filtered_country_files_to_tiles(self):
        print('\n# Split filtered country files to tiles')
        tile_count = 1
        for tile in self.tiles_from_json:

            for country in tile['countries']:
                print(f'+ Split filtered country {country}')
                print(f'+ Splitting tile {tile_count} of {len(self.tiles_from_json)} for Coordinates: {tile["x"]},{tile["y"]} from map of {country}')
                out_file = os.path.join(file_directory_functions.OUTPUT_DIR,
                 f'{tile["x"]}', f'{tile["y"]}', f'split-{country}.osm.pbf')
                if not os.path.isfile(out_file) or self.force_processing == 1:
                    # Windows
                    if platform.system() == "Windows":
                        #cmd = ['.\\osmosis\\bin\\osmosis.bat', '--rbf',border_countries[c]['filtered_file'],'workers='+workers, '--buffer', 'bufferCapacity=12000', '--bounding-box', 'completeWays=yes', 'completeRelations=yes']
                        #cmd.extend(['left='+f'{tile["left"]}', 'bottom='+f'{tile["bottom"]}', 'right='+f'{tile["right"]}', 'top='+f'{tile["top"]}', '--buffer', 'bufferCapacity=12000', '--wb'])
                        #cmd.append('file='+outFile)
                        #cmd.append('omitmetadata=true')
                        cmd = ['osmconvert', '-v', '--hash-memory=2500']
                        cmd.append('-b='+f'{tile["left"]}' + ',' + f'{tile["bottom"]}' + ',' + f'{tile["right"]}' + ',' + f'{tile["top"]}')
                        cmd.extend(['--complete-ways', '--complete-multipolygons', '--complete-boundaries'])
                        cmd.append(self.border_countries[country]['filtered_file'])
                        cmd.append('-o='+out_file)

                        # print(cmd)
                        result = subprocess.run(cmd)
                        if result.returncode != 0:
                            print(f'Error in Osmosis with country: {country}')
                            sys.exit()
                        # print(border_countries[c]['filtered_file'])

                    # Non-Windows
                    else:
                        cmd = ['osmium', 'extract']
                        cmd.extend(['-b',f'{tile["left"]},{tile["bottom"]},{tile["right"]},{tile["top"]}'])
                        cmd.append(self.border_countries[country]['filtered_file'])
                        cmd.extend(['-s', 'smart'])
                        cmd.extend(['-o', out_file])
                        # print(cmd)
                        subprocess.run(cmd)
                        print(self.border_countries[country]['filtered_file'])

            tile_count += 1

            # logging
            print('# Split filtered country files to tiles: OK')


    def merge_splitted_tiles_with_land_and_sea(self):
        print('\n# Merge splitted tiles with land an sea')
        tile_count = 1
        for tile in self.tiles_from_json:
            print(f'+ Merging tiles for tile {tile_count} of {len(self.tiles_from_json)} for Coordinates: {tile["x"]},{tile["y"]}')
            out_file = os.path.join(file_directory_functions.OUTPUT_DIR,
             f'{tile["x"]}', f'{tile["y"]}', 'merged.osm.pbf')
            if not os.path.isfile(out_file) or self.force_processing == 1:
                # Windows
                if platform.system() == "Windows":
                    cmd = [os.path.join (file_directory_functions.COMMON_DIR,
                     'Osmosis', 'bin', 'osmosis.bat')]
                    loop=0
                    for country in tile['countries']:
                        cmd.append('--rbf')
                        cmd.append(os.path.join(file_directory_functions.OUTPUT_DIR,
                         f'{tile["x"]}', f'{tile["y"]}', f'split-{country}.osm.pbf'))
                        cmd.append('workers='+ self.workers)
                        if loop > 0:
                            cmd.append('--merge')
                        loop+=1
                    land_files = glob.glob(os.path.join(file_directory_functions.OUTPUT_DIR,
                     f'{tile["x"]}', f'{tile["y"]}', 'land*.osm'))
                    for land in land_files:
                        cmd.extend(['--rx', 'file='+os.path.join(file_directory_functions.OUTPUT_DIR,
                         f'{tile["x"]}', f'{tile["y"]}', f'{land}'), '--s', '--m'])
                    cmd.extend(['--rx', 'file='+os.path.join(file_directory_functions.OUTPUT_DIR,
                     f'{tile["x"]}', f'{tile["y"]}', 'sea.osm'), '--s', '--m'])
                    cmd.extend(['--tag-transform', 'file=' + os.path.join (file_directory_functions.COMMON_DIR, 'tunnel-transform.xml'), '--wb', out_file, 'omitmetadata=true'])

                    #print(cmd)
                    result = subprocess.run(cmd)
                    if result.returncode != 0:
                        print(f'Error in Osmosis with country: {country}')
                        sys.exit()
                # Non-Windows
                else:
                    cmd = ['osmium', 'merge', '--overwrite']
                    for country in tile['countries']:
                        cmd.append(os.path.join(file_directory_functions.OUTPUT_DIR,
                         f'{tile["x"]}', f'{tile["y"]}', f'split-{country}.osm.pbf'))

                    cmd.append(os.path.join(file_directory_functions.OUTPUT_DIR,
                     f'{tile["x"]}', f'{tile["y"]}', 'land1.osm'))
                    cmd.append(os.path.join(file_directory_functions.OUTPUT_DIR,
                     f'{tile["x"]}', f'{tile["y"]}', 'sea.osm'))
                    cmd.extend(['-o', out_file])

                    #print(cmd)
                    subprocess.run(cmd)
            tile_count += 1

        # logging
        print('# Merge splitted tiles with land an sea: OK')


    def create_map_files(self):
        print('\n# Creating .map files')
        tile_count = 1
        for tile in self.tiles_from_json:
            print(f'+ Creating map file for tile {tile_count} of {len(self.tiles_from_json)} for Coordinates: {tile["x"]}, {tile["y"]}')
            out_file = os.path.join(file_directory_functions.OUTPUT_DIR,
             f'{tile["x"]}', f'{tile["y"]}.map')
            if not os.path.isfile(out_file+'.lzma') or self.force_processing == 1:
                merged_file = os.path.join(file_directory_functions.OUTPUT_DIR,
                 f'{tile["x"]}', f'{tile["y"]}', 'merged.osm.pbf')

                # Windows
                if platform.system() == "Windows":
                    cmd = [os.path.join (file_directory_functions.COMMON_DIR, 'Osmosis', 'bin', 'osmosis.bat'), '--rbf', merged_file, 'workers=' + self.workers, '--mw', 'file='+out_file]
                # Non-Windows
                else:
                    cmd = ['osmosis', '--rb', merged_file, '--mw', 'file='+out_file]

                cmd.append(f'bbox={tile["bottom"]:.6f},{tile["left"]:.6f},{tile["top"]:.6f},{tile["right"]:.6f}')
                cmd.append('zoom-interval-conf=10,0,17')
                cmd.append('threads='+ self.threads)
                # should work on macOS and Windows
                cmd.append(f'tag-conf-file={os.path.join(file_directory_functions.COMMON_DIR, "tag-wahoo.xml")}')
                # print(cmd)
                result = subprocess.run(cmd)
                if result.returncode != 0:
                    print(f'Error in Osmosis with country: c // tile: {tile["x"]}, {tile["y"]}')
                    sys.exit()

                # Windows
                if platform.system() == "Windows":
                    cmd = ['lzma', 'e', out_file, out_file+'.lzma', f'-mt{self.threads}', '-d27', '-fb273', '-eos']
                # Non-Windows
                else:
                    cmd = ['lzma', out_file]

                    # --keep: do not delete source file
                    if self.save_cruiser:
                        cmd.append('--keep')

                # print(cmd)
                subprocess.run(cmd)
            tile_count += 1

        # logging
        print('# Creating .map files: OK')


    def zip_map_files(self):
        print('\n# Zip .map.lzma files')
        # countryName = os.path.split(sys.argv[1])
        # print(f'+ Country: {countryName[1][:-5]}')
        print(f'+ Country: {self.country_name}')

        # Make Wahoo zip file
        # Windows
        if platform.system() == "Windows":
            cmd = ['7za', 'a', '-tzip', '-m0=lzma', '-mx9', '-mfb=273', '-md=1536m', self.country_name + '.zip']
            #cmd = ['7za', 'a', '-tzip', '-m0=lzma', countryName[1] + '.zip']
        # Non-Windows
        else:
            cmd = ['zip', '-r', self.country_name + '.zip']

        for tile in self.tiles_from_json:
            cmd.append(os.path.join(f'{tile["x"]}', f'{tile["y"]}.map.lzma'))
        #print(cmd)
        subprocess.run(cmd, cwd=file_directory_functions.OUTPUT_DIR)

        # logging
        print('# Zip .map.lzma files: OK \n')


    def make_cruiser_files(self):
        # Make Cruiser map files zip file
        if self.save_cruiser == 1:
            # Windows
            if platform.system() == "Windows":
                cmd = ['7za', 'a', '-tzip', '-m0=lzma', self.country_name + '-maps.zip']
            # Non-Windows
            else:
                cmd = ['zip', '-r', self.country_name + '-maps.zip']

            for tile in self.tiles_from_json:
                cmd.append(os.path.join(f'{tile["x"]}', f'{tile["y"]}.map'))
            #print(cmd)
            subprocess.run(cmd, cwd=file_directory_functions.OUTPUT_DIR)


    def download_map(self, country):
        # search for user entered country name in translated (to geofabrik). if match continue with matched else continue with user entered country
        # search for country match in geofabrik tables to determine region to use for map download

        print(f'+ Trying to download missing map of {country}.')

        # get Geofabrik region of country
        translated_country = constants_functions.translate_input_country_to_osm(country)
        region = constants_functions.get_geofabrik_region_of_country(f'{country}')

        if region != 'no':
            url = 'https://download.geofabrik.de/'+ region + '/' + translated_country + '-latest.osm.pbf'
        else:
            url = 'https://download.geofabrik.de/' + translated_country + '-latest.osm.pbf'

        request_geofabrik = requests.get(url, allow_redirects=True, stream = True)
        if request_geofabrik.status_code != 200:
            print(f'! failed to find or download country: {country}')
            sys.exit()
        download=open(os.path.join (file_directory_functions.MAPS_DIR, f'{country}' + '-latest.osm.pbf'), 'wb')
        for chunk in request_geofabrik.iter_content(chunk_size=1024*100):
            download.write(chunk)
        download.close()
        map_files = [os.path.join (file_directory_functions.MAPS_DIR, f'{country}' + '-latest.osm.pbf')]
        print(f'+ Map of {country} downloaded.')

        return map_files
