from pony.orm import *
from tor_db.db import db
class BlockedDomain(db.Entity):
    _table_   = "blocked_domain"
    domain      = Required(str, 1024)

