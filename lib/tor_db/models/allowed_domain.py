from pony.orm import *
from tor_db.db import db
class AllowedDomain(db.Entity):
    _table_   = "allowed_domain"
    domain      = Required(str, 1024)

