from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, ForeignKey, Boolean
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy_json import NestedMutableJson, MutableJson
import configparser

config = configparser.SafeConfigParser()
config.read('config.ini')
user = config.get('MYSQL', 'USER')
try:
    passwd = config.get('MYSQL', 'PASSWD')
except:
    passwd = None
host = config.get('MYSQL', 'HOST')
database = config.get('MYSQL', 'DATABASE')

Base = declarative_base()


class Server(Base):
    __tablename__ = 'servers'

    map_id = Column(Integer, primary_key=True)
    id = Column(BigInteger, unique=True)
    prefix = Column( String(5) )
    roles = Column( NestedMutableJson )
    sounds = relationship('Sound', backref='server', lazy='dynamic')

    def __repr__(self):
        return '<Server {}>'.format(self.id)


class User(Base):
    __tablename__ = 'users'

    map_id = Column(Integer, primary_key=True)
    id = Column(BigInteger, unique=True)
    last_vote = Column(Integer)

    join_sound_id = Column( Integer, ForeignKey('sounds.id', ondelete='SET NULL'), nullable=True )
    leave_sound_id = Column( Integer, ForeignKey('sounds.id', ondelete='SET NULL'), nullable=True )

    join_sound = relationship('Sound', foreign_keys=[join_sound_id] )
    leave_sound = relationship('Sound', foreign_keys=[leave_sound_id] )

    def __repr__(self):
        return '<User {}>'.format(self.id)


class Sound(Base):
    __tablename__ = 'sounds'

    id = Column( Integer, primary_key=True )
    name = Column( String(20) )

    url = Column( String(120) )
    last_used = Column( Integer )
    plays = Column( Integer )

    emoji = Column( String(64) )

    server_id = Column( BigInteger, ForeignKey('servers.id') )

    public = Column( Boolean, nullable=False, default=False )
    safe = Column( Boolean, nullable=False, default=False )
    locked = Column( Boolean, nullable=False, default=False)
    reports = Column( Integer )


if passwd:
    engine = create_engine('mysql+pymysql://{user}:{passwd}@{host}/{db}?charset=utf8mb4'.format(user=user, passwd=passwd, host=host, db=database))
else:
    engine = create_engine('mysql+pymysql://{user}@{host}/{db}?charset=utf8mb4'.format(user=user, host=host, db=database))
Base.metadata.create_all(bind=engine)

Session = sessionmaker(bind=engine)
session = Session()
