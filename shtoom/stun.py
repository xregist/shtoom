import struct, socket, time
from twisted.internet import reactor
from twisted.internet.protocol import DatagramProtocol


DefaultServers = [
    ('tesla.divmod.net', 3478),
    ('erlang.divmod.net', 3478),
    ('tesla.divmod.net', 3479),
    ('erlang.divmod.net', 3479),
    ('stun.wirlab.net', 3478),
]

StunTypes = { 
   0x0001: 'MAPPED-ADDRESS',
   0x0002: 'RESPONSE-ADDRESS ',
   0x0003: 'CHANGE-REQUEST',
   0x0004: 'SOURCE-ADDRESS',
   0x0005: 'CHANGED-ADDRESS',
   0x0006: 'USERNAME',
   0x0007: 'PASSWORD',
   0x0008: 'MESSAGE-INTEGRITY',
   0x0009: 'ERROR-CODE',
   0x000a: 'UNKNOWN-ATTRIBUTES',
   0x000b: 'REFLECTED-FROM',
}


class StunProtocol(DatagramProtocol, object):
    def __init__(self, servers=DefaultServers, *args, **kwargs):
        self._pending = {}
        self.servers = servers
        super(StunProtocol, self, *args, **kwargs)

    def datagramReceived(self, dgram, address):
        mt, pktlen, tid = struct.unpack('!hh16s', dgram[:20])
        # Check tid is one we sent and haven't had a reply to yet
        if self._pending.has_key(tid):
            del self._pending[tid]
        else:
            print "error, unknown transaction ID!"
            return
        if mt == 0x0101:
            # response
            remainder = dgram[20:]
            while remainder:
                avtype, avlen = struct.unpack('!hh', remainder[:4])
                val = remainder[4:4+avlen]
                avtype = StunTypes.get(avtype, '(Unknown type %04x)'%avtype)
                remainder = remainder[4+avlen:]
                if avtype in ('MAPPED-ADDRESS',
                              'CHANGED-ADDRESS',
                              'SOURCE-ADDRESS'):
                    dummy,family,port,addr = struct.unpack('!cch4s', val)
                    print "%s: %s %s"%(avtype,socket.inet_ntoa(addr),port)
                    if avtype == 'MAPPED-ADDRESS':
                        self.gotMappedAddress(socket.inet_ntoa(addr),port)
                else:
                    print "unhandled AV %s, val %r"%(avtype, repr(val))
        elif mt == 0x0111:
            print "error!"
        
    def gotMappedAddress(self, addr, port):
        pass

    def sendRequest(self, server, avpairs=()):
        tid = open('/dev/urandom').read(16)
        mt = 0x1 # binding request
        avstr = ''
        # add any attributes
        for a,v in avpairs:
            raise NotImplementedError, "implement avpairs"
        pktlen = len(avstr)
        if pktlen > 65535:
            raise ValueError, "stun request too big (%d bytes)"%pktlen
        pkt = struct.pack('!hh16s', mt, pktlen, tid) + avstr
        self._pending[tid] = (time.time(), server)
        # install a callLater for retransmit and timeouts
        self.transport.write(pkt, server)

    def blatServers(self):
        for s in self.servers:
            self.sendRequest(s)

class StunHook(StunProtocol):
    """Hook a StunHook into a UDP protocol object, and it will discover 
       STUN settings for it
    """
    def __init__(self, protobj, cbMapped, *args, **kwargs):
        self._cbMapped = cbMapped
        self._protocol = protobj
        super(StunProtocol, self, *args, **kwargs)

    def installStun(self):
        self._protocol._mp_datagramReceived = self._protocol.datagramReceived
        self._protocol.datagramReceived = self.datagramReceived

    def gotMappedAddress(self, address, port):
        self._cbMapped(address, port)
        if not self._pending.keys():
            self.uninstallStun()
        # Check for timeouts here

    def uninstallStun(self):
        self._protocol.datagramReceived = self._protocol._mp_datagramReceived


if __name__ == "__main__":
    stunClient = StunProtocol()
    reactor.listenUDP(5061, stunClient)
    reactor.callLater(2, stunClient.blatServers)
    reactor.run()