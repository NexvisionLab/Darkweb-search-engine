import urllib.parse 
import re
import os
import time as TimeA

from pony.orm import *
from datetime import *
import dateutil.parser
import pretty
import banned
from tor_elasticsearch import *

from tor_db.db import db
from tor_db.constants import *
from tor_db.models import *


TimeA.sleep(10)

db.generate_mapping(create_tables=True)