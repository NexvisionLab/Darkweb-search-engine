from Crypto.Hash import SHA256
import re
import math

REGEX = re.compile(r'\b[13][a-zA-Z1-9]{26,34}\b')
REGEX_ALL = re.compile('^[13][a-zA-Z1-9]{26,34}$')

# https://github.com/joeblackwaslike/coinaddr
import coinaddr

def is_valid(addr):
    addr = addr.strip().encode('utf-8')
    try:
        return coinaddr.validate('btc', addr).valid
    except:
        return False

