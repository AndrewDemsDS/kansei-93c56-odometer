#!/usr/bin/env python3
"""Generalized checksum sweep over the genuine 93C56 images.

Extends ANALYSIS 15.8: (1) the result is searched for ANYWHERE in the
image (bytes, words in either byte order, decoded per-word units, decoded
3-word V), not only at 0x00-0x05; (2) inputs include the decoded cell views
(units per word, thermometer level per word) since the whole image is
cell-coded; (3) 'constant across samples' tests for sum-to-constant schemes.
A hit is reported only if it holds for every sample in the family set at the
same (algo, region, location).  Trials are counted so spurious-hit
expectation can be stated.
"""
import sys, itertools, collections
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kansei_codec import word_units as decode_word  # noqa

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
SAMPLES = {
 'predonor':  'dumps/predonor-20260901-184533-GOOD.bin',
 'mattydr67': 'reference/community-93c56-93c46-dumps/dk-93c56-mattydr67-130000km.bin',
 'sanjay1a':  'reference/community-93c56-93c46-dumps/dk-93c56-sanjaycip-1a.bin',
 'alimmo':    'reference/community-93c56-93c46-dumps/dk-93c56-alimmo-original-160274mi.bin',
 'd40':       'reference/forum-dumps-d40-navara-different-unit/nissannavara.bin',
}
imgs = {k: open(os.path.join(ROOT, v),'rb').read() for k,v in SAMPLES.items()}
assert all(len(v)==256 for v in imgs.values()), {k:len(v) for k,v in imgs.items()}

def words_be(b): return [(b[i]<<8)|b[i+1] for i in range(0,len(b),2)]
def units(b):
    out=[]
    for w in words_be(b):
        try: out.append(decode_word(w) & 0x1f)
        except Exception: out.append(0)
    return out
def level(w):  # thermometer level: popcount = 1 + 3*level
    return (bin(w).count('1')-1)//3

# ---- CRC catalogue (width, poly, init, refin, refout, xorout)
CRC8 = {
 'CRC8':(0x07,0,0,0,0),'CDMA2000':(0x9B,0xFF,0,0,0),'DARC':(0x39,0,1,1,0),'DVB-S2':(0xD5,0,0,0,0),
 'EBU':(0x1D,0xFF,1,1,0),'I-CODE':(0x1D,0xFD,0,0,0),'ITU':(0x07,0,0,0,0x55),'MAXIM':(0x31,0,1,1,0),
 'ROHC':(0x07,0xFF,1,1,0),'WCDMA':(0x9B,0,1,1,0),'AUTOSAR':(0x2F,0xFF,0,0,0xFF),'BLUETOOTH':(0xA7,0,1,1,0),
 'GSM-A':(0x1D,0,0,0,0),'GSM-B':(0x49,0,0,0,0xFF),'LTE':(0x9B,0,0,0,0),'MIFARE':(0x1D,0xC7,0,0,0),
 'NRSC5':(0x31,0xFF,0,0,0),'OPENSAFETY':(0x2F,0,0,0,0),'SAE-J1850':(0x1D,0xFF,0,0,0xFF),'HITAG':(0x1D,0xFF,0,0,0),
 'P1D-FF':(0x1D,0xFF,0,0,0),'P31-FF-ref':(0x31,0xFF,1,1,0),'P07-FF':(0x07,0xFF,0,0,0),
}
CRC16 = {
 'ARC':(0x8005,0,1,1,0),'AUG-CCITT':(0x1021,0x1D0F,0,0,0),'UMTS':(0x8005,0,0,0,0),'CCITT-FALSE':(0x1021,0xFFFF,0,0,0),
 'CDMA2000':(0xC867,0xFFFF,0,0,0),'DDS-110':(0x8005,0x800D,0,0,0),'DECT-R':(0x0589,0,0,0,1),'DECT-X':(0x0589,0,0,0,0),
 'DNP':(0x3D65,0,1,1,0xFFFF),'EN13757':(0x3D65,0,0,0,0xFFFF),'GENIBUS':(0x1021,0xFFFF,0,0,0xFFFF),'MAXIM':(0x8005,0,1,1,0xFFFF),
 'MCRF4XX':(0x1021,0xFFFF,1,1,0),'RIELLO':(0x1021,0xB2AA,1,1,0),'T10-DIF':(0x8BB7,0,0,0,0),'TELEDISK':(0xA097,0,0,0,0),
 'TMS37157':(0x1021,0x89EC,1,1,0),'USB':(0x8005,0xFFFF,1,1,0xFFFF),'CRC-A':(0x1021,0xC6C6,1,1,0),'KERMIT':(0x1021,0,1,1,0),
 'MODBUS':(0x8005,0xFFFF,1,1,0),'X25':(0x1021,0xFFFF,1,1,0xFFFF),'XMODEM':(0x1021,0,0,0,0),'CMS':(0x8005,0xFFFF,0,0,0),
 'GSM':(0x1021,0,0,0,0xFFFF),'LJ1200':(0x6F63,0,0,0,0),'NRSC5':(0x080B,0xFFFF,1,1,0),'OPENSAFETY-A':(0x5935,0,0,0,0),
 'OPENSAFETY-B':(0x755B,0,0,0,0),'PROFIBUS':(0x1DCF,0xFFFF,0,0,0xFFFF),'M17':(0x5935,0xFFFF,0,0,0),
}
def crc(data, width, poly, init, refin, refout, xorout):
    top = 1<<(width-1); mask=(1<<width)-1; reg=init
    for b in data:
        if refin: b = int('{:08b}'.format(b)[::-1],2)
        reg ^= b << (width-8)
        for _ in range(8):
            reg = ((reg<<1)^poly)&mask if reg&top else (reg<<1)&mask
    if refout: reg = int(('{:0%db}'%width).format(reg)[::-1],2)
    return reg ^ xorout

def algos():
    for n,p in CRC8.items(): yield ('crc8-'+n, 8, lambda d,p=p: crc(d,8,*p))
    for n,p in CRC16.items(): yield ('crc16-'+n, 16, lambda d,p=p: crc(d,16,*p))
    yield ('sum8',8, lambda d: sum(d)&0xff)
    yield ('negsum8',8, lambda d: (-sum(d))&0xff)
    yield ('notsum8',8, lambda d: (~sum(d))&0xff)
    yield ('xor8',8, lambda d: __import__('functools').reduce(lambda a,b:a^b,d,0))
    yield ('notxor8',8, lambda d: 0xff ^ __import__('functools').reduce(lambda a,b:a^b,d,0))
    yield ('sum16',16, lambda d: sum(d)&0xffff)
    yield ('negsum16',16, lambda d: (-sum(d))&0xffff)
    yield ('wsum16be',16, lambda d: sum(words_be(d if len(d)%2==0 else d+b'\0'))&0xffff)
    yield ('negwsum16be',16, lambda d: (-sum(words_be(d if len(d)%2==0 else d+b'\0')))&0xffff)
    yield ('wsum16le',16, lambda d: sum(int.from_bytes(d[i:i+2],'little') for i in range(0,len(d)-1,2))&0xffff)
    yield ('wxor16be',16, lambda d: __import__('functools').reduce(lambda a,b:a^b,words_be(d if len(d)%2==0 else d+b'\0'),0))
    yield ('notwxor16be',16, lambda d: 0xffff ^ __import__('functools').reduce(lambda a,b:a^b,words_be(d if len(d)%2==0 else d+b'\0'),0))
    def fl16(d):
        a=b=0
        for x in d: a=(a+x)%255; b=(b+a)%255
        return (b<<8)|a
    yield ('fletcher16',16, fl16)
    yield ('popcount',16, lambda d: sum(bin(x).count('1') for x in d))
    yield ('zerocount',16, lambda d: sum(8-bin(x).count('1') for x in d))

# byte regions [a,b)
CUTS = [0x00,0x06,0x50,0x62,0x64,0x6a,0x6e,0x70,0x8e,0x100]
REGIONS = [(a,b) for a,b in itertools.combinations(CUTS,2)]
REGIONS += [('excl',0x00,0x06),('excl',0x6a,0x70),('excl',0x00,0x06,0x6a,0x70)]

def region_bytes(img, r):
    if r[0]=='excl':
        keep=bytearray(img); ex=set()
        for i in range(1,len(r),2): ex.update(range(r[i],r[i+1]))
        return bytes(x for i,x in enumerate(keep) if i not in ex)
    return img[r[0]:r[1]]

def region_units(u, r):
    if r[0]=='excl':
        ex=set()
        for i in range(1,len(r),2): ex.update(range(r[i]//2,r[i+1]//2))
        return [x for i,x in enumerate(u) if i not in ex]
    return u[r[0]//2:r[1]//2]

VIEWS = {
  'raw': lambda img,u,lv,r: region_bytes(img,r),
  'swapped': lambda img,u,lv,r: bytes(x for w in words_be(region_bytes(img,r)) for x in (w&0xff,w>>8)),
  'units': lambda img,u,lv,r: bytes(region_units(u,r)),
  'levels': lambda img,u,lv,r: bytes(region_units(lv,r)),
}

def locations(img, u, val, width):
    """Return set of location descriptors where val appears."""
    locs=set()
    if width==8:
        for i,x in enumerate(img):
            if x==val: locs.add(('byte',i))
    else:
        for i in range(0,255):
            if (img[i]<<8|img[i+1])==val: locs.add(('be16',i))
            if (img[i+1]<<8|img[i])==val: locs.add(('le16',i))
    for w,x in enumerate(u):
        if x==(val&0x1f): locs.add(('unit',w))
    for w in range(0,126):
        V=u[w]+32*u[w+1]+1024*u[w+2]
        if V==(val&0x7fff): locs.add(('V3',w))
    return locs

def main(family):
    U={k:units(v) for k,v in imgs.items()}
    LV={k:[level(w) for w in words_be(v)] for k,v in imgs.items()}
    trials=0; hits=collections.defaultdict(list); const_hits=[]
    for vname,vf in VIEWS.items():
        for aname,width,af in algos():
            for r in REGIONS:
                vals={}
                for s in family:
                    d=vf(imgs[s],U[s],LV[s],r)
                    if len(d)==0: break
                    vals[s]=af(d)
                if len(vals)!=len(family): continue
                trials+=1
                # sum-to-constant: same value in every sample, on inputs that differ
                inputs={s:bytes(vf(imgs[s],U[s],LV[s],r)) for s in family}
                if len(set(vals.values()))==1 and len(set(inputs.values()))>1 \
                        and vals[family[0]] not in (0,0xff,0xffff):
                    const_hits.append((vname,aname,r,hex(vals[family[0]])))
                # location search: intersect across samples
                common=None
                for s in family:
                    L=locations(imgs[s],U[s],vals[s],width)
                    common = L if common is None else common & L
                    if not common: break
                if common:
                    # A plain hash cannot contain its own result, so drop locations inside the
                    # input region, and drop the all-0xFF tail and 5-bit unit matches, which
                    # hit by chance far too often to mean anything.
                    keep=[]
                    for l in sorted(common):
                        if l[0] not in ('byte','be16','le16') or l[1]>=0x8e: continue
                        if r[0]!='excl' and r[0]<=l[1]<r[1]: continue
                        keep.append(l)
                    if keep and not any(v in (0,0xff,0xffff,0x80,0x8000,0x0080) for v in vals.values()):
                        hits[(vname,aname,r)]=keep
    print(f'family={family}  trials={trials}')
    print('--- value identical across all samples (sum-to-constant candidates):')
    for h in const_hits: print('  ',h)
    print('--- (view, algo, region) whose value sits at the SAME location in every sample')
    print('    (below 0x8e, outside its own input region, non-trivial value):')
    for k,v in hits.items(): print('  ',k,'->',v)
    if not hits: print('   none')
    print('Expect roughly trials*positions/2^width chance hits per family member; only a hit')
    print('shared by three independent images at one location is worth a bench cycle (ANALYSIS 6).')

if __name__=='__main__':
    fam=sys.argv[1:] or ['predonor','mattydr67','sanjay1a']
    main(fam)
