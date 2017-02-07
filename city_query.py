'''Classes for managing data associated with the Geonames city data.

In particular, the CityQueryBuilder dumps the data into a SQL database, and
builds two indices for optimized lexical searches and nearest neighbors
searches. The CityQuery object then knows how to load these indices into memory
and perform the desired searches.

See README for design choices, limitations, and future directions for this
code.
'''
import collections
import math
import glob
import json
import os
import pandas
from rtree import index
import sqlite3 as sqlite


class CityQuery:
    rtree_properties = index.Property(dimension=3)
    '''Loads inverted index and spatial index into memory and runs lexical
    search and nearest neighbors queries on city data.

    Since CityQuery operates over read-only data, it's conveniently thread safe
    no matter how many queries from different CityQuery objects you run in
    parallel.
    '''
    def __init__(self, database, inverted_index_file, spatial_index):
        '''Initialize state by loading relevant indices into memory. Note that
        we also set up a connection the SQLite database storing the original
        data so that we can return more detailed answers to queries.
        '''
        self.db_conn = sqlite.connect(database)
        self.cursor = self.db_conn.cursor()

        with open(inverted_index_file, 'r') as f:
            self.inverted_index = json.load(f)
            f.close()

        self.idx = index.Rtree(
            spatial_index, properties=self.rtree_properties)

    def __del__(self):
        self.db_conn.close()

    def lexical_search(self, search_str):
        '''Searches for cities that include every word in search_str somewhere
        in their collection of names.

        The run-time of this function breaks down into:
          - O(w) to look up words in the inverted_index, where w is the number
            of words in search_str
          - O(m) to do the set intersection operations, where m is the total
            number of matches across all the words

        Since we expect both w and m to be relatively small and we store the
        inverted index in memory, this query should quite run quickly.

        We then do some work to search the database for additional information
        about each of these IDs, which we don't count in the above run time, but
        which should take O(k) * time to search the database for a key (likely
        O(1) or O(log number of entries)), where k is the total number of matches.

        (What this function doesn't do: ensure that all the words in search_str
        appear in the *same* alternate name or return the alternate name that
        matched search_str. However, it's not difficult to modify the code to
        handle these situations. In particular, we iterate through all of the
        matching IDs, look at all of the names and make sure that all words in
        search_str appear in at least one name (+store that name), eliminating
        the IDs that don't have a matching name.)
        '''
        matching_ids_lists = []
        search_str = search_str.lower()
        for word in search_str.split():
            if word not in self.inverted_index:
                matching_ids_lists.append(set())
            else:
                matching_ids_lists.append(set(self.inverted_index[word]))

        matching_ids = set(matching_ids_lists[0])
        for i in range(1, len(matching_ids_lists)):
            matching_ids = matching_ids.intersection(matching_ids_lists[i])

        return self._find_matching_cities(matching_ids)

    def _find_matching_cities(self, ids):
        '''Helper function to translate computer-friendly unique city IDs to
        human-friendly tuples of information about cities. Used by both query
        functions to return human-readable output.

        Returns a list of tuples with interesting information. "Interesting"
        information is, of course, a relative term and the fields retrieved can
        be modified by updating the SQL statement below.
        '''
        SELECT_QUERY = '''
           SELECT id, name, latitude, longitude, country_code, admin1_code, population
           FROM cities
           WHERE id=?
        '''

        matching_cities = []
        for geoid in ids:
            self.cursor.execute(SELECT_QUERY, (geoid,))
            matching_cities.append(self.cursor.fetchone())
        return matching_cities

    def nearest_neighbors(self, geoid, num=1):
        '''Find the `num` nearest neighbors by Euclidean distance to the city
        with ID geoid.

        As it turns out, getting the run-time for a nearest neighbors search
        on this library implementation is pretty hard, given the shoddily
        documented original C++ implementation.

        Returns a list of information about the matching cities.
        '''
        SELECT_QUERY = '''SELECT latitude, longitude FROM cities WHERE id=?'''

        self.cursor.execute(SELECT_QUERY, (geoid,))
        (latitude, longitude) = self.cursor.fetchone()
        coords = CityQuery.geodetic_to_cartesian_coord(latitude, longitude)
        
        # The R-tree will return the query city as well, so we ask for num+1
        # neighbors and remove the query city.
        matching_ids = list(self.idx.nearest(coords, num+1))
        matching_ids.remove(geoid)

        return self._find_matching_cities(matching_ids)

    @staticmethod
    def geodetic_to_cartesian_coord(latitude, longitude):
        '''Helper method to translate latitude and longitude coordinates into
        Euclidean coordinates.

        Note that we make some simplifying assumptions here, namely, all cities
        are at the same elevation from the Earth's surface. This could be
        fixed with a tweak to the formulas to take into account altitude from
        the Earth's surface, a field which is stored in the GeoNames data.

        The formulas here were found on the Internet for mapping from spherical
        to Cartesian coordinates.
        '''
        lat = math.radians(latitude)
        lon = math.radians(longitude)

        r = 6371
        x = r * math.cos(lat) * math.cos(lon)
        y = r * math.cos(lat) * math.sin(lon)
        z = r * math.sin(lat)

        return (x, y, z)


class CityQueryBuilder:
    '''Class for building out indexes used by CityQuery.'''

    @staticmethod
    def build_city_query(
            database, inverted_index_file, spatial_index_file, data_file=None):
        '''Returns a new CityQuery object. If data_file is not None, also build
        all relevant indices and save to files specified. Then load files into
        CityQuery object.'''
        if data_file is not None:
            CityQueryBuilder.dump_to_sqlite_table(data_file, database)
            CityQueryBuilder.build_inverted_index_file(database, inverted_index_file)
            CityQueryBuilder.build_spatial_index(database, spatial_index_file)
        return CityQuery(database, inverted_index_file, spatial_index_file)

    @staticmethod
    def dump_to_sqlite_table(data_file, database):
        '''Dumps all the data in the data_file to the given database.

        We create a table that is indexed by the unique geoid given to each
        city. Then we build out our lexical index and spatial index by just
        storing IDs, which we can then look up in this SQLite database for
        additional information on the cities.

        Note that we create a new table "cities", dropping the table if it
        already existed. SQLite for python does not support parametrization on
        the table name, else we'd make this configurable as well. (It is, of
        course, possible to do the string sanitization ourselves, but for the
        purposes of this use case, we'll not worry about it too much and just
        directly hard code the value.)
        '''
        DROP_TABLE = '''DROP TABLE IF EXISTS cities;'''
        CREATE_TABLE = '''CREATE TABLE cities (
            id int PRIMARY KEY,
            name varchar(200),
            asciiname varchar(200),
            altnames varchar(10000),
            latitude real,
            longitude real,
            feature_class char(1),
            feature_code varchar(10),
            country_code char(2),
            cc2 varchar(200),
            admin1_code varchar(20),
            admin2_code varchar(80),
            admin3_code varchar(20),
            admin4_code varchar(20),
            population bigint,
            elevation int,
            dem int,
            timezone varchar(40),
            modification_date varchar(16)
        );'''

        conn = sqlite.connect(database)
        c = conn.cursor()
        
        c.execute(CityQueryBuilder.DROP_TABLE)
        c.execute(CityQueryBuilder.CREATE_TABLE)
        
        df = pandas.read_csv(data_file, sep='\t')
        # don't write pandas index since we have our own primary key already
        df.to_sql('cities', conn, if_exists='append', index=False)
        
        conn.commit()
        conn.close()
        
    @staticmethod
    def build_inverted_index_file(database, inverted_index_file):
        '''Builds an inverted index file that maps a word to the geoid of every
        city that includes that word in one of its names. This is a simple map
        of word -> list of geoids, which we serialize to a file using JSON.
        '''
        SELECT_QUERY = '''SELECT id, name, asciiname, altnames FROM cities'''

        conn = sqlite.connect(database)
        c = conn.cursor()
        
        inverted_index = collections.defaultdict(lambda: list())
        for (geoid, name, asciiname, altnames) in c.execute(SELECT_QUERY):
            for word in CityQueryBuilder._generate_words_from_names(
                    name, asciiname, altnames):
                inverted_index[word].append(geoid)

        conn.commit()
        conn.close()

        with open(inverted_index_file, 'w+') as f:
            json.dump(inverted_index, f)
            f.close()

    @staticmethod
    def _generate_words_from_names(name, asciiname, altnames):
        '''Helper method to generate all words from the many names a city
        has.'''
        all_names = [name]
        if asciiname is not None:
            all_names += [asciiname]
        if altnames is not None:
            all_names += altnames.split(',')

        all_words = set()
        for n in all_names:
            for word in n.split():
                all_words.add(word.lower())
        return all_words
        
    @staticmethod
    def build_spatial_index(database, spatial_index_file):
        '''Builds a spatial index for the cities data set. The spatial index is
        built on top of a 3D R-tree, which stores the geoids for each city in
        its ID field for easy accessibility later. The R-tree is then serialized
        to a file.
        '''
        SELECT_QUERY = '''SELECT id, name, latitude, longitude FROM cities'''

        for f in glob.glob(spatial_index_file + ".*"):
            os.remove(f)

        conn = sqlite.connect(database)
        c = conn.cursor()

        idx = index.Rtree(
            spatial_index_file, properties=CityQuery.rtree_properties)

        query = None
        for (geoid, name, latitude, longitude) in c.execute(SELECT_QUERY):
            cartesian_coords = CityQuery.geodetic_to_cartesian_coord(
                latitude, longitude)
            idx.insert(geoid, cartesian_coords)

        conn.commit()
        conn.close()



