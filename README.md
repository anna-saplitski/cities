
## Install

The python R-tree implementation we use is built on a C++ library for spatial indexing, lipspatialindex. Installation instructions are available [here](http://libspatialindex.github.io/install.html).

`pip3 install rtree`

`pip3 install pandas`

`pip3 install sqlite3`

## Data

### Source
The data comes from the GeoNames data set, available for download [here](download.geonames.org/export/dump/cities1000.zip). Column names and descriptions are available [here](http://download.geonames.org/export/dump/).

I had to do perform a small amount of data sanitization and prep for the data file to be ingestible. In particular, the data file as first downloaded does not include the column names, so I created a header and appended it to the file. It's definitely possible to do what I did programmatically, but since it only has to be performed once, I didn't bother.

The data also had a number of unescaped quotation marks (which appeared in random places), which caused the csv reader to misinterpret large chunks of the data as strings in the data set, instead of individual commas. I did a simple search and replace of " for \", which fixed the issue. This is also possible to do programmatically by reading in the entire file and doing a similar search and replace, but since the command only needed to be issued once, I just used a single Emacs command to do the necessary escaping. I didn't bother trying to figure out what the quotation marks were actually supposed to be (they often appeared in the middle of words), since there was 23Mb of data to comb through and there didn't seem to be any discernible pattern to what the quotation marks had been replacing.

The sanitized data is available in the `data/` folder in this repo.

### Why SQL?
The first thing we do with the data file is dump the sanitized data in a SQLite database. I wanted to use some sort of database to store the
data, but since the data was so small, I picked the lightweight SQLite. SQLite is super easy to use, hooks nicely into python and supported the main things I wanted from SQL: persistent storage on disk and fast indexing by the key of my choice.

There are many other choices I could have made to store the data persistently that satisfied these two properties. For example, I could have just built up a hash map that mapped primary key --> rest of data, and used json to serialize it. However, there are two things I particularly liked from SQL: the labelled columns and the fact that I didn't necessarily need to store all the data in memory when I was using the database.

Another option was to not use any sort of structure to store all of the original data set, and store only relevant information in each of the two indexes I built. The main issues with this were that this would have caused some data to be unnecessarily replicated (e.g. both indexes ideally should store the distinguishing information about a particular city, such as its name, country and geographic coordinates) and some data to be lost unnecessarily if it wasn't deemed interesting at pre-processing time. Instead, each of the indexes just stores geographic IDs, and queries the database for additional information on the IDs.

## Pre-processing

### Lexical Search
To support lexical search, we construct an inverted index, a classic data structure used by search engines. The construction is very simple: we map from a word --> a list of geoids of cities that have that word somewhere in (one of) their name(s). There are a number of ways to store this index, which is just a key-value store. Since the data was relatively small, I just constructed a Python dictionary in memory to hold this mapping, and used JSON to serialize to a file for persistent storage.

Another reasonable option would have been to use SQLite as a KV-store, making sure to mark the key field as the primary key for fast searches. I decided against this just because I tried storing the entire dictionary in memory and my (very lame, 4GB of RAM-having, 5 year-old) computer didn't seem to struggle at all. Of course, if the data set were larger, I'd definitely switch over to some sort of database.

### Nearest Neighbors Search
To support nearest neighbors search, we construct a 3D R-tree, a classic data structure for storing multi-dimensional/spatial data. R-trees have support for fast nearest neighbors search since they behave essentially like multi-dimensional B-trees (i.e. balanced binary trees, but with multiple dimensions). Of course, I could have just constructed a 3D grid which was broken into cubes or chosen a projection which was broken into squares by latitude/longitude, and performed this search myself. However, cities are not evenly distributed across the cube that contains the entire Earth (e.g. there are no cities that aren't on the surface) and aren't even evenly distributed across the Earth's surface in a 2D projection (e.g. oceans). However, R-trees group data into leaf nodes in a balanced way, which would eliminate my having to deal with this issue. R-trees also ship with a nearest neighbors search, so I didn't have to implement that functionality myself. In addition, R-trees, like B-trees, store on disk nicely and quite fast in practice.

Once I'd picked R-trees, I needed to decide how to actually store the data. The data set stores latitude and longitude coordinates. However, I didn't want to directly plug these coordinates into the R-tree as if they were Eucliean coordinates because cities with the same latitude closer to the equator are further from each other than cities with the same latitude closer to the poles. Furthermore, storing the data as 2D would have been incorrect, as cities with longitude 179 are close to cities with longitude -179, a complexity that 2D data is incapable of representing.

Thus, I needed to represent the data in three dimensions, and Cartesian coordinates were, of course, the natural choice. However, since cities only lie on the surface, there was a choice of two distances: Eucliean and geodetic. While geodetic or great circle distance is probably what is meant when we talk about distances between cities (humans travel on the surface, not through the crust, after all), I chose to use Euclidean distance for the nearest neighbors search. The mathematically valid reason is quite interesting: Eucliean distance is always a lower bound on geodetic distance, and if Euclidean dist(x,y) < Euclidean dist(x,z), then geodetic dist(x,y) < geodetic dist(x,z). That is, nearest neighbors search with Euclidean distance will always return the same result as geodetic distance. The other reason I chose Eucliean distance is that this is what the R-tree implementation I used ships with by default (more on this in the next section).

## Next steps
There's a lot more work that can be done on this project to make the interface more robust. The queries' capabilities are pretty limited right now -- there is some discussion in `lexical_query` documentation about how that function can be expanded (or have multiple versions). It'd be reasonably straightforward to make the return results of the queries more configurable, as right now they just return the data that I find most interesting about a city. If I were to work on this some more, I'd probably have queries return just lists of IDs, and include a function that can return some subset of the columns that the user is interested in for that list of IDs.

The most amount of work I'd want to do here is on the nearest neighbors search. There's a lot that can be better here. First of all, I think I'd probably rewrite the code in C++ because the original library is in C++. Currently, the functionality is limited by the Python hooks available into the C++ implementation. Importantly, this means that you can't select what kind of R-tree you want to use (e.g. the more balanced R*-tree), you can't use custom distance metrics, and you can't perform constrained nearest neighbors search. If I had implemented this in C++ with a custom distance metric, I would have been able to use geodetic distances, which more correspond to our notion of distances between cities on Earth.

Finally, I didn't have time to implement constraint by country, but there were a number of ways to do this. One option would have been to construct a separate R-tree for each country, mapping on the country code. A better solution, however, is to perform constrained nearest neighbor search, which I could have done if I'd written the code in C++ to gain access to the full R-tree functionality.