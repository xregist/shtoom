# Copyright (C) 2003 Anthony Baxter

from converters import NullConv, PCM16toULAWConv
import baseaudio, ossaudiodev

opened = None

class OSSAudioDevice(baseaudio.AudioDevice):
    def openDev(self):
        import ossaudiodev
        dev = ossaudiodev.open(self._mode)
        dev.speed(8000)
        dev.nonblock()
        dev.channels(1)
        formats = listFormats(dev)
        if not self._wrapped:
            self.dev = dev
        if 0 and 'AFMT_MU_LAW' in formats:
            dev.setfmt(ossaudiodev.AFMT_MU_LAW)
            self.dev = NullConv(dev)
        elif 'AFMT_S16_LE' in formats:
            dev.setfmt(ossaudiodev.AFMT_S16_LE)
            self.dev = PCM16toULAWConv(dev)
        else:
            raise ValueError, \
                "Couldn't find ULAW or signed 16b PCM, got %s"%(
                ", ".join(formats))

def getAudioDevice(mode, wrapped=1):
    global opened
    if opened is None:
        opened = OSSAudioDevice(mode, wrapped)
    else:
        if opened.isClosed():
            opened.reopen()
    return opened


def listFormats(dev):
    import ossaudiodev as O
    supported = dev.getfmts()
    l = [ x for x in dir(O) if x.startswith('AFMT') ]
    l = [ fmt for fmt in l if getattr(O, fmt) & supported ]
    return l

def test():
    dev = getAudioDevice('rw', wrapped=0)
    print "got device", dev
    print "supports", ", ".join(listFormats(dev))

if __name__ == "__main__":
    test()
