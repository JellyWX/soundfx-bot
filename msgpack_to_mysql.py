import msgpack
import zlib

from models import Server, session

with open('data.mp', 'rb') as f:
    data = msgpack.unpackb(zlib.decompress(f.read()), encoding='utf8')

for guild in data:
    s = Server(id=guild['id'], prefix=guild['prefix'], sounds=guild['sounds'], roles=guild['roles'])
    session.add(s)

session.commit()
