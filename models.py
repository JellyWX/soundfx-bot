from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, ForeignKey, Boolean
from sqlalchemy import create_engine
from sqlalchemy.dialects.mysql import MEDIUMBLOB, TINYINT
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy_json import NestedMutableJson

from config import config

Base = declarative_base()


class GuildData(Base):
    __tablename__ = 'servers'

    id = Column(BigInteger, primary_key=True, autoincrement=False)
    prefix = Column( String(5), nullable=False, default='?' )
    roles = Column( NestedMutableJson )
    sounds = relationship('Sound', backref='server', lazy='dynamic')
    volume = Column(TINYINT(unsigned=True), nullable=False, default=100)

    # max length of server name is 100 characters
    # store name to do shit rapid
    name = Column(String(100), nullable=True)

    def __repr__(self):
        return '<Server {}>'.format(self.id)


class Sound(Base):
    __tablename__ = 'sounds'

    id = Column( Integer, primary_key=True )
    name = Column( String(20), index=True )

    src = Column( MEDIUMBLOB, nullable=False )
    plays = Column( Integer, nullable=False, default=0 )

    server_id = Column( BigInteger, ForeignKey('servers.id') )
    uploader_id = Column( BigInteger, index=True )

    public = Column( Boolean, nullable=False, default=True )


if config.passwd is not None:
    engine = create_engine('mysql+pymysql://{user}:{passwd}@{host}/{db}?charset=utf8mb4'.format(user=config.user, passwd=config.passwd, host=config.host, db=config.database))
else:
    engine = create_engine('mysql+pymysql://{user}@{host}/{db}?charset=utf8mb4'.format(user=config.user, host=config.host, db=config.database))
Base.metadata.create_all(bind=engine)

Session = sessionmaker(bind=engine)
session = Session()