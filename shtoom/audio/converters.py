# Copyright (C) 2004 Anthony Baxter
from shtoom.rtp.formats import PT_PCMU, PT_GSM, PT_SPEEX, PT_DVI4, PT_RAW
from shtoom.rtp.formats import PT_PCMA, PT_ILBC
from shtoom.rtp.formats import PT_CN, PT_xCN, AudioPTMarker
from shtoom.avail import codecs
from shtoom.audio import aufile, playout
from shtoom.lwc import Interface, implements

from twisted.python import log

import sets, struct

try:
    import audioop
except ImportError:
    audioop = None

class NullSink:
    def handle_data(self, data):
        pass

nullsink = NullSink()

class MediaSample:
    def __init__(self, ct, data):
        self.ct = ct
        self.data = data

    def __repr__(self):
        return "<%s/%s, %s>" % (self.__class__.__name__, self.ct, `self.data`,)

class NullConv:
    # Should be refactored away
    def __init__(self, device):
        self._d = device
    def getDevice(self):
        return self._d
    def setDevice(self, d):
        self._d = d
    def getFormats(self):
        if self._d:
            return self._d.getFormats()
    def write(self, data):
        if self._d:
            return self._d.write(data)
    def close(self):
        if self._d:
            log.msg("audio device %r close"%(self._d,), system="audio")
            return self._d.close()
    def reopen(self):
        if self._d:
            log.msg("audio device %r reopen ..."%(self._d,), system="audio")
            return self._d.reopen()
    def isOpen(self):
        if self._d:
            return self._d.isOpen()
    def __repr__(self):
        return '<%s wrapped around %r>'%(self.__class__.__name__, self._d)

def isLittleEndian():
    import struct
    p = struct.pack('H', 1)
    if p == '\x01\x00':
        return True
    elif p == '\x00\x01':
        return False
    else:
        raise ValueError("insane endian-check result %r"%(p))

class IAudioCodec:
    def buffer_and_encode(self, bytes):
        "encode bytes, a string of audio"
    def decode(self, bytes):
        "decode bytes, a string of audio"

class _Codec:
    "Base class for codecs"
    implements(IAudioCodec)
    def __init__(self, samplesize):
        self.samplesize = samplesize
        self.b = ''

    def buffer_and_encode(self, bytes):
        self.b += bytes
        res = []
        while len(self.b) >= self.samplesize:
            sample, self.b = self.b[:self.samplesize], self.b[self.samplesize:]
            res.append(self._encode(sample))
        return res

class GSMCodec(_Codec):
    def __init__(self):
        _Codec.__init__(self, 320)
        if isLittleEndian():
            self.enc = codecs.gsm.gsm(codecs.gsm.LITTLE)
            self.dec = codecs.gsm.gsm(codecs.gsm.LITTLE)
        else:
            self.enc = codecs.gsm.gsm(codecs.gsm.BIG)
            self.dec = codecs.gsm.gsm(codecs.gsm.BIG)

    def _encode(self, bytes):
        assert isinstance(bytes, str), bytes
        return self.enc.encode(bytes)

    def decode(self, bytes):
        assert isinstance(bytes, str), bytes
        if len(bytes) != 33:
            log.msg("GSM: short read on decode, %d !=  33"%len(bytes),
                                                            system="codec")
            return None
        return self.dec.decode(bytes)

class SpeexCodec(_Codec):
    "A codec for Speex"

    def __init__(self):
        self.enc = codecs.speex.new(8)
        self.dec = codecs.speex.new(8)
        _Codec.__init__(self, 320)

    def _encode(self, bytes, unpack=struct.unpack):
        frames = list(unpack('160h', bytes))
        return self.enc.encode(frames)

    def decode(self, bytes):
        if len(bytes) != 40:
            log.msg("speex: short read on decode %d != 40"%len(bytes),
                                                            system="codec")
            return None
        frames = self.dec.decode(bytes)
        ostr = struct.pack('160h', *frames)
        return ostr

class MulawCodec(_Codec):
    "A codec for mulaw encoded audio (e.g. G.711U)"

    def __init__(self):
        _Codec.__init__(self, 320)

    def _encode(self, bytes):
        return audioop.lin2ulaw(bytes, 2)

    def decode(self, bytes):
        if len(bytes) != 160:
            log.msg("mulaw: short read on decode, %d != 160"%len(bytes),
                                                            system="codec")
        return audioop.ulaw2lin(bytes, 2)

class AlawCodec(_Codec):
    "A codec for alaw encoded audio (e.g. G.711A)"

    def __init__(self):
        _Codec.__init__(self, 320)

    def _encode(self, bytes):
        return audioop.lin2alaw(bytes, 2)

    def decode(self, bytes):
        if len(bytes) != 160:
            log.msg("alaw: short read on decode, %d != 160"%len(bytes),
                                                            system="codec")
        return audioop.alaw2lin(bytes, 2)

class NullCodec(_Codec):
    "A codec that consumes/emits nothing (e.g. for confort noise)"

    def __init__(self):
        _Codec.__init__(self, 1)

    def _encode(self, bytes):
        return None

    def decode(self, bytes):
        return None

class PassthruCodec(_Codec):
    "A codec that leaves it's input alone"
    def __init__(self):
        _Codec.__init__(self, None)
    decode = lambda self, bytes: bytes
    buffer_and_encode = lambda self, bytes: [bytes]

def make_codec_set():
    format_to_codec = {}
    format_to_codec[PT_CN] = NullCodec()
    format_to_codec[PT_xCN] = NullCodec()
    format_to_codec[PT_RAW] = PassthruCodec()
    assert codecs.mulaw
    if codecs.mulaw is not None:
        format_to_codec[PT_PCMU] = MulawCodec()
    if codecs.alaw is not None:
        format_to_codec[PT_PCMA] = AlawCodec()
    if codecs.gsm is not None:
        format_to_codec[PT_GSM] = GSMCodec()
    if codecs.speex is not None:
        format_to_codec[PT_SPEEX] = SpeexCodec()
    #if codecs.dvi4 is not None:
    #    format_to_codec[PT_DVI4] = DVI4Codec()
    #if codecs.ilbc is not None:
    #    format_to_codec[PT_ILBC] = ILBCCodec()
    return format_to_codec

known_formats = (sets.ImmutableSet(make_codec_set().keys()) - 
                                  sets.ImmutableSet([PT_CN, PT_xCN,]))

class Codecker:
    def __init__(self, format):
        self.format_to_codec = make_codec_set()
        if not format in known_formats:
            raise ValueError("Can't handle codec %r"%format)
        self.format = format
        self.handler = None

    def set_handler(self, handler):
        """
        handler will subsequently receive calls to handle_media_sample().
        """
        self.handler = handler

    def getDefaultFormat(self):
        return self.format

    def handle_data(self, bytes):
        "Accept audio as bytes, emits MediaSamples."
        if not bytes:
            return None
        codec = self.format_to_codec.get(self.format)
        if not codec:
            raise ValueError("can't encode format %r"%self.format)
        encaudios = codec.buffer_and_encode(bytes)
        for encaudio in encaudios:
            self.handler.handle_media_sample(MediaSample(self.format, encaudio))

    def decode(self, packet):
        "Accepts an RTPPacket, emits audio as bytes"
        if not packet.data:
            return None
        codec = self.format_to_codec.get(packet.header.ct)
        if not codec:
            raise ValueError("can't decode format %r"%packet.header.ct)
        encaudio = codec.decode(packet.data)
        return encaudio

class MediaLayer(NullConv):
    """ The MediaLayer sits between the network and the raw
        audio device. It converts the audio to/from the codec on
        the network to the format used by the lower-level audio
        devices (16 bit signed ints at an integer multiple of 8KHz).
    """
    def __init__(self, device, *args, **kwargs):
        self.playout = None
        self.codecker = None
        self.defaultFormat = None
        NullConv.__init__(self, device, *args, **kwargs) # this sets self._d = device

    def getFormat(self):
        return self.defaultFormat

    def write(self, packet):
        if self.playout is None:
            log.msg("write before reopen, discarding")
            return 0
        audio = self.codecker.decode(packet)
        if audio:
            return self.playout.write(audio, packet.header.seq)
        else:
            self.playout.write('', packet.header.seq)
            return 0

    def selectDefaultFormat(self, fmts=[PT_PCMU,]):
        assert isinstance(fmts, (list, tuple,)), fmts
        assert not self._d or not self._d.isOpen(), \
            "You are required to close the device before calling "+\
            "selectDefaultFormat(). self._d: %s" % (self._d,)

        for f in fmts:
            if f in known_formats:
                self.defaultFormat = f
                break
        else:
            raise ValueError("No working formats!")

    def reopen(self, mediahandler=None):
        """
        mediahandler, if not None, will subsequently receive calls to 
        handle_media_sample().

        This flushes codec buffers.  The audio playout buffers and microphone 
        readin buffers *ought* to be flushed by the lower-layer audio device 
        when we call reopen() on it.
        """
        assert self.defaultFormat, "You are required to selectDefaultFormat()" +\
                                   "before (re-)opening the device."

        self.codecker = Codecker(self.defaultFormat)
        self._d.reopen()
        if mediahandler:
            self.codecker.set_handler(mediahandler)
            self._d.set_sink(self.codecker)
        else:
            self._d.set_sink(nullsink)

        if self.playout:
            log.msg("playout already started")
        else:
            self.playout = playout.Playout(self)

    def play_wave_file(self, fname):
        """
            Note that calling write() in a while loop like this
            effectively blocks the whole Twisted app until we finish
            spooling the whole audio file into the output audio buffer.
            Hopefully this is good enough for now. In the future it would
            be nice if we could just initiate a playout here, the way Doug
            does. That would also allow you to answer the phone before the
            ring file finishes playing... --Zooko 2004-10-21 
            P.S. Oh, and if your output device is ALSA, this will
            immediately overflow the output FIFO, so only the first few
            milliseconds of the wav file will be heard. Whoops. This
            really needs to be fixed... --Zooko 2005-02-25
        """
        if not self._d.isOpen():
            self.selectDefaultFormat([PT_PCMU,])
            self.reopen()
        try:
            wavefileobj = aufile.WavReader(fname)
            data = wavefileobj.read()
            # Note that calling write() in a while loop like this effectively 
            # blocks the whole Twisted app until the audio file is all buffered 
            # up by the underlying audio output device.  Hopefully this is good 
            # enough for now.  In the future it would be nice if we could just 
            # initiate a playout here, the way doug does.  That would also 
            # allow you to answer the phone before the ring file finishes 
            # playing...  --Zooko 2004-10-21
            while data:
                self._d.write(data)
                data = wavefileobj.read()
        except (IOError, ValueError, EOFError,), le:
            print "warning: wave file error: %r, %s, %s" % (le, le, le.args,)
            pass

    def close(self):
        self.playout = None
        self.codecker = None
        self._d.set_sink(nullsink)
        NullConv.close(self)

class DougConverter(MediaLayer):
    "Specialised converter for Doug."
    # XXX should be refactored away to just use a Codecker directly
    def __init__(self, defaultFormat=PT_PCMU, *args, **kwargs):
        self.codecker = Codecker(defaultFormat)
        self.convertInbound = self.codecker.decode
        self.set_handler = self.codecker.set_handler
        if not kwargs.get('device'):
            kwargs['device'] = None
        NullConv.__init__(self, *args, **kwargs)
