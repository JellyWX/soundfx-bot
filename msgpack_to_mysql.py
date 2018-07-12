import msgpack
import zlib

from models import Server, session

with open('data.mp', 'rb') as f:
    data = msgpack.unpackb(zlib.decompress(f.read()), encoding='utf8')

ids = []
for guild in data:
    if guild['id'] in ids:
        print('dup')
        continue
    ids.append(guild['id'])

    s = Server(id=guild['id'], prefix=guild['prefix'][0:5], sounds=guild['sounds'], roles=guild['roles'])
    session.add(s)

session.commit()
