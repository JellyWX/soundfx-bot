from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, Unicode
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
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
    sounds = Column( NestedMutableJson )
    roles = Column( NestedMutableJson )

    def __repr__(self):
        return '<Server {}>'.format(self.id)


class User(Base):
    __tablename__ = 'users'

    map_id = Column(Integer, primary_key=True)
    id = Column(BigInteger, unique=True)
    last_vote = Column(Integer)


if passwd:
    engine = create_engine('mysql+pymysql://{user}:{passwd}@{host}/{db}?charset=utf8mb4'.format(user=user, passwd=passwd, host=host, db=database))
else:
    engine = create_engine('mysql+pymysql://{user}@{host}/{db}?charset=utf8mb4'.format(user=user, host=host, db=database))
Base.metadata.create_all(bind=engine)

Session = sessionmaker(bind=engine)
session = Session()
