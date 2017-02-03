'''This program takes the Geonames city data for cities of population >1000 and
processes it to optimize for two queries: lexical search for strings in city
names and nearest neighbors search.

Expected output can be founds in output/example.out.

E.g. to run this program:
python3 example.py data/cities1000.txt db/sql.db db/lex_idx.json db/spatial_idx
'''
import sys
from city_query import CityQuery, CityQueryBuilder

def print_lexical_search(search_obj, search_str):
    '''Helper method to run lexical search and pretty print results.'''
    print("Searching for {}...".format(search_str))
    matches = search_obj.lexical_search(search_str)

    if len(matches) == 0:
        print("No matches found.")
        return

    print("Found {} matches:".format(len(matches)))
    for match in matches:
        print("\t{}: {}".format(match[0], match[1:]))


def print_nearest_neighbors(search_obj, geoid):
    '''Helper method to run nearest neighbors search and pretty print
    results.'''
    matches = search_obj.nearest_neighbors(geoid, 10)

    print("Nearest neighbors search returns...")
    for match in matches:
        print("\t{}: {}".format(match[0], match[1:]))


def main():
    data_file = sys.argv[1]
    database = sys.argv[2]
    inverted_index_file = sys.argv[3]
    spatial_index_file  = sys.argv[4]

    search_obj = CityQueryBuilder.build_city_query(database, inverted_index_file, spatial_index_file, data_file)

    # Some common repeated names
    print_lexical_search(search_obj, "London")
    print_lexical_search(search_obj, "Paris")
    print_lexical_search(search_obj, "Chicago")

    # no matches
    print_lexical_search(search_obj, "meow")

    # test case
    print_lexical_search(search_obj, "grygov")

    # test with punctuation in name
    print_lexical_search(search_obj, "Sa'dah")

    # test multiple strings
    print_lexical_search(search_obj, "Washington DC")
    print_lexical_search(search_obj, "Cape Town")
    print_lexical_search(search_obj, "San Francisco")

    # test Unicode
    print_lexical_search(search_obj, "北京市")  # Beijing

    # Some nearest neighbors searches
    print_nearest_neighbors(search_obj, 2988507)  # Paris
    print_nearest_neighbors(search_obj, 4887398)  # Chicago


if __name__ == "__main__":
    main()
