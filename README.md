# Nexvisions TOR Hidden Service Crawler

This is a copy of the source for the http://zlal32teyptf4tvi.onion hidden service, which implements a tor hidden service crawler/spider and website.

## Features

* Crawls the darknet looking for new hidden service
* Find hidden services from a number of clear net sources
* Optional full-text Elasticsearch support
* Marks clone sites of the /r/darknet super list
* Finds SSH fingerprints across hidden services
* Finds email addresses across hidden  services
* Finds bitcoin addresses across hidden services
* Shows incoming / outgoing links to onion domains
* Up-to-date alive/dead hidden service status
* Portscanner
* Search for "interesting" URL paths, useful 404 detection
* Automatic language detection
* Fuzzy clone detection (requires Elasticsearch, more advanced than super list clone detection)
* Doesn't fuck around in general.

## Licence

This software is made available under the GNU Affero GPL 3 License. What this means is that is you deploy this software as part of the networked software that is available to the public, you must make the source code available (and any modifications).

From the GNU site:

> The GNU Affero General Public License is a modified version of the ordinary GNU GPL version 3. It has one added requirement: if you run a modified program on a server and let other users communicate with it there, your server must also allow them to download the source code corresponding to the modified version running there

## Docker installation
First of all, clone the GitHub project and run the script create_flask_web to generate the secret file used by the web server.

    git clone https://github.com/GoSecure/nexvisions-torscraper.git
    cd nexvisions-torscraper/scripts/
    ./create_flask_secret.sh

Once your flask secet is create, you should see this confirmation message:
> ('Directory ', '/your/path/nexvisions-torscraper/etc/private/', ' Created ')
Written flask secret to '/your/path/nexvisions-torscraper/etc/private/flask.secret'

Now go to the nexvisions-torscraper root directory and start the docker containers by doing:

    sudo docker-compose up

The docker-compose command will start 9 different containers.
* Web service (1)
* Crawler (1)
* Database (1)
* Kibana (1)
* Elasticsearch (1)
* nexvisions-torscraper-tor-privoxy (4)

**Do these steps once (only when all containers are built for the first time).**
Once all the containers are started, open another terminal and connect to the crawler container.

    sudo docker exec -it nexvisions-torscraper-crawler /bin/bash

Now you supposed to have a terminal in the container. So we will run the script elasticsearch_migrate.sh

    cd scripts
    ./elasticsearch_migrate.sh

It will Initialize Elasticsearch database.


In the crawler container, it has a script that will crawl automatically (docker_haproxy_harvest_scrape.sh). This script restart the haproxy service (repartition of request), start harvest (search all onions site in the list of website that we provide) and after that it scrape all of them (Find bitcoin address, Email, link between onions, and save the data of website to the Elasticsearch and the database). Once this script finishes his execution, it will start over.

** Harvesting takes a lot of time so be patient, It can take up to (45 minutes) to get all onions in the list of website that we provide. **

If you prefer doing it the manual way, follow the procedure below.
## Manual Installation

### Dependencies

* python
* tor

### Warning
This software requires an Elasticsearch version in the 5.x series. As of this writing, the latest is 5.6.6. 6.x is known to be problematic. Also, if you decide to install Kibana or any extra functionalities linked to Elasticsearch, install them with the same version otherwise it won't work.

Do not start too many instances of scraper/crawler because, with only 4 instances of tor proxy, it will be hard to connect to the onion site. If you create more than 3-4 instances, it could become really slow. In this situation,  the crawler will become so slow that they will not be able to crawl pages. So you will not progress with this method. Let the crawler run and you will create a bigger list of valid domains with information in it.

The Pastebin script works only if you are on the whitelist of Pastebin. If you're not, you will need to read the scraping API to understand how to activate it: https://pastebin.com/api_scraping_faq

After booting, be sure that the link between Tor and Privoxy are working. To test it, use these commands.

    curl --socks5-hostname 127.0.0.1:9050 http://workingOnionWebsite
    curl --proxy 127.0.0.1:3129 http://workingOnionWebsite

If it didn't work, fix the problem before crawling because all your onions will convert to a "dead" status. You can try to run the script:`start.sh` to reinitialize the links.

### Tor service
To use the new version of tor, you should follow these steps: https://www.torproject.org/docs/debian.html.en
By using the last version of tor, you will be able to crawl the new generation of onions (V3).

If you used a version older than 0.3.x, you can have a problem with the update to 0.3.x. I was missing two libraries:

 * libssl1.1
 * libzstd1

So, I installed them:

        sudo apt-get install libzstd1

To install libssl1.1, I used a Debian package: https://packages.ubuntu.com/bionic/libssl1.1

        lynx  https://packages.ubuntu.com/bionic/libssl1.1

Use the bottom arrow to go at the bottom of the page and select your "Architecture Package Size". When you had made your choice, click on the right arrow, it will redirect you to the download page. Now it's the same thing. Use the bottom arrow to go down and choose the one that you want. When you find the one, just click on the right arrow. At the bottom of your interface, you will see `D) Download or C) Cancel`. Press `D`. When you will see the text `Save to disk`, go on it. Press the right arrow and press on `Enter`. When it's done click on `q` and `y` to quit.

        dpkg -i libssl1.1_1.1.0g-2ubuntu2_amd64.deb #the name of your debain package

Finish the tor installation by looking to your version. If you have the last one (0.3.2 at the time that I wrote it).

        tor --version


### Haproxy service

    sudo apt-get install haproxy
    
### Privoxy service

    sudo apt-get install privoxy

### Install Pip:

    sudo apt-get install python-pip
    sudo pip install --upgrade pip
### Install Virtual environment    
    sudo pip install virtualenv
    sudo apt-get install python-virtualenv

Go in your crawler/scraper folder and write.

    virtualenv venv

then activate it.

    . venv/bin/activate
    # Run the next command when you're in your virtual environment because if you aren't, it will install in your normal environment
    pip install -r requirements.txt
### Install MariaDB
*** Mysql has problems with some syntax in the code so I recommend you to install MariaDB ***

    sudo apt-get install mariadb-server
    sudo apt-get install mariadb-client

Now we will connect to MariaDB and create our database from `schema.sql`. We need to be in the folder to be able to see `schema.sql` because we will need it later.

    mysql -u root
    CREATE DATABASE databaseName;
    use databaseName;
    source schema.sql
To know if all works well you should have "Query OK" on each row. You should have 20 tables if you do this command:

    show tables;

Need a modification to be able to connect Elasticsearh with our database.

    use mysql;
    update user set plugin='mysql_native_password' where User='root';
    flush privileges;
    exit
    #To secure the installation. By default the password should be empty so just press enter. I recommand to put one.
    sudo mysql_secure_installation
    #To reconnect
    mysql -u root -p

### Config your files
Edit `etc/database` for your database setup

Edit `etc/tor/torrc` to uncomment the line : SocksPort 9050 (line 18)

Edit `etc/uwsgi_only` and set BASEDIR to wherever torscraper is installed (i.e. /home/user/torscraper)

Edit `etc/proxy` for your TOR setup

    export TOR_PROXY_PORT=3129
    #export TOR_PROXY_PORT=3140
    export TOR_PROXY_HOST=localhost
    export http_proxy=http://localhost:3129
    #export http_proxy=http://localhost:3140
    export https_proxy=https://localhost:3129
    export SOCKS_PROXY=localhost:9050
    HIDDEN_SERVICE_PROXY_HOST=127.0.0.1
    HIDDEN_SERVICE_PROXY_PORT=9090

 Now we will go in Privoxy config

    cd /etc/privoxy/
    cp default.action default.action.orig
    cp default.filter default.filter.orig
    touch default.action (leave the file empty)
    touch default.filter (leave the file empty)

### Start your services

    service tor start
    service privoxy start
    service haproxy start
    service elasticsearch start
    service mysql start

Go to the scripts folder and run this command

    ./create_privoxy_confs.sh
   
Now it's time to try. Go to the directory:  .../nexvisions-torscraper/scripts/. This directory is relative, you could have changed the name of the directory.

    ./start.sh
    
Now you can test if it works with the new generation of onions (V3) (test all ports 9051, 9052, 90... and 3129, 3130, 31...)

    curl --socks5-hostname 127.0.0.1:9051 http://jamie3vkiwibfiwucd6vxijskbhpjdyajmzeor4mc4i7yopvpo4p7cyd.onion/
    curl --proxy 127.0.0.1:3129 http://jamie3vkiwibfiwucd6vxijskbhpjdyajmzeor4mc4i7yopvpo4p7cyd.onion/

If you get something like "Privoxy localhost port forwarding" don't continue, it will not work.

    ./push.sh someoniondirectory.onion

To start the flask server to see our web interface. First, create a flask secret with:

    mkdir -p etc/private/
    python3 -c 'import os; print("FLASK_SECRET=\"" + os.urandom(32).decode("ascii", errors="backslashreplace") + "\"")' > etc/private/flask.secret

Then start the Web server with:

    ./scripts/web.sh

To set up the port forwarding from your server to your browser, do this command on your computer to access server

    ssh -L 5000:localhost:5000 username@IpAddressOfServer

To try if it works well for now.

    scripts/push.sh someoniondirectory.onion
    scripts/push.sh anotheroniondirectory.onion
    
Run:

    script/harvest.sh  #To get onions (just detect the onions, don't go deeper to find bitcoin address, emails, etc.)
    init/scraper_service.sh  #To start crawling (will get bitcoin address, emails, etc. if you already found onions with harvest.sh)
    init/isup_service.sh  #To keep site status up to date
    
### Optional ElasticSearch Fulltext Search

The Torscraper comes with optional Elasticsearch capability (enabled by default). Edit `etc/elasticsearch` and set vars or set `ELASTICSEARCH_ENABLED=false` to disable. 

Run `scripts/elasticsearch_migrate.sh` to perform the initial setup after configuration.

If Elasticsearch is disabled there will be no full-text search, however crawling and discovering new sites will still work.


### ElasticSearch
You will need to install Elasticsearch(probably not only the pip package), this is the link to download the last version of 5.x. : https://www.elastic.co/downloads/past-releases/elasticsearch-5-6-6 . You can have problems with versions (like I said in the warning section). If you want to be sure you are using the right version, you can do this command :

    curl -XGET 'http://localhost:9200'

To enable Elasticsearch

    service elasticsearch start
    ./elasticsearch_migrate.sh  #To perform the initial setup or if you want to reset Elasticsearch, but we need it at the beginning to start it. 

After restart :

    . venv/bin/activate
    ./script/start.sh  #To start the instance of tor and privoxy

### FLASK :
    ./scripts/web.sh  #Launch flask to have a web interface

### Cronjobs

    #Harvest onions from various sources
    1 18 * * * /home/nexvisions-torscraper/scripts/harvest.sh

    #Get ssh fingerprints for new sites
    1 4,16 * * * /home/nexvisions-torscraper/scripts/update_fingerprints.sh

    #Mark sites as genuine / fake from the /r/darknetmarkets superlist
    1 1 * * 1 /home/nexvisions-torscraper/scripts/get_valid.sh

    #Scrape pastebin for onions (needs paid account / IP whitelisting)
    */5 * * * * /home/nexvisions-torscraper/scripts/pastebin.sh

    #Portscan new onions
    1 13 * * * /home/nexvisions-torscraper/scripts/portscan_up.sh

    #Scrape stronghold paste
    32 */2 * * * /home/nexvisions-torscraper/scripts/stronghold_paste_rip.sh

    #Detect clones
    20 14 * * * /home/nexvisions-torscraper/scripts/detect_clones.sh

    #Keep a sql dump of data
    1 */1 * * * mysqldump -u username -ppassword --database tor --result-file=/home/dump.sql
    1 */8 * * * mysqldump -u username -ppassword --database tor --result-file=/home/dump_backup.sql


## Infrastructure

Nexvisions runs on two servers, a frontend host running the database and hidden service website, and a backend host running the crawler. Probably most interesting to the reader is the setup for the backend. TOR as a client is COMPLETELY SINGLETHREADED. I know! It's 2017, and along with a complete lack of flying cars, TOR runs in a single thread. What this means is that if you try to run a crawler on a single TOR instance you will quickly find you are maxing out your CPU at 100%.

The solution to this problem is running multiple TOR instances and connecting to them through some kind of frontend that will round-robin your requests. The Nexvisions crawler runs eight Tor instances.

Debian (and Ubuntu) comes with a useful program "tor-instance-create" for quickly creating multiple instances of TOR. I used Squid as my frontend proxy, but unfortunately, it can't connect to SOCKS directly, so I used "Privoxy" as an intermediate proxy. You will need one Privoxy instance for every TOR instance. There is a script in "scripts/create_privoxy.sh" to help with creating Privoxy instances on Debian systems. It also helps to replace /etc/privoxy/default.filter with an empty file, to reduce CPU load by removing unnecessary regexes.

Additionally, this resource https://www.howtoforge.com/ultimate-security-proxy-with-tor might be useful in setting up squid. If all you are doing is crawling and don't care about anonymity, I also recommend running TOR in tor2web mode (required recompilation) for increased speed.
