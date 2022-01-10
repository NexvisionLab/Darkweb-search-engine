import random
from datetime import *

from twisted.internet.defer import Deferred
from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.internet.protocol import Protocol, ClientFactory
from twisted.internet.task import react
from txsocksx.client import SOCKS5ClientEndpoint
from twisted.internet import reactor

from portscanner_utils import PORTS
from tor_db import *

#           |----------------- HOST -----------------|-------------------- PORT --------------------|
#Tor 1
TOR_HOST  = [os.environ['HIDDEN_SERVICE_PROXY_HOST'], int(os.environ['HIDDEN_SERVICE_PROXY_PORT'])]
#Tor 2
TOR_HOST2 = [os.environ['HIDDEN_SERVICE_PROXY_HOST2'], int(os.environ['HIDDEN_SERVICE_PROXY_PORT2'])]
#Tor 3
TOR_HOST3 = [os.environ['HIDDEN_SERVICE_PROXY_HOST3'], int(os.environ['HIDDEN_SERVICE_PROXY_PORT3'])]
#Tor 4
TOR_HOST4 = [os.environ['HIDDEN_SERVICE_PROXY_HOST4'], int(os.environ['HIDDEN_SERVICE_PROXY_PORT4'])]

TOR_HOSTS = [TOR_HOST, TOR_HOST2, TOR_HOST3, TOR_HOST4]

MAX_TOTAL_CONNECTIONS = 16
MAX_CONNECTIONS_PER_HOST = 1

def pop_or_none(l):
    if len(l) == 0:
        return None
    return l.pop()


class PortScannerClient(Protocol):
    def connectionMade(self):
        self.data = []
        self.deferred = Deferred()
        self.transport.loseConnection()

    def dataReceived(self, data):
        self.data.append(data)

    def connectionLost(self, reason):
        self.factory.conn.next_port()
        #self.deferred.callback(''.join(self.data))

class PortScannerClientFactory(ClientFactory):

    def __init__(self, conn):
        self.conn = conn

    def buildProtocol(self, addr):
        p = PortScannerClient()
        p.factory = self
        return p

    def clientConnectionLost(self, connector, reason):
        """If we get disconnected, reconnect to server."""
        print("connection lost")

    def clientConnectionFailed(self, connector, reason):
        print("connection failed")

def gotProtocol(p, conn):
    conn.active_host.add_open_port(conn.current_port)

def gotErr(failure, conn):
    conn.next_port()

class Connection:

    def __init__(self, scanner):
        self.scanner = scanner
        self.active_host = None
        self.current_port = None

    def next_port(self):
        self.current_port = self.active_host.next_port()
        if self.current_port:
            self.connect()
            return self.current_port
        else:
            print("%s is finished" % self.active_host.hostname)
            host = self.scanner.attach_to_next()
            if host is None:
                self.scanner.conn_finished(self)
                return None
            else:
                return self.attach_to(host)

    def attach_to(self, host):
        self.active_host = host
        self.active_host.n_conn += 1
        return self.next_port()


    def connect(self):
        #Generate a random int between 0 and 4 (include) to know which Tor Host we will use.
        index= random.randint(0,4)
        torEndpoint = TCP4ClientEndpoint(reactor, TOR_HOSTS[index][0], TOR_HOSTS[index][1])
        proxiedEndpoint = SOCKS5ClientEndpoint(self.active_host.hostname.encode("ascii"), self.current_port, torEndpoint)
        d = proxiedEndpoint.connect(PortScannerClientFactory(self))
        d.addCallback(gotProtocol, self)
        d.addErrback(gotErr, self)
        #reactor.callLater(60, d.cancel)




class ActiveHost():
    @db_session
    def __init__(self, hostname):
        self.hostname = hostname
        self.port_queue = list(PORTS.keys())
        #self.port_queue = [80]
        self.n_conn = 0
        self.domain = Domain.find_by_host(self.hostname)
        self.domain.portscanned_at = datetime.now()
        random.shuffle(self.port_queue)
        self.domain.open_ports.clear()

    @db_session
    def add_open_port(self, port):
        print("Found open port %s:%d" % (self.hostname, port))
        domain = Domain.find_by_host(self.hostname)
        domain.open_ports.create(port=port)

    def next_port(self):
        return pop_or_none(self.port_queue)



class PortScanner:
    
    
    def conn_new(self):
        self.n_conn += 1
        return Connection(self)

    def conn_finished(self, conn):
        self.n_conn -= 1
        if self.n_conn < 1:
            reactor.stop()

    def attach_to_next(self):
        if self.last is None or self.last.n_conn >= MAX_CONNECTIONS_PER_HOST:
            hostname = pop_or_none(self.host_queue)
            if hostname:
                self.last = ActiveHost(hostname) 
            else:
                self.last = None 
        return self.last

    def __init__(self, hosts):
        self.host_queue   = list(hosts)
        self.active_hosts = list()
        self.n_conn       = 0
        self.last         = None
     
        for i in range(0, MAX_TOTAL_CONNECTIONS):
            host = self.attach_to_next()
            if host:
                conn = self.conn_new()
                conn.attach_to(host)

        reactor.run()
            