from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, ForeignKey, Boolean, Text, LargeBinary
from sqlalchemy import create_engine
from sqlalchemy.dialects.mysql import MEDIUMBLOB, TINYINT
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy_json import NestedMutableJson, MutableJson

from tinyconf.deserializers import IniDeserializer
from tinyconf.fields import Field

class MysqlConfig(IniDeserializer):
    user = Field(strict=True)
    passwd = Field(strict=False)
    host = Field(strict=False, default='localhost')
    database = Field(strict=False, default='soundfx')

config = MysqlConfig(filename='config.ini', section='MYSQL')
Base = declarative_base()


class GuildData(Base):
    __tablename__ = 'servers'

    map_id = Column(Integer, primary_key=True)
    id = Column(BigInteger, unique=True)
    prefix = Column( String(5) )
    roles = Column( NestedMutableJson )
    sounds = relationship('Sound', backref='server', lazy='dynamic')
    volume = Column(TINYINT(unsigned=True), nullable=False, default=100)

    def __repr__(self):
        return '<Server {}>'.format(self.id)


class Sound(Base):
    __tablename__ = 'sounds'

    id = Column( Integer, primary_key=True )
    name = Column( String(20) )

    src = Column( MEDIUMBLOB, nullable=False )
    plays = Column( Integer, nullable=False, default=0 )

    server_id = Column( BigInteger, ForeignKey('servers.id') )
    uploader_id = Column( BigInteger, ForeignKey('users.id') )

    public = Column( Boolean, nullable=False, default=True )


class User(Base):
    __tablename__ = 'users'

    map_id = Column(Integer, primary_key=True)
    id = Column(BigInteger, unique=True)

    join_sound_id = Column( Integer, ForeignKey('sounds.id', ondelete='SET NULL'), nullable=True )
    join_sound = relationship('Sound', foreign_keys=[join_sound_id] )

    sounds = relationship('Sound', backref='user', foreign_keys=[Sound.uploader_id])

    def __repr__(self):
        return '<User {}>'.format(self.id)


if config.passwd is not None:
    engine = create_engine('mysql+pymysql://{user}:{passwd}@{host}/{db}?charset=utf8mb4'.format(user=config.user, passwd=config.passwd, host=config.host, db=config.database))
else:
    engine = create_engine('mysql+pymysql://{user}@{host}/{db}?charset=utf8mb4'.format(user=config.user, host=config.host, db=config.database))
Base.metadata.create_all(bind=engine)

Session = sessionmaker(bind=engine)
session = Session()