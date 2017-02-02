import collections
import json
import pandas
import sqlite3 as sqlite
import sys

def build_inverted_index(database, inverted_index_file):
    SELECT_QUERY = '''SELECT id, name, altnames FROM cities'''

    conn = sqlite.connect(database)
    c = conn.cursor()

    inverted_index = collections.defaultdict(lambda: list())
    for (id, name, altnames) in c.execute(SELECT_QUERY):
        all_names = [name]
        if altnames is not None:
            all_names += altnames.split(',')
        all_words = set()
        for n in all_names:
            for word in n.split():
                all_words.add(word)
        for word in all_words:
            inverted_index[word].append(id)

    conn.commit()
    conn.close()

    with open(inverted_index_file, 'w+') as f:
        json.dump(inverted_index, f)
        f.close()
    print("Inverted index constructed.")

def dump_to_sqlite_table(data_file, database):
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

    c.execute(DROP_TABLE)
    c.execute(CREATE_TABLE)
    
    df = pandas.read_csv(data_file, sep='\t')
    # don't write pandas index since we have our own primary key already
    df.to_sql('cities', conn, if_exists='append', index=False)

    conn.commit()
    conn.close()

    print("SQL import complete.")

def main():
    data_file = sys.argv[1]
    database = sys.argv[2]
    inverted_index_file = sys.argv[3]
    
    dump_to_sqlite_table(data_file, database)
    build_inverted_index(database, inverted_index_file)
    
if __name__ == "__main__":
    main()
